/*
 * AMOSTRAS FRA 2.0  -  Firmware ESP32 <-> AD5933 (placa KDT5933-013)
 * =================================================================
 * Faz a varredura de frequencia no AD5933 por I2C e envia, para o
 * AmostrasFRA, uma linha por ponto no formato ROTULADO que o software
 * ja aceita:
 *
 *      f=<Hz> z'=<ohm> z''=<ohm>\n
 *
 * (o AmostrasFRA calcula |Z|, fase e o restante a partir de z' e z'').
 *
 * -----------------------------------------------------------------
 * LIGACAO (conector P1 da placa, XH2.54 4 pinos):
 *      P1.1 = GND   -> GND do ESP32
 *      P1.2 = SCL   -> GPIO 22 (SCL_PIN)
 *      P1.3 = SDA   -> GPIO 21 (SDA_PIN)
 *      P1.4 = 5V-VIN-> 5V (VIN/5V do ESP32; a placa regula p/ 3,3 V)
 *
 * IMPORTANTE: o barramento I2C da placa opera em 3,3 V (pull-ups R3/R4
 * para DVDD=3,3 V via RT9193). O ESP32 e' 3,3 V -> ligacao DIRETA, sem
 * conversor de nivel. NAO alimente o AD5933 com 3,3 V nos pinos de I2C
 * a partir de um MCU de 5 V.
 * -----------------------------------------------------------------
 * REGISTRADORES (confirmados no driver de fabrica AD5933.c):
 *   0x0D  endereco I2C
 *   0x80/0x81 controle | 0x82-84 freq inicial | 0x85-87 incremento
 *   0x88-89 nº incrementos | 0x8A-8B ciclos de acomodacao
 *   0x8F status (bit1=DFT pronto, bit2=sweep completo)
 *   0x92-93 temperatura | 0x94-95 Real | 0x96-97 Imag
 *   Ponteiro de bloco = 0xB0 ; codigo de freq = 2^29/MCLK * f
 *
 * CLOCK: usa o oscilador INTERNO de 16,776 MHz (bom para ~1-100 kHz).
 * Para <1 kHz sera necessario injetar clock externo no SMA P5 (fase 4
 * do plano) -> ver AD5933_MCLK_HZ e o bit de clock no controle.
 * -----------------------------------------------------------------
 * USO:
 *   1) Ajuste F_INICIAL, F_INCREMENTO, N_PONTOS e o GANHO abaixo.
 *   2) Calibracao (fase 3): defina MODO_CALIBRACAO 1, meca um resistor
 *      conhecido (R_CALIBRACAO), abra o Monitor Serial 115200 e anote
 *      GAIN_FACTOR e FASE_SISTEMA impressos. Depois volte MODO_CALIBRACAO
 *      para 0 e cole esses dois valores nas constantes correspondentes.
 *   3) No AmostrasFRA: Ferramentas -> Conexao Serial..., baud 115200.
 *
 * Comandos por serial (opcional, um por linha):
 *   S  -> executa uma varredura      T -> le a temperatura do chip
 */

#include <Wire.h>
#include <math.h>

// ------------------------- CONFIGURACAO ---------------------------
static const uint8_t  SDA_PIN = 21;
static const uint8_t  SCL_PIN = 22;
static const uint32_t I2C_HZ  = 100000;      // 100k (pode ir a 400k)
static const long     BAUD    = 115200;

// Clock do AD5933 (Hz). Interno = 16,776 MHz. Se usar clock externo
// no SMA P5, coloque aqui a frequencia real do clock injetado.
static const double   AD5933_MCLK_HZ = 16776000.0;
static const bool     USAR_CLOCK_EXTERNO = false;

// Varredura (valores iniciais; configuraveis em tempo real pelo
// AmostrasFRA com o comando serial "C f0=... df=... n=... vpp=...
// pga=... st=..." — ver processaComando()).
static double   F_INICIAL    = 1000.0;   // Hz
static double   F_INCREMENTO = 1000.0;   // Hz por passo
static uint16_t N_PONTOS     = 100;      // pontos (<=512)

// Faixa de excitacao (D10:D9) e ganho do PGA (D8). Para 1 Vpp use
// SAIDA_1V. Para o bias-tee futuro, a AC de medicao sai por aqui.
enum { SAIDA_2V=0x0000, SAIDA_200mV=0x0200, SAIDA_400mV=0x0400, SAIDA_1V=0x0600 };
enum { PGA_x5=0x0000, PGA_x1=0x0100 };
static uint16_t FAIXA_SAIDA = SAIDA_1V;
static uint16_t GANHO_PGA   = PGA_x1;

// Ciclos de acomodacao antes de cada DFT (estabiliza o DUT).
static uint16_t CICLOS_ACOMODACAO = 100;

// --- Calibracao (fase 3) ---
#define MODO_CALIBRACAO 0
static const double R_CALIBRACAO = 1000.0;     // ohm, resistor conhecido
// Valores obtidos na calibracao (preencher apos rodar MODO_CALIBRACAO):
static const double GAIN_FACTOR  = 1.0;        // 1/(|Z_cal| * magnitude)
static const double FASE_SISTEMA = 0.0;        // rad, atan2(imag,real) do R_cal

// Convencao de sinal de Z'' do AmostrasFRA (Z'' < 0 p/ capacitivo).
// Se os graficos sairem espelhados, troque para true.
static const bool INVERTER_SINAL_ZII = false;

// ------------------------- REGISTRADORES --------------------------
static const uint8_t ADDR = 0x0D;
static const uint8_t REG_CTRL_HI = 0x80, REG_CTRL_LO = 0x81;
static const uint8_t REG_FSTART  = 0x82, REG_FINCR   = 0x85;
static const uint8_t REG_NINCR   = 0x88, REG_SETTLE  = 0x8A;
static const uint8_t REG_STATUS  = 0x8F, REG_TEMP    = 0x92;
static const uint8_t REG_REAL    = 0x94, REG_IMAG    = 0x96;
static const uint8_t PTR_CMD     = 0xB0;

// Nibbles de comando (D15:D12) prontos para o byte alto do controle.
static const uint8_t CMD_INIT   = 0x10;  // init com freq inicial
static const uint8_t CMD_START  = 0x20;  // inicia varredura
static const uint8_t CMD_INCR   = 0x30;  // incrementa frequencia
static const uint8_t CMD_REPEAT = 0x40;  // repete frequencia
static const uint8_t CMD_TEMP   = 0x90;  // mede temperatura
static const uint8_t CMD_PDOWN  = 0xA0;  // power-down
static const uint8_t CMD_STANDBY= 0xB0;  // standby

// ------------------------- I2C BAIXO NIVEL ------------------------
static bool escreveReg(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(ADDR);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

static uint8_t leReg(uint8_t reg) {
  // Aponta o ponteiro de endereco e le 1 byte.
  Wire.beginTransmission(ADDR);
  Wire.write(PTR_CMD);
  Wire.write(reg);
  Wire.endTransmission();
  Wire.requestFrom((int)ADDR, 1);
  return Wire.available() ? Wire.read() : 0;
}

// Le 2 bytes consecutivos (big-endian) como inteiro com sinal.
static int16_t leReg16(uint8_t reg) {
  uint8_t hi = leReg(reg);
  uint8_t lo = leReg(reg + 1);
  return (int16_t)((hi << 8) | lo);
}

// Byte alto do controle = comando | (faixa/ganho em D11:D8).
static uint8_t ctrlHi(uint8_t cmd) {
  uint16_t rangePga = (FAIXA_SAIDA | GANHO_PGA) >> 8;  // ocupa D11:D8
  return cmd | (rangePga & 0x0F);
}

// Byte baixo do controle: D4=reset, D3=clock externo.
static uint8_t ctrlLo(bool reset) {
  uint8_t v = 0;
  if (reset) v |= 0x10;                 // D4
  if (USAR_CLOCK_EXTERNO) v |= 0x08;    // D3
  return v;
}

// Codigo de 24 bits de uma frequencia (ou incremento).
static void escreveFreq(uint8_t reg, double f) {
  uint32_t code = (uint32_t)((536870912.0 / AD5933_MCLK_HZ) * f);  // 2^29
  escreveReg(reg,     (code >> 16) & 0xFF);
  escreveReg(reg + 1, (code >> 8)  & 0xFF);
  escreveReg(reg + 2,  code        & 0xFF);
}

// --------------------------- VARREDURA ----------------------------
struct Ponto { double f; int16_t re; int16_t im; };

static void configuraSweep() {
  uint16_t nIncr = (N_PONTOS > 0) ? (N_PONTOS - 1) : 0;

  escreveReg(REG_CTRL_LO, ctrlLo(true));            // reset
  escreveReg(REG_CTRL_HI, ctrlHi(CMD_STANDBY));     // standby

  escreveFreq(REG_FSTART, F_INICIAL);
  escreveFreq(REG_FINCR,  F_INCREMENTO);
  escreveReg(REG_NINCR,   (nIncr >> 8) & 0xFF);
  escreveReg(REG_NINCR+1,  nIncr       & 0xFF);
  escreveReg(REG_SETTLE,  (CICLOS_ACOMODACAO >> 8) & 0x01);  // mult x1
  escreveReg(REG_SETTLE+1, CICLOS_ACOMODACAO       & 0xFF);
  escreveReg(REG_CTRL_LO, ctrlLo(false));           // tira do reset
}

static void converteImpedancia(int16_t re, int16_t im, double &zr, double &zi) {
  double mag = sqrt((double)re * re + (double)im * im);
  double zmod = (GAIN_FACTOR > 0 && mag > 0) ? 1.0 / (GAIN_FACTOR * mag) : 0.0;
  double theta = atan2((double)im, (double)re) - FASE_SISTEMA;
  zr = zmod * cos(theta);
  zi = zmod * sin(theta);
  if (INVERTER_SINAL_ZII) zi = -zi;
}

// Roda a varredura completa, enviando cada ponto pela serial.
static void executaVarredura() {
  configuraSweep();
  escreveReg(REG_CTRL_HI, ctrlHi(CMD_INIT));   // energiza VOUT c/ freq inicial
  delay(20);                                   // acomodacao do DUT
  escreveReg(REG_CTRL_HI, ctrlHi(CMD_START));  // inicia a varredura

  double f = F_INICIAL;
  while (true) {
    // Espera o DFT concluir (bit 1 do status).
    uint32_t t0 = millis();
    while (!(leReg(REG_STATUS) & 0x02)) {
      if (millis() - t0 > 1000) { Serial.println("# ERRO: timeout DFT"); return; }
    }

    int16_t re = leReg16(REG_REAL);
    int16_t im = leReg16(REG_IMAG);

#if MODO_CALIBRACAO
    double mag = sqrt((double)re * re + (double)im * im);
    double gf  = (R_CALIBRACAO * mag > 0) ? 1.0 / (R_CALIBRACAO * mag) : 0.0;
    double fase = atan2((double)im, (double)re);
    Serial.print("# CAL f="); Serial.print(f, 2);
    Serial.print(" real=");   Serial.print(re);
    Serial.print(" imag=");   Serial.print(im);
    Serial.print(" mag=");    Serial.print(mag, 3);
    Serial.print(" GAIN_FACTOR="); Serial.print(gf, 10);
    Serial.print(" FASE_SISTEMA="); Serial.println(fase, 6);
#else
    double zr, zi;
    converteImpedancia(re, im, zr, zi);
    Serial.print("f=");   Serial.print(f, 3);
    Serial.print(" z'="); Serial.print(zr, 4);
    Serial.print(" z''=");Serial.println(zi, 4);
#endif

    // Fim da varredura? (bit 2 do status)
    if (leReg(REG_STATUS) & 0x04) break;

    escreveReg(REG_CTRL_HI, ctrlHi(CMD_INCR));   // proxima frequencia
    f += F_INCREMENTO;
  }

  escreveReg(REG_CTRL_HI, ctrlHi(CMD_PDOWN));    // economiza / silencia VOUT
}

static void leTemperatura() {
  escreveReg(REG_CTRL_HI, CMD_TEMP);
  delay(10);
  int16_t raw = leReg16(REG_TEMP);
  double tempC = (raw < 8192) ? raw / 32.0 : (raw - 16384) / 32.0;
  Serial.print("# Temperatura AD5933 = "); Serial.print(tempC, 2);
  Serial.println(" C");
}

// ----------------------------- SETUP ------------------------------
void setup() {
  Serial.begin(BAUD);
  Wire.begin(SDA_PIN, SCL_PIN, I2C_HZ);

  // Verifica presenca do chip no barramento.
  Wire.beginTransmission(ADDR);
  if (Wire.endTransmission() == 0) {
    Serial.println("# AD5933 detectado em 0x0D. Envie 'S' para varrer, 'T' p/ temperatura.");
  } else {
    Serial.println("# ERRO: AD5933 NAO respondeu em 0x0D. Confira SDA/SCL/GND/5V.");
  }
}

// Interpreta "C f0=100 df=400.5 n=100 vpp=1000 pga=1 st=100".
// vpp em mV (2000|1000|400|200); pga 1|5; st = ciclos de acomodacao.
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

  if (f0 > 0)              F_INICIAL    = f0;
  if (df > 0)              F_INCREMENTO = df;
  if (n >= 2 && n <= 512)  N_PONTOS     = (uint16_t)n;
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
  Serial.print(" vpp=");          Serial.print(
    FAIXA_SAIDA == SAIDA_2V ? 2000 : FAIXA_SAIDA == SAIDA_1V ? 1000 :
    FAIXA_SAIDA == SAIDA_400mV ? 400 : 200);
  Serial.print(" pga=");          Serial.print(GANHO_PGA == PGA_x1 ? 1 : 5);
  Serial.print(" st=");           Serial.println(CICLOS_ACOMODACAO);
}

void loop() {
  if (Serial.available()) {
    String linha = Serial.readStringUntil('\n');
    linha.trim();
    if (linha.length() == 0) return;
    char c = linha.charAt(0);
    if (c == 'S' || c == 's') executaVarredura();
    else if (c == 'T' || c == 't') leTemperatura();
    else if (c == 'C' || c == 'c') processaComando(linha);
  }
}
