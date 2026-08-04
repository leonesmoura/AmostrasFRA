/*
 * AMOSTRAS FRA 2.0 - Firmware TTGO T-Display <-> AD5933 (KDT5933-013)
 * ===================================================================
 * Mesmo protocolo serial do firmware base (esp32_ad5933.ino) — o
 * AmostrasFRA nao percebe diferenca — com interface local no display
 * ST7735 80x160 (telas.h) e botoes da placa:
 *
 *   BTN1 (GPIO 0)  = inicia a varredura local / cancela em andamento
 *   BTN2 (GPIO 35) = alterna o brilho do display
 *
 * LIGACAO (conector P1 da placa AD5933, XH2.54 4 pinos):
 *      P1.1 = GND    -> GND do T-Display
 *      P1.2 = SCL    -> GPIO 22
 *      P1.3 = SDA    -> GPIO 21
 *      P1.4 = 5V-VIN -> 5V do T-Display (a placa regula p/ 3,3 V)
 * O I2C da placa opera em 3,3 V — ligacao direta, sem conversor.
 *
 * Comandos por serial (um por linha, 115200 baud):
 *   S  -> executa uma varredura
 *   T  -> le a temperatura do chip
 *   C f0=<Hz> df=<Hz> n=<pts> vpp=<mV> pga=<1|5> st=<ciclos>
 *      -> configura a varredura (enviado pelo AmostrasFRA)
 *   V  -> liga a excitacao continua na frequencia inicial (bancada)
 *   P  -> desliga a excitacao
 *
 * Saida por ponto (formato rotulado que o AmostrasFRA ja aceita):
 *   f=<Hz> z'=<ohm> z''=<ohm>\n
 */

#include <Arduino.h>
#include <Wire.h>
#include <math.h>

#include "telas.h"

// ------------------------- CONFIGURACAO ---------------------------
static const uint8_t  SDA_PIN = 21;
static const uint8_t  SCL_PIN = 22;
static const uint32_t I2C_HZ  = 100000;
static const long     BAUD    = 115200;

// Botoes do T-Display (ativos em nivel baixo; GPIO35 e' input-only e
// tem pull-up externo na placa).
static const uint8_t BTN1_PIN = 0;
static const uint8_t BTN2_PIN = 35;

// Clock do AD5933 (Hz). Interno = 16,776 MHz. Se usar clock externo
// no SMA P5, coloque aqui a frequencia real injetada.
static const double   AD5933_MCLK_HZ = 16776000.0;
static const bool     USAR_CLOCK_EXTERNO = false;

// Varredura (configuravel em tempo real pelo comando "C").
static double   F_INICIAL    = 1000.0;   // Hz
static double   F_INCREMENTO = 1000.0;   // Hz por passo
static uint16_t N_PONTOS     = 100;      // pontos (<=512)

enum { SAIDA_2V=0x0000, SAIDA_200mV=0x0200, SAIDA_400mV=0x0400, SAIDA_1V=0x0600 };
enum { PGA_x5=0x0000, PGA_x1=0x0100 };
// SAIDA_2V (1,98 Vpp, bias DC 1,48 V) e' a faixa com menor degrau DC
// contra o terra virtual VDD/2 = 1,65 V do VIN, impedancia de saida de
// 200 ohm e +-5,8 mA de acionamento. E' a faixa usada nos exemplos do
// fabricante (AD5933.c, DA5933_Get_Rs). As faixas menores tem bias DC
// mais baixo e forcam corrente continua pelo DUT.
static uint16_t FAIXA_SAIDA = SAIDA_2V;
static uint16_t GANHO_PGA   = PGA_x1;
static uint16_t CICLOS_ACOMODACAO = 100;

// Frequencia minima util: a DFT integra 1024 amostras a MCLK/16, ou
// seja uma janela fixa de 1024*16/MCLK segundos (0,98 ms com o clock
// interno). Abaixo de MCLK/16384 nem um ciclo completo cabe na janela
// e o par real/imag deixa de ser uma medida de impedancia. Bate com a
// faixa de 1 kHz a 100 kHz especificada no datasheet.
static double freqMinimaDft() { return AD5933_MCLK_HZ / 16384.0; }

// --- Calibracao (fase 3) ---
#define MODO_CALIBRACAO 0
// ATENCAO: R_CALIBRACAO tem que ser o valor REAL do padrao usado e tem
// que estar dentro da janela que o resistor de transimpedancia da placa
// (R9, 200 kohm de fabrica) permite: na pratica 220 kohm a 1 Mohm. Um
// padrao de 1 kohm satura o estagio I-V e produz um gain factor invalido
// — para medir a decada de 1 kohm e' preciso trocar R9 por ~1 kohm.
static const double R_CALIBRACAO = 220000.0;
static const double GAIN_FACTOR  = 1.0;   // placeholder: calibrar (fase 3)
static const double FASE_SISTEMA = 0.0;   // placeholder: calibrar (fase 3)

// Convencao de sinal de Z'' do AmostrasFRA (Z'' < 0 p/ capacitivo).
static const bool INVERTER_SINAL_ZII = false;

// ------------------------- REGISTRADORES --------------------------
static const uint8_t ADDR = 0x0D;
static const uint8_t REG_CTRL_HI = 0x80, REG_CTRL_LO = 0x81;
static const uint8_t REG_FSTART  = 0x82, REG_FINCR   = 0x85;
static const uint8_t REG_NINCR   = 0x88, REG_SETTLE  = 0x8A;
static const uint8_t REG_STATUS  = 0x8F, REG_TEMP    = 0x92;
static const uint8_t REG_REAL    = 0x94, REG_IMAG    = 0x96;
static const uint8_t PTR_CMD     = 0xB0;

static const uint8_t CMD_INIT   = 0x10;
static const uint8_t CMD_START  = 0x20;
static const uint8_t CMD_INCR   = 0x30;
static const uint8_t CMD_TEMP   = 0x90;
static const uint8_t CMD_PDOWN  = 0xA0;
static const uint8_t CMD_STANDBY= 0xB0;

static bool chipOk = false;

// ------------------------- I2C BAIXO NIVEL ------------------------
static bool escreveReg(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(ADDR);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

static uint8_t leReg(uint8_t reg) {
  Wire.beginTransmission(ADDR);
  Wire.write(PTR_CMD);
  Wire.write(reg);
  Wire.endTransmission();
  Wire.requestFrom((int)ADDR, 1);
  return Wire.available() ? Wire.read() : 0;
}

static int16_t leReg16(uint8_t reg) {
  uint8_t hi = leReg(reg);
  uint8_t lo = leReg(reg + 1);
  return (int16_t)((hi << 8) | lo);
}

static uint8_t ctrlHi(uint8_t cmd) {
  uint16_t rangePga = (FAIXA_SAIDA | GANHO_PGA) >> 8;
  return cmd | (rangePga & 0x0F);
}

static uint8_t ctrlLo(bool reset) {
  uint8_t v = 0;
  if (reset) v |= 0x10;
  if (USAR_CLOCK_EXTERNO) v |= 0x08;
  return v;
}

static void escreveFreq(uint8_t reg, double f) {
  uint32_t code = (uint32_t)((536870912.0 / AD5933_MCLK_HZ) * f);  // 2^29
  escreveReg(reg,     (code >> 16) & 0xFF);
  escreveReg(reg + 1, (code >> 8)  & 0xFF);
  escreveReg(reg + 2,  code        & 0xFF);
}

// ------------------------- AUXILIARES -----------------------------
static int vppMv() {
  return FAIXA_SAIDA == SAIDA_2V ? 2000 : FAIXA_SAIDA == SAIDA_1V ? 1000 :
         FAIXA_SAIDA == SAIDA_400mV ? 400 : 200;
}

static int pgaX() { return GANHO_PGA == PGA_x1 ? 1 : 5; }

// Leitura com debounce simples (ativo em nivel baixo).
static bool botaoPressionado(uint8_t pino) {
  if (digitalRead(pino) != LOW) return false;
  delay(30);
  if (digitalRead(pino) != LOW) return false;
  // Espera soltar (evita repeticao).
  uint32_t t0 = millis();
  while (digitalRead(pino) == LOW && millis() - t0 < 800) delay(5);
  return true;
}

static double leTemperaturaC() {
  escreveReg(REG_CTRL_HI, CMD_TEMP);
  delay(10);
  int16_t raw = leReg16(REG_TEMP);
  return (raw < 8192) ? raw / 32.0 : (raw - 16384) / 32.0;
}

static void mostraEstado() {
  double t = chipOk ? leTemperaturaC() : 0.0;
  telas::estado(chipOk, t);
}

// --------------------------- VARREDURA ----------------------------
static void configuraSweep() {
  uint16_t nIncr = (N_PONTOS > 0) ? (N_PONTOS - 1) : 0;

  escreveReg(REG_CTRL_LO, ctrlLo(true));            // reset
  escreveReg(REG_CTRL_HI, ctrlHi(CMD_STANDBY));     // standby

  escreveFreq(REG_FSTART, F_INICIAL);
  escreveFreq(REG_FINCR,  F_INCREMENTO);
  escreveReg(REG_NINCR,   (nIncr >> 8) & 0xFF);
  escreveReg(REG_NINCR+1,  nIncr       & 0xFF);
  escreveReg(REG_SETTLE,  (CICLOS_ACOMODACAO >> 8) & 0x01);
  escreveReg(REG_SETTLE+1, CICLOS_ACOMODACAO       & 0xFF);
  escreveReg(REG_CTRL_LO, ctrlLo(false));
}

static void converteImpedancia(int16_t re, int16_t im,
                               double &zr, double &zi) {
  double mag = sqrt((double)re * re + (double)im * im);
  double zmod = (GAIN_FACTOR > 0 && mag > 0)
                ? 1.0 / (GAIN_FACTOR * mag) : 0.0;
  double theta = atan2((double)im, (double)re) - FASE_SISTEMA;
  zr = zmod * cos(theta);
  zi = zmod * sin(theta);
  if (INVERTER_SINAL_ZII) zi = -zi;
}

static void executaVarredura() {
#if !MODO_CALIBRACAO
  // Sem calibracao o gain factor e' o placeholder 1.0 e |Z| = 1/mag sai
  // ~5e6 vezes menor que o valor real (0,0002 ohm para 1 kohm). Melhor
  // recusar do que emitir numeros com cara de medida valida. O gain
  // factor fisico fica na ordem de 1e-9; qualquer valor acima de 1e-4
  // e' placeholder ou erro de digitacao.
  if (GAIN_FACTOR > 1e-4) {
    Serial.println("# ERRO: firmware nao calibrado (GAIN_FACTOR placeholder).");
    Serial.println("#       Rode com MODO_CALIBRACAO 1 e preencha GAIN_FACTOR/FASE_SISTEMA.");
    telas::erro("Nao calibrado - ver fase 3");
    return;
  }
#endif
  if (F_INICIAL < freqMinimaDft()) {
    Serial.print("# AVISO: f0 abaixo do minimo da DFT (");
    Serial.print(freqMinimaDft(), 1);
    Serial.println(" Hz) - pontos baixos sem validade.");
  }

  configuraSweep();
  telas::iniciaVarredura(N_PONTOS, vppMv());

  escreveReg(REG_CTRL_HI, ctrlHi(CMD_INIT));   // energiza VOUT
  delay(20);
  escreveReg(REG_CTRL_HI, ctrlHi(CMD_START));  // inicia a varredura

  double f = F_INICIAL;
  double zMin = 1e30, zMax = 0.0;
  double ultimoGf = 0.0, ultimaFase = 0.0;
  uint16_t i = 0;

  while (true) {
    // Espera o DFT concluir (bit 1 do status); BTN1 cancela.
    // O chip so' amostra depois de CICLOS_ACOMODACAO ciclos DA EXCITACAO,
    // isto e' CICLOS_ACOMODACAO/f segundos — 100 ms a 1 kHz, mas 10 s a
    // 10 Hz. Um limite fixo abortaria toda frequencia abaixo de ~100 Hz,
    // por isso ele e' recalculado a cada ponto (o multiplicador D10-D9 do
    // reg. 0x8A esta' em x1; se passar a usa-lo, multiplicar aqui tambem).
    const double tDftMs = 1000.0 * 16384.0 / AD5933_MCLK_HZ;   // ~0,98 ms
    const double fEspera = (f > 0.0) ? f : 1.0;
    const uint32_t limiteMs =
        (uint32_t)(2.0 * (1000.0 * CICLOS_ACOMODACAO / fEspera + tDftMs)) + 250;
    uint32_t t0 = millis();
    while (!(leReg(REG_STATUS) & 0x02)) {
      if (botaoPressionado(BTN1_PIN)) {
        escreveReg(REG_CTRL_HI, ctrlHi(CMD_PDOWN));
        Serial.println("# Varredura cancelada (BTN1).");
        telas::erro("Cancelada (BTN1)");
        return;
      }
      if (millis() - t0 > limiteMs) {
        Serial.print("# ERRO: timeout DFT em f=");
        Serial.print(f, 2);
        Serial.print(" Hz (limite ");
        Serial.print(limiteMs);
        Serial.println(" ms)");
        telas::erro("ERRO: timeout DFT");
        return;
      }
    }

    int16_t re = leReg16(REG_REAL);
    int16_t im = leReg16(REG_IMAG);

#if MODO_CALIBRACAO
    double mag = sqrt((double)re * re + (double)im * im);
    ultimoGf   = (R_CALIBRACAO * mag > 0)
                 ? 1.0 / (R_CALIBRACAO * mag) : 0.0;
    ultimaFase = atan2((double)im, (double)re);
    Serial.print("# CAL f="); Serial.print(f, 2);
    Serial.print(" real=");   Serial.print(re);
    Serial.print(" imag=");   Serial.print(im);
    Serial.print(" mag=");    Serial.print(mag, 3);
    Serial.print(" GAIN_FACTOR="); Serial.print(ultimoGf, 10);
    Serial.print(" FASE_SISTEMA="); Serial.println(ultimaFase, 6);
    telas::ponto(i, N_PONTOS, f, mag, ultimaFase * 57.2957795);
#else
    double zr, zi;
    converteImpedancia(re, im, zr, zi);
    Serial.print("f=");   Serial.print(f, 3);
    Serial.print(" z'="); Serial.print(zr, 4);
    Serial.print(" z''=");Serial.println(zi, 4);

    double zmod = sqrt(zr * zr + zi * zi);
    double faseGraus = atan2(zi, zr) * 57.2957795;
    if (zmod > 0 && zmod < zMin) zMin = zmod;
    if (zmod > zMax) zMax = zmod;
    telas::ponto(i, N_PONTOS, f, zmod, faseGraus);
#endif

    if (leReg(REG_STATUS) & 0x04) break;    // fim da varredura

    escreveReg(REG_CTRL_HI, ctrlHi(CMD_INCR));
    f += F_INCREMENTO;
    i++;
  }

  escreveReg(REG_CTRL_HI, ctrlHi(CMD_PDOWN));
#if MODO_CALIBRACAO
  telas::calibracao(ultimoGf, ultimaFase);
#else
  telas::fimVarredura(i + 1, (zMin < 1e30) ? zMin : 0.0, zMax);
#endif
}

static void leTemperatura() {
  double tempC = leTemperaturaC();
  Serial.print("# Temperatura AD5933 = ");
  Serial.print(tempC, 2);
  Serial.println(" C");
  telas::estado(chipOk, tempC);
}

// Liga o VOUT na frequencia inicial e DEIXA ligado, para conferir os
// terminais do DUT com osciloscopio. Fora de uma varredura o AD5933 fica
// em power-down, entao medir "em repouso" da' 0 V — o que ja' confundiu
// mais de um teste de bancada.
static void ligaExcitacao() {
  configuraSweep();
  escreveReg(REG_CTRL_HI, ctrlHi(CMD_INIT));
  Serial.print("# Excitacao LIGADA em ");
  Serial.print(F_INICIAL, 2);
  Serial.print(" Hz, ");
  Serial.print(vppMv());
  Serial.println(" mVpp. Envie 'P' para desligar.");
  Serial.println("#   Multimetro comum nao le seno de 1 kHz+; use osciloscopio.");
  telas::excitacao(F_INICIAL, vppMv());
}

static void desligaExcitacao() {
  escreveReg(REG_CTRL_HI, ctrlHi(CMD_PDOWN));
  Serial.println("# Excitacao DESLIGADA.");
  mostraEstado();
}

// Interpreta "C f0=100 df=400.5 n=100 vpp=1000 pga=1 st=100".
static void processaComando(const String &linha) {
  double f0 = F_INICIAL, df = F_INCREMENTO;
  long n = N_PONTOS, vpp = 0, pga = 0, st = CICLOS_ACOMODACAO;

  int pos = 1;  // pula o 'C'
  while (pos < (int)linha.length()) {
    int eq = linha.indexOf('=', pos);
    if (eq < 0) break;
    int ini = linha.lastIndexOf(' ', eq);
    String chave = linha.substring(ini + 1, eq);
    int fim = linha.indexOf(' ', eq + 1);
    if (fim < 0) fim = linha.length();
    double valor = linha.substring(eq + 1, fim).toDouble();

    if      (chave == "f0")  f0  = valor;
    else if (chave == "df")  df  = valor;
    else if (chave == "n")   n   = (long)valor;
    else if (chave == "vpp") vpp = (long)valor;
    else if (chave == "pga") pga = (long)valor;
    else if (chave == "st")  st  = (long)valor;
    pos = fim + 1;
  }

  // A tolerancia de 5% aceita os 1000 Hz nominais do datasheet, que ficam
  // pouco abaixo do limite exato (1023,9 Hz com o clock interno). Quando o
  // clock externo entrar (fase 4), basta ajustar AD5933_MCLK_HZ que o
  // limite acompanha sozinho.
  if (f0 >= 0.95 * freqMinimaDft()) {
    F_INICIAL = f0;
  } else if (f0 > 0) {
    Serial.print("# ERRO: f0=");
    Serial.print(f0, 1);
    Serial.print(" Hz abaixo do minimo da DFT (");
    Serial.print(freqMinimaDft(), 1);
    Serial.println(" Hz). Exige clock externo mais lento no SMA P5; f0 mantido.");
  }
  if (df > 0)               F_INCREMENTO = df;
  if (n >= 2 && n <= 512)   N_PONTOS     = (uint16_t)n;
  if (st >= 1 && st <= 511) CICLOS_ACOMODACAO = (uint16_t)st;
  if      (vpp == 2000) FAIXA_SAIDA = SAIDA_2V;
  else if (vpp == 1000) FAIXA_SAIDA = SAIDA_1V;
  else if (vpp == 400)  FAIXA_SAIDA = SAIDA_400mV;
  else if (vpp == 200)  FAIXA_SAIDA = SAIDA_200mV;
  if      (pga == 1) GANHO_PGA = PGA_x1;
  else if (pga == 5) GANHO_PGA = PGA_x5;

  Serial.print("# CFG ok: f0=");  Serial.print(F_INICIAL, 3);
  Serial.print(" df=");           Serial.print(F_INCREMENTO, 6);
  Serial.print(" n=");            Serial.print(N_PONTOS);
  Serial.print(" vpp=");          Serial.print(vppMv());
  Serial.print(" pga=");          Serial.print(pgaX());
  Serial.print(" st=");           Serial.println(CICLOS_ACOMODACAO);

  double fFinal = F_INICIAL + F_INCREMENTO * (N_PONTOS - 1);
  telas::configuracao(F_INICIAL, fFinal, N_PONTOS, vppMv(), pgaX(),
                      CICLOS_ACOMODACAO);
}

// ----------------------------- SETUP ------------------------------
void setup() {
  Serial.begin(BAUD);
  pinMode(BTN1_PIN, INPUT_PULLUP);
  pinMode(BTN2_PIN, INPUT);        // input-only; pull-up externo

  telas::inicia();
  delay(900);                      // tela de abertura visivel

  Wire.begin(SDA_PIN, SCL_PIN, I2C_HZ);
  Wire.beginTransmission(ADDR);
  chipOk = (Wire.endTransmission() == 0);
  if (chipOk) {
    Serial.println("# AD5933 detectado em 0x0D. Envie 'S' para varrer, 'T' p/ temperatura.");
  } else {
    Serial.println("# ERRO: AD5933 NAO respondeu em 0x0D. Confira SDA/SCL/GND/5V.");
  }
  mostraEstado();
}

void loop() {
  if (Serial.available()) {
    String linha = Serial.readStringUntil('\n');
    linha.trim();
    if (linha.length() > 0) {
      char c = linha.charAt(0);
      if (c == 'S' || c == 's') executaVarredura();
      else if (c == 'T' || c == 't') leTemperatura();
      else if (c == 'C' || c == 'c') processaComando(linha);
      else if (c == 'V' || c == 'v') ligaExcitacao();
      else if (c == 'P' || c == 'p') desligaExcitacao();
    }
  }

  if (botaoPressionado(BTN1_PIN)) executaVarredura();
  if (botaoPressionado(BTN2_PIN)) telas::alternaBrilho();
}
