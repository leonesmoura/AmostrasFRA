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
 *   B  -> lista as bandas de frequencia (uma linha por banda)
 *   B sel=<0..2>                  -> torna a banda ativa (clock + bit D3)
 *   B i=<0..2> mclk=<Hz> ext=<0|1> -> configura a banda e grava na NVS
 *   G  -> imprime a calibracao vigente (uma linha por banda e PGA)
 *   W [banda=<0..2>] pga=<1|5> ka= kb= kc= fa= fb= rout= fmin= fmax=
 *      -> grava a calibracao na NVS (assistente do AmostrasFRA)
 *   X  -> apaga a calibracao gravada e volta aos valores de fabrica
 *
 * Com "raw=1" no comando C, a varredura seguinte sai como
 *   # RAW f=<Hz> real=<int> imag=<int>
 * sem converter em ohms — e' o que alimenta o assistente de calibracao.
 *
 * Saida por ponto (formato rotulado que o AmostrasFRA ja aceita):
 *   f=<Hz> z'=<ohm> z''=<ohm>\n
 */

#include <Arduino.h>
#include <Preferences.h>
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

// ------------------- BANDAS DE FREQUENCIA (MCLK) ------------------
// Um unico MCLK cobre so' uma razao de ~97:1 (piso = MCLK/16384, teto =
// MCLK/167,76). Para varrer de 100 Hz a 100 kHz a varredura passa a ser
// feita POR BANDAS: cada banda tem o seu MCLK e a sua propria
// calibracao. O teto fica em 100 kHz de proposito — 200 kHz exigiria
// MCLK de 33,5 MHz, o dobro do maximo de 16,776 MHz do datasheet.
//
// A banda 0 usa o oscilador interno do AD5933; as demais recebem o
// clock gerado pelo proprio ESP32 em PINO_MCLK e ligam o bit D3 do
// registrador 0x81.
static const uint8_t NUM_BANDAS = 3;

struct Banda {
  double mclkHz;    // MCLK EFETIVO da banda, em Hz
  bool   externo;   // true = clock gerado pelo ESP32 (bit D3 do 0x81)
};

// constexpr (e nao const) para que os elementos possam inicializar o
// vetor mutavel abaixo em tempo de compilacao.
static constexpr Banda BANDAS_FABRICA[NUM_BANDAS] = {
  { 16776000.0, false },   // 1,02 kHz a 100 kHz  (oscilador interno)
  {  1638400.0, true  },   //  100 Hz  a 9,8 kHz
  {   163840.0, true  },   //   10 Hz  a 977 Hz
};

static Banda   bandas[NUM_BANDAS] = { BANDAS_FABRICA[0], BANDAS_FABRICA[1],
                                      BANDAS_FABRICA[2] };
static uint8_t BANDA_ATIVA = 0;

// Pino do clock externo. AJUSTAVEL: serve qualquer GPIO livre capaz de
// saida. O 26 esta' livre no T-Display (19/18/5/16/23 vao para o TFT, 4
// para o backlight, 21/22 para o I2C, 0/35 para os botoes).
static const uint8_t PINO_MCLK = 26;

// LEDC canal 2 — OBRIGATORIO. telas.cpp usa o canal 0 para o PWM do
// backlight (BL_CANAL = 0, GPIO 4) e no arduino-esp32 o timer e'
// (canal/2)%4: os canais 0 e 1 dividem o timer 0. O canal 2 cai no
// timer 1 e pode ter frequencia propria sem apagar (ou piscar) o
// display.
static const uint8_t CANAL_MCLK = 2;

// Resolucao do LEDC: o contador percorre 2^bits passos do clock de
// 80 MHz a cada periodo, entao a maior resolucao possivel para f e'
// bits = floor(log2(80e6/f)). O hardware nao passa de 14 bits nem
// trabalha com menos de 1. O duty fica em 2^(bits-1), que sao os 50 %
// de razao ciclica que o AD5933 espera no MCLK.
static int bitsLedc(double f) {
  int bits = (f > 0.0) ? (int)floor(log2(80000000.0 / f)) : 1;
  if (bits < 1)  bits = 1;
  if (bits > 14) bits = 14;
  return bits;
}

static double mclkAtual()    { return bandas[BANDA_ATIVA].mclkHz; }
static bool   clockExterno() { return bandas[BANDA_ATIVA].externo; }

// Limites uteis de uma banda: piso da DFT e teto da excitacao.
static double fminBanda(double mclk) { return mclk / 16384.0; }
static double fmaxBanda(double mclk) { return mclk / 167.76; }

// Definida adiante: precisa de ctrlLo() para reescrever o bit D3.
static void aplicaClockBanda();

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

// Pausa depois de cada ponto, so' para dar tempo de LER o display. Nao
// afeta a medida: ela entra depois do dado ja' ter sido lido e enviado.
// Uma varredura de 100 pontos de 1 a 100 kHz leva ~0,6 s, ou seja 6 ms por
// ponto — rapido demais para o olho. Configuravel por "dly=" no comando C.
static uint16_t ATRASO_PONTO_MS = 0;

// Frequencia minima util: a DFT integra 1024 amostras a MCLK/16, ou
// seja uma janela fixa de 1024*16/MCLK segundos (0,98 ms com o clock
// interno). Abaixo de MCLK/16384 nem um ciclo completo cabe na janela
// e o par real/imag deixa de ser uma medida de impedancia. Com o clock
// interno da' 1023,9 Hz, que e' o 1 kHz do datasheet; e' justamente
// esse piso que as bandas de MCLK menor derrubam ate os 100 Hz.
static double freqMinimaDft() { return fminBanda(mclkAtual()); }

// --- Calibracao (fase 3) ---
#define MODO_CALIBRACAO 0
// ATENCAO: R_CALIBRACAO tem que ser o valor REAL do padrao usado e tem
// que estar dentro da janela que o resistor de transimpedancia da placa
// (R9, 200 kohm de fabrica) permite: na pratica 220 kohm a 1 Mohm. Um
// padrao de 1 kohm satura o estagio I-V e produz um gain factor invalido
// — para medir a decada de 1 kohm e' preciso trocar R9 por ~1 kohm.
static const double R_CALIBRACAO = 147.6;   // padrao usado na ultima calibracao

// Calibracao de DOIS PONTOS, 04/08/2026: padroes de 147,6 ohm e 332,5 ohm,
// 2 a 100 kHz, 2 Vpp, PGA x1, clock interno, com o R9 ja' modificado
// (330 ohm em paralelo com os 200,4 kohm originais).
//
// MODELO. A magnitude bruta da DFT responde a' CORRENTE, e o AD5933 tem
// resistencia de saida propria em serie com a amostra:
//     mag = K(f) / (ROUT + |Z|)
// e nao mag ~ 1/|Z|. Com um unico padrao os dois efeitos se confundem e a
// resposta vira afim: o erro chega a +94 % em 150 ohm e -16 % em 15 kohm.
// Por isso a calibracao usa dois padroes e resolve o ROUT explicitamente.
// Medido: ROUT = 230,3 ohm (o datasheet da' 200 ohm como TIPICO), com
// desvio de apenas 0,5 ohm em 99 frequencias — vale a pena medir, nao supor.
//
//   K(f)    = K_A*f^2 + K_B*f + K_C       -> residuo 0,13 % rms
//   FASE(f) = FASE_A*f + FASE_B  [rad]    -> residuo 0,23 grau rms
//
// A fase do sistema NAO e' constante: vai de 89,2 a 153,2 graus na banda
// (atraso de 1,77 us). O termo constante deu 1,5718 rad = pi/2, que sao os
// 90 graus inerentes a' conversao corrente-tensao.
//
// Verificacao sobre os proprios padroes: 332,47 ohm (alvo 332,5) e
// 147,57 ohm (alvo 147,6). REFAZER se trocar R9, faixa de saida, PGA ou
// clock — os coeficientes valem so' para essa combinacao.
// DUAS SUBFAIXAS. O alvo (150 ohm a 15 kohm) e' uma razao de 100x, demais
// para uma escala so': no topo, com PGA x1, sobram ~300 contagens de 20200
// e o ruido domina. Por isso ha um jogo de coeficientes por ganho do PGA:
//   x1 -> 150 ohm a ~15 kohm   (padroes de 147,6 e 332,5 ohm)
//   x5 -> 1,3 kohm a ~75 kohm  (padrao de 21,92 kohm)
// A x5 precisou de um padrao so' porque o ROUT e' do chip e ja' estava
// determinado pela x1 — ele nao depende do PGA. Ganho efetivo medido do
// PGA: 4,858 (o nominal e' 5).
struct Calibracao {
  double ka, kb, kc;     // K(f)    = ka*f^2 + kb*f + kc
  double fa, fb;         // FASE(f) = fa*f + fb   [rad]
  double fmin, fmax;     // banda em que os coeficientes valem
};

// Valores de FABRICA (compilados). O assistente de calibracao do AmostrasFRA
// grava outros na NVS pelo comando W, e eles passam a valer sem recompilar;
// o comando X restaura estes aqui.
static const Calibracao CAL_FABRICA_X1 = {
  -1.297152392695e-05, -8.669915510008e-02,  4.683947170245e+06,
   1.114138937902e-05,  1.571832821289e+00,  2000.0, 100000.0
};
static const Calibracao CAL_FABRICA_X5 = {
  -1.690647135774e-04,  6.767157599982e+00,  2.269985074007e+07,
   1.303983672756e-05,  1.551299417715e+00,  2000.0, 100000.0
};
static const double ROUT_FABRICA = 230.3248;

// A calibracao passa a ser indexada por [banda][pga]: 3 bandas x 2
// ganhos = 6 perfis. Os coeficientes de fabrica acima sao os da BANDA 0
// (clock interno, 2 a 100 kHz); as bandas 1 e 2 nascem SEM calibracao e
// a varredura nelas e' recusada ate o assistente gravar os seus
// coeficientes. O ROUT e' do chip — nao depende de banda nem de PGA —
// entao continua um valor unico e global.
static const uint8_t IDX_X1 = 0, IDX_X5 = 1;
static uint8_t idxPga() { return (GANHO_PGA == PGA_x5) ? IDX_X5 : IDX_X1; }

static Calibracao cal[NUM_BANDAS][2];
static bool calValida[NUM_BANDAS][2];   // perfil pode virar ohms?
static bool calDeNvs[NUM_BANDAS][2];    // origem= nvs (senao firmware)
static double ROUT_OHM = ROUT_FABRICA;

// Volta bandas, perfis e ROUT aos valores de fabrica.
static void restauraFabrica() {
  for (uint8_t b = 0; b < NUM_BANDAS; b++) {
    bandas[b] = BANDAS_FABRICA[b];
    for (uint8_t p = 0; p < 2; p++) {
      cal[b][p]       = (p == IDX_X5) ? CAL_FABRICA_X5 : CAL_FABRICA_X1;
      calValida[b][p] = (b == 0);   // so' a banda 0 vem calibrada
      calDeNvs[b][p]  = false;
      if (b != 0) {
        // Sem coeficientes proprios: zera K e FASE (marca inequivoca de
        // perfil nao calibrado, ja' que o W exige kc > 0) e mostra a
        // faixa FISICA da banda em vez da faixa da banda 0.
        cal[b][p].ka = cal[b][p].kb = cal[b][p].kc = 0.0;
        cal[b][p].fa = cal[b][p].fb = 0.0;
        cal[b][p].fmin = fminBanda(bandas[b].mclkHz);
        cal[b][p].fmax = fmaxBanda(bandas[b].mclkHz);
      }
    }
  }
  BANDA_ATIVA = 0;
  ROUT_OHM    = ROUT_FABRICA;
}

// Varredura em modo bruto: emite real/imag sem converter em ohms. E' o que
// o assistente de calibracao consome — sem ele seria preciso recompilar o
// firmware so' para enxergar os numeros crus do conversor.
static bool MODO_BRUTO = false;

static const Calibracao &calAtual() { return cal[BANDA_ATIVA][idxPga()]; }
static bool calAtualValida()        { return calValida[BANDA_ATIVA][idxPga()]; }

// Fora da banda calibrada os polinomios viram extrapolacao: o argumento e'
// limitado a [fmin, fmax] para nao divergir e a varredura avisa.
static double fCalibravel(double f) {
  const Calibracao &c = calAtual();
  if (f < c.fmin) return c.fmin;
  if (f > c.fmax) return c.fmax;
  return f;
}

static double ganhoEm(double f) {
  const Calibracao &c = calAtual();
  const double x = fCalibravel(f);
  return (c.ka * x + c.kb) * x + c.kc;
}

static double faseSistemaEm(double f) {
  const Calibracao &c = calAtual();
  return c.fa * fCalibravel(f) + c.fb;
}

// ------------------- CALIBRACAO GRAVADA (NVS) ---------------------
// Cada perfil vai inteiro como blob: evita espalhar oito doubles em oito
// chaves e mantem os coeficientes coerentes entre si. As chaves da NVS
// tem no maximo 15 caracteres, dai os nomes curtos "b<banda>p<pga>"
// ("b0p1", "b0p5", "b1p1", ...). O vetor de bandas vai em "bandas" e o
// ROUT, que e' unico, em "rout".
static Preferences nvs;
static const char *NVS_ESPACO = "calad5933";

static void chaveCal(uint8_t b, uint8_t p, char *saida, size_t n) {
  snprintf(saida, n, "b%up%u", (unsigned)b,
           (unsigned)((p == IDX_X5) ? 5 : 1));
}

static void carregaCalibracao() {
  restauraFabrica();
  nvs.begin(NVS_ESPACO, true);              // somente leitura

  if (nvs.getBytesLength("bandas") == sizeof(bandas)) {
    nvs.getBytes("bandas", bandas, sizeof(bandas));
  }

  bool achouAlgum = false;
  for (uint8_t b = 0; b < NUM_BANDAS; b++) {
    for (uint8_t p = 0; p < 2; p++) {
      char k[16];
      chaveCal(b, p, k, sizeof(k));
      if (nvs.getBytesLength(k) == sizeof(Calibracao)) {
        nvs.getBytes(k, &cal[b][p], sizeof(Calibracao));
        calValida[b][p] = true;
        calDeNvs[b][p]  = true;
        achouAlgum = true;
      }
    }
  }

  // Compatibilidade: o firmware anterior nao tinha bandas e gravava
  // "x1"/"x5". Esses blobs, se ainda existirem, sao a calibracao do
  // clock interno — ou seja, da banda 0. Migra em vez de descartar: sao
  // horas de bancada com padroes de 147,6 e 332,5 ohm.
  for (uint8_t p = 0; p < 2; p++) {
    const char *antiga = (p == IDX_X5) ? "x5" : "x1";
    if (!calValida[0][p] &&
        nvs.getBytesLength(antiga) == sizeof(Calibracao)) {
      nvs.getBytes(antiga, &cal[0][p], sizeof(Calibracao));
      calValida[0][p] = true;
      calDeNvs[0][p]  = true;
      achouAlgum = true;
    }
  }

  if (achouAlgum) ROUT_OHM = nvs.getDouble("rout", ROUT_FABRICA);
  nvs.end();

  // Perfis que continuam sem calibracao acompanham a faixa fisica da
  // banda, que pode ter vindo alterada da NVS.
  for (uint8_t b = 0; b < NUM_BANDAS; b++) {
    for (uint8_t p = 0; p < 2; p++) {
      if (!calValida[b][p]) {
        cal[b][p].fmin = fminBanda(bandas[b].mclkHz);
        cal[b][p].fmax = fmaxBanda(bandas[b].mclkHz);
      }
    }
  }
}

static void imprimeCal(uint8_t b, uint8_t p) {
  // %.12g em vez de Serial.print(x, casas): os coeficientes vao de 1e-5 a
  // 1e+7 e a impressao em ponto fixo perderia os algarismos dos pequenos.
  const Calibracao &c = cal[b][p];
  char l[240];
  snprintf(l, sizeof(l),
           "# CAL banda=%u pga=%d ka=%.12g kb=%.12g kc=%.12g fa=%.12g "
           "fb=%.12g rout=%.12g fmin=%.12g fmax=%.12g origem=%s",
           (unsigned)b, (p == IDX_X5) ? 5 : 1, c.ka, c.kb, c.kc, c.fa,
           c.fb, ROUT_OHM, c.fmin, c.fmax,
           calDeNvs[b][p] ? "nvs" : "firmware");
  Serial.println(l);
}

// Extrai " chave=valor" de uma linha de comando (todo par vem precedido de
// espaco, entao " fa=" nunca casa dentro de " fmax=").
static bool valorDe(const String &linha, const char *chave, double &saida) {
  String alvo = String(" ") + chave + "=";
  int p = linha.indexOf(alvo);
  if (p < 0) return false;
  int ini = p + alvo.length();
  int fim = linha.indexOf(' ', ini);
  if (fim < 0) fim = linha.length();
  saida = linha.substring(ini, fim).toDouble();
  return true;
}

// "W [banda=<0..2>] pga=<1|5> ka=... kb=... kc=... fa=... fb=...
//    rout=... fmin=... fmax=..."
// Sem 'banda=' grava na banda ATIVA — e' o que mantem compativel o
// assistente antigo, que nao conhecia bandas.
static void gravaCalibracao(const String &linha) {
  double v;

  uint8_t b = BANDA_ATIVA;
  if (valorDe(linha, "banda", v)) {
    if (v < 0.0 || v >= (double)NUM_BANDAS) {
      Serial.println("# ERRO: W exige banda=0..2");
      return;
    }
    b = (uint8_t)v;
  }

  if (!valorDe(linha, "pga", v) || (v != 1.0 && v != 5.0)) {
    Serial.println("# ERRO: W exige pga=1 ou pga=5");
    return;
  }
  const uint8_t p = (v == 5.0) ? IDX_X5 : IDX_X1;

  Calibracao c = cal[b][p];               // chave ausente mantem o valor
  if (valorDe(linha, "ka",   v)) c.ka   = v;
  if (valorDe(linha, "kb",   v)) c.kb   = v;
  if (valorDe(linha, "kc",   v)) c.kc   = v;
  if (valorDe(linha, "fa",   v)) c.fa   = v;
  if (valorDe(linha, "fb",   v)) c.fb   = v;
  if (valorDe(linha, "fmin", v)) c.fmin = v;
  if (valorDe(linha, "fmax", v)) c.fmax = v;

  double rout = ROUT_OHM;
  if (valorDe(linha, "rout", v)) rout = v;

  if (!(c.kc > 0.0) || !(c.fmin > 0.0) || !(c.fmax > c.fmin) ||
      rout < 0.0 || rout > 100000.0) {
    Serial.println("# ERRO: coeficientes invalidos, nada gravado");
    return;
  }

  cal[b][p]       = c;
  calValida[b][p] = true;
  calDeNvs[b][p]  = true;
  ROUT_OHM        = rout;

  // Cada perfil tem a sua chave, entao nao e' mais preciso reescrever o
  // par para manter os dois coerentes: o carregador testa cada chave
  // separadamente.
  char k[16];
  chaveCal(b, p, k, sizeof(k));
  nvs.begin(NVS_ESPACO, false);
  nvs.putBytes(k, &c, sizeof(c));
  nvs.putDouble("rout", rout);
  nvs.end();

  Serial.print("# CAL gravada: banda=");
  Serial.print(b);
  Serial.print(" pga=");
  Serial.println((p == IDX_X5) ? 5 : 1);
}

static void apagaCalibracao() {
  nvs.begin(NVS_ESPACO, false);
  nvs.clear();
  nvs.end();
  restauraFabrica();       // bandas, seis perfis, ROUT e banda ativa = 0
  aplicaClockBanda();      // a banda 0 e' interna: desliga o gerador
  Serial.println("# CAL apagada: fabrica em todas as bandas, banda 0 ativa");
}

// ------------------------ BANDAS (comando B) ----------------------
static void imprimeBanda(uint8_t b) {
  char l[180];
  snprintf(l, sizeof(l),
           "# BAND i=%u mclk=%.12g ext=%d ativa=%d fmin=%.12g fmax=%.12g",
           (unsigned)b, bandas[b].mclkHz, bandas[b].externo ? 1 : 0,
           (b == BANDA_ATIVA) ? 1 : 0,
           fminBanda(bandas[b].mclkHz), fmaxBanda(bandas[b].mclkHz));
  Serial.println(l);
}

static void gravaBandas() {
  nvs.begin(NVS_ESPACO, false);
  nvs.putBytes("bandas", bandas, sizeof(bandas));
  nvs.end();
}

// "B"                            -> lista as tres bandas
// "B sel=<n>"                    -> torna a banda n ativa (clock + D3)
// "B i=<n> mclk=<Hz> ext=<0|1>"  -> configura a banda n e grava na NVS
static void processaBanda(const String &linha) {
  double v;

  if (valorDe(linha, "sel", v)) {
    if (v < 0.0 || v >= (double)NUM_BANDAS) {
      Serial.println("# ERRO: B exige sel=0..2");
      return;
    }
    BANDA_ATIVA = (uint8_t)v;
    const double antes = bandas[BANDA_ATIVA].mclkHz;
    aplicaClockBanda();
    // ledcSetup pode ter corrigido o nominal para a frequencia real do
    // divisor; se corrigiu, a NVS tem de acompanhar.
    if (bandas[BANDA_ATIVA].mclkHz != antes) gravaBandas();
    char l[140];
    snprintf(l, sizeof(l), "# BAND ativa: i=%u mclk=%.12g ext=%d",
             (unsigned)BANDA_ATIVA, bandas[BANDA_ATIVA].mclkHz,
             bandas[BANDA_ATIVA].externo ? 1 : 0);
    Serial.println(l);
    return;
  }

  if (valorDe(linha, "i", v)) {
    if (v < 0.0 || v >= (double)NUM_BANDAS) {
      Serial.println("# ERRO: B exige i=0..2");
      return;
    }
    const uint8_t b = (uint8_t)v;
    double mclk = bandas[b].mclkHz;
    bool   ext  = bandas[b].externo;
    if (valorDe(linha, "mclk", v)) mclk = v;
    if (valorDe(linha, "ext",  v)) ext  = (v != 0.0);

    // Teto do datasheet; o piso e' folgado de proposito (as bandas
    // lentas sao justamente o motivo desta mudanca).
    if (!(mclk >= 1000.0) || mclk > 16776000.0) {
      Serial.println("# ERRO: mclk fora de 1e3 a 16,776e6 Hz, nada gravado");
      return;
    }

    if (ext) {
      // Descobre o MCLK EFETIVO consultando o divisor, mesmo que a banda
      // nao seja a ativa. Programar o canal nao emite nada por si (o
      // pino so' e' ligado em aplicaClockBanda); no pior caso ha' um
      // instante de clock errado no pino, e a chamada logo abaixo
      // restaura o gerador da banda ativa.
      const double efet = ledcSetup(CANAL_MCLK, mclk, bitsLedc(mclk));
      if (!(efet > 0.0)) {
        // Gravar o nominal quando o LEDC recusou seria pior que recusar
        // o comando: o pino nao geraria nada e o eixo de frequencia
        // inteiro passaria a mentir, sem nenhum sinal de erro na medida.
        Serial.println("# ERRO: LEDC nao sintetiza esse mclk, nada gravado");
        aplicaClockBanda();      // devolve o gerador a' banda ativa
        return;
      }
      mclk = efet;
    }

    // Trocar o clock invalida FISICAMENTE os coeficientes da banda:
    // K(f) e a fase foram levantados com o MCLK antigo. Nao apago (seria
    // facil perder horas de bancada com um comando digitado errado), mas
    // aviso — senao a placa volta a emitir ohms plausiveis e errados.
    if ((mclk != bandas[b].mclkHz || ext != bandas[b].externo) &&
        (calValida[b][IDX_X1] || calValida[b][IDX_X5])) {
      Serial.print("# AVISO: banda ");
      Serial.print(b);
      Serial.println(" foi calibrada com o clock anterior - recalibre.");
    }

    bandas[b].mclkHz  = mclk;
    bandas[b].externo = ext;
    aplicaClockBanda();          // reprograma o gerador da banda ATIVA
    gravaBandas();

    // Perfis ainda nao calibrados acompanham a nova faixa fisica.
    for (uint8_t p = 0; p < 2; p++) {
      if (!calValida[b][p]) {
        cal[b][p].fmin = fminBanda(bandas[b].mclkHz);
        cal[b][p].fmax = fmaxBanda(bandas[b].mclkHz);
      }
    }

    char l[140];
    snprintf(l, sizeof(l), "# BAND ok: i=%u mclk=%.12g ext=%d",
             (unsigned)b, bandas[b].mclkHz, bandas[b].externo ? 1 : 0);
    Serial.println(l);
    return;
  }

  for (uint8_t b = 0; b < NUM_BANDAS; b++) imprimeBanda(b);
}

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
  if (clockExterno()) v |= 0x08;   // D3 = usa o clock do PINO_MCLK
  return v;
}

// A palavra de frequencia e' proporcional a 2^29/MCLK: TEM que usar o
// MCLK da banda ativa, senao todo o eixo de frequencia do espectro sai
// deslocado pelo mesmo fator.
static void escreveFreq(uint8_t reg, double f) {
  uint32_t code = (uint32_t)((536870912.0 / mclkAtual()) * f);  // 2^29
  escreveReg(reg,     (code >> 16) & 0xFF);
  escreveReg(reg + 1, (code >> 8)  & 0xFF);
  escreveReg(reg + 2,  code        & 0xFF);
}

// Programa (ou desliga) o gerador de clock da banda ativa e reescreve o
// bit D3 do registrador 0x81. Chamada em configuraSweep, no setup e ao
// trocar/configurar banda pelo comando B.
static void aplicaClockBanda() {
  Banda &bd = bandas[BANDA_ATIVA];
  if (!bd.externo) {
    // Banda interna: solta o pino para nao injetar clock em quem nao
    // pediu (e para nao deixar o LEDC preso ao GPIO).
    ledcDetachPin(PINO_MCLK);
    pinMode(PINO_MCLK, INPUT);
  } else {
    const int bits = bitsLedc(bd.mclkHz);
    // ledcSetup DEVOLVE a frequencia que o divisor consegue sintetizar,
    // que raramente e' exatamente a pedida. E' esse valor, e nao o
    // nominal, que vale como MCLK efetivo da banda.
    const double efetiva = ledcSetup(CANAL_MCLK, bd.mclkHz, bits);
    if (efetiva > 0.0) {
      bd.mclkHz = efetiva;
    } else {
      // Sem clock no pino. Continuar calculando com o nominal produziria
      // um espectro inteiro deslocado e com cara de valido — por isso o
      // erro e' gritado na serial em vez de passar despercebido.
      Serial.print("# ERRO: LEDC nao sintetizou o MCLK da banda ");
      Serial.println(BANDA_ATIVA);
    }
    ledcAttachPin(PINO_MCLK, CANAL_MCLK);
    ledcWrite(CANAL_MCLK, 1u << (bits - 1));   // 50 % de razao ciclica
  }
  if (chipOk) escreveReg(REG_CTRL_LO, ctrlLo(false));
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

  // Ponto unico por onde passam a varredura e a excitacao continua:
  // garante o gerador da banda ativa rodando ANTES de qualquer escrita
  // de frequencia, ja' que a palavra de FSTART depende do MCLK.
  aplicaClockBanda();

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

static void converteImpedancia(int16_t re, int16_t im, double f,
                               double &zr, double &zi) {
  double mag = sqrt((double)re * re + (double)im * im);
  // O que a magnitude entrega e' o modulo de (ROUT + Z), nao de Z.
  double zTotal = (mag > 0) ? ganhoEm(f) / mag : 0.0;
  double theta = atan2((double)im, (double)re) - faseSistemaEm(f);
  // O ROUT e' resistivo puro, entao sai apenas da parte real — e DEPOIS da
  // rotacao de fase, senao a subtracao cai no eixo errado.
  zr = zTotal * cos(theta) - ROUT_OHM;
  zi = zTotal * sin(theta);
  if (INVERTER_SINAL_ZII) zi = -zi;
}

static void executaVarredura() {
#if !MODO_CALIBRACAO
  // Sem calibracao os ohms sairiam errados por ordens de grandeza, com
  // toda a aparencia de medida valida — melhor recusar. A verificacao e'
  // por PERFIL: as bandas 1 e 2 saem de fabrica sem coeficientes, entao
  // nelas so' o modo bruto roda ate o assistente calibrar.
  // O modo bruto nao converte em ohms, entao nao depende de calibracao —
  // e' justamente ele que a produz.
  if (!calAtualValida() && !MODO_BRUTO) {
    Serial.print("# ERRO: banda ");
    Serial.print(BANDA_ATIVA);
    Serial.print(" (PGA x");
    Serial.print(pgaX());
    Serial.println(") sem calibracao - nao emito ohms.");
    Serial.println("#       Use o assistente de calibracao do AmostrasFRA");
    Serial.println("#       ('B sel=' escolhe a banda, 'W banda=' grava).");
    telas::erro("Banda sem calibracao");
    return;
  }
  if (!MODO_BRUTO) {
    const double fFinal = F_INICIAL + F_INCREMENTO * (N_PONTOS - 1);
    const Calibracao &c = calAtual();
    if (F_INICIAL < c.fmin || fFinal > c.fmax) {
      Serial.print("# AVISO: faixa fora da calibracao (");
      Serial.print(c.fmin, 0); Serial.print(" a ");
      Serial.print(c.fmax, 0);
      Serial.println(" Hz) - pontos fora dela usam os coeficientes da borda.");
    }
  }
#endif
  if (F_INICIAL < freqMinimaDft()) {
    Serial.print("# AVISO: f0 abaixo do minimo da DFT da banda ");
    Serial.print(BANDA_ATIVA);
    Serial.print(" (");
    Serial.print(freqMinimaDft(), 1);
    Serial.println(" Hz) - pontos baixos sem validade.");
  }
  // Teto da banda: acima de MCLK/167,76 a palavra de frequencia satura e
  // o filtro de entrada do AD5933 ja' nao acompanha.
  const double fFimVarr = F_INICIAL + F_INCREMENTO * (N_PONTOS - 1);
  if (fFimVarr > fmaxBanda(mclkAtual())) {
    Serial.print("# AVISO: f final acima do teto da banda ");
    Serial.print(BANDA_ATIVA);
    Serial.print(" (");
    Serial.print(fmaxBanda(mclkAtual()), 1);
    Serial.println(" Hz) - use 'B sel=' numa banda de MCLK maior.");
  }

  // O modo bruto e' de um tiro so': vale para esta varredura e se desarma
  // aqui, para nao sobreviver a um cancelamento ou timeout.
  const bool bruto = MODO_BRUTO;
  MODO_BRUTO = false;

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
    const double tDftMs = 1000.0 * 16384.0 / mclkAtual();   // 0,98 ms na banda 0
    const double fEspera = (f > 0.0) ? f : 1.0;
    const uint32_t limiteMs =
        (uint32_t)(2.0 * (1000.0 * CICLOS_ACOMODACAO / fEspera + tDftMs)) + 500;
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
    if (bruto) {
      // Sem conversao: o assistente de calibracao precisa dos numeros crus.
      Serial.print("# RAW f="); Serial.print(f, 3);
      Serial.print(" real=");   Serial.print(re);
      Serial.print(" imag=");   Serial.println(im);
      // No display o valor mostrado e' a magnitude em contagens, nao ohms —
      // e' o que interessa durante a calibracao (saturacao vs. sinal fraco).
      double magb = sqrt((double)re * re + (double)im * im);
      telas::ponto(i, N_PONTOS, f, magb,
                   atan2((double)im, (double)re) * 57.2957795);
    } else {
      double zr, zi;
      converteImpedancia(re, im, f, zr, zi);
      Serial.print("f=");   Serial.print(f, 3);
      Serial.print(" z'="); Serial.print(zr, 4);
      Serial.print(" z''=");Serial.println(zi, 4);

      double zmod = sqrt(zr * zr + zi * zi);
      double faseGraus = atan2(zi, zr) * 57.2957795;
      if (zmod > 0 && zmod < zMin) zMin = zmod;
      if (zmod > zMax) zMax = zmod;
      telas::ponto(i, N_PONTOS, f, zmod, faseGraus);
    }
#endif

    if (leReg(REG_STATUS) & 0x04) break;    // fim da varredura

    // Pausa de leitura: fora do laco de espera do DFT, entao nao conta
    // para o timeout nem interfere na medida. BTN1 continua cancelando.
    if (ATRASO_PONTO_MS > 0) {
      uint32_t tp = millis();
      while (millis() - tp < ATRASO_PONTO_MS) {
        if (botaoPressionado(BTN1_PIN)) {
          escreveReg(REG_CTRL_HI, ctrlHi(CMD_PDOWN));
          Serial.println("# Varredura cancelada (BTN1).");
          telas::erro("Cancelada (BTN1)");
          return;
        }
        delay(5);
      }
    }

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
  long dly = -1, raw = -1;

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
    else if (chave == "dly") dly = (long)valor;
    else if (chave == "raw") raw = (long)valor;
    pos = fim + 1;
  }

  // A tolerancia de 5% aceita os 1000 Hz nominais do datasheet, que ficam
  // pouco abaixo do limite exato (1023,9 Hz com o clock interno). O piso
  // acompanha sozinho a banda ativa: para descer abaixo dele basta
  // selecionar uma banda de MCLK menor com 'B sel='. ATENCAO A ORDEM: o
  // 'B sel=' tem que vir ANTES do 'C f0=', senao o f0 baixo e' recusado.
  if (f0 >= 0.95 * freqMinimaDft()) {
    F_INICIAL = f0;
  } else if (f0 > 0) {
    Serial.print("# ERRO: f0=");
    Serial.print(f0, 1);
    Serial.print(" Hz abaixo do minimo da DFT da banda ");
    Serial.print(BANDA_ATIVA);
    Serial.print(" (");
    Serial.print(freqMinimaDft(), 1);
    Serial.println(" Hz). Selecione outra banda com 'B sel='; f0 mantido.");
  }
  if (df > 0)               F_INCREMENTO = df;
  if (n >= 2 && n <= 512)   N_PONTOS     = (uint16_t)n;
  if (st >= 1 && st <= 511) CICLOS_ACOMODACAO = (uint16_t)st;
  if (dly >= 0 && dly <= 5000) ATRASO_PONTO_MS = (uint16_t)dly;
  if (raw >= 0) MODO_BRUTO = (raw != 0);
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
  Serial.print(" st=");           Serial.print(CICLOS_ACOMODACAO);
  Serial.print(" dly=");          Serial.println(ATRASO_PONTO_MS);

  double fFinal = F_INICIAL + F_INCREMENTO * (N_PONTOS - 1);
  telas::configuracao(F_INICIAL, fFinal, N_PONTOS, vppMv(), pgaX(),
                      CICLOS_ACOMODACAO);
}

// ----------------------------- SETUP ------------------------------
void setup() {
  Serial.begin(BAUD);
  pinMode(BTN1_PIN, INPUT_PULLUP);
  pinMode(BTN2_PIN, INPUT);        // input-only; pull-up externo

  carregaCalibracao();             // NVS tem prioridade sobre os padroes

  telas::inicia();
  delay(900);                      // tela de abertura visivel

  Wire.begin(SDA_PIN, SCL_PIN, I2C_HZ);
  Wire.beginTransmission(ADDR);
  chipOk = (Wire.endTransmission() == 0);

  // Aplica o clock da banda ativa (0 = interno por padrao) so' depois de
  // o I2C estar de pe: e' aqui que o bit D3 do 0x81 e' escrito pela
  // primeira vez. Vem depois de telas::inicia(), que ja' tomou o canal 0
  // do LEDC para o backlight — dai o MCLK usar o canal 2.
  aplicaClockBanda();
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
      else if (c == 'B' || c == 'b') processaBanda(linha);
      else if (c == 'G' || c == 'g') {
        // Seis linhas: uma por (banda, pga).
        for (uint8_t b = 0; b < NUM_BANDAS; b++) {
          imprimeCal(b, IDX_X1);
          imprimeCal(b, IDX_X5);
        }
      }
      else if (c == 'W' || c == 'w') gravaCalibracao(linha);
      else if (c == 'X' || c == 'x') apagaCalibracao();
    }
  }

  if (botaoPressionado(BTN1_PIN)) executaVarredura();
  if (botaoPressionado(BTN2_PIN)) telas::alternaBrilho();
}
