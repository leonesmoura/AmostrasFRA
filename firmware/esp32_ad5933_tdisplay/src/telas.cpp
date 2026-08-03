/*
 * AMOSTRAS FRA 2.0 - Implementacao das telas (ST7735 80x160, paisagem)
 * ====================================================================
 * Layout da tela de varredura (160x80):
 *   y  0..15  cabecalho: ponto i/N e frequencia atual
 *   y 17..43  |Z| em fonte grande (destaque)
 *   y 44..59  fase (graus) e corrente estimada
 *   y 61..70  sparkline de |Z| (historico da varredura)
 *   y 73..79  barra de progresso
 */
#include "telas.h"

#include <TFT_eSPI.h>

namespace telas {

static TFT_eSPI tft;

// Historico de |Z| para o sparkline (ate 512 pontos por varredura).
static float historico[512];
static uint16_t nHistorico = 0;
static uint16_t nTotal = 0;
static int vppConfigMv = 1000;

// Backlight: canal 0 do LEDC no GPIO 4 (ativo em HIGH).
static const int BL_PIN = 4;
static const int BL_CANAL = 0;
static const uint8_t BL_NIVEIS[] = {255, 128, 50};
static uint8_t blIndice = 0;

// Cores (RGB565).
static const uint16_t COR_TITULO = TFT_CYAN;
static const uint16_t COR_TEXTO  = TFT_WHITE;
static const uint16_t COR_FRACO  = 0x8410;    // cinza medio
static const uint16_t COR_OK     = TFT_GREEN;
static const uint16_t COR_ERRO   = TFT_RED;
static const uint16_t COR_FASE   = TFT_YELLOW;
static const uint16_t COR_SPARK  = TFT_GREEN;
static const uint16_t COR_BARRA  = 0x34BF;    // azul claro

// ------------------------- formatadores ---------------------------
// Frequencia legivel: "845.2 Hz" / "45.70 kHz".
static void fmtFreq(double f, char *saida, size_t n) {
  if (f < 1000.0)      snprintf(saida, n, "%.1f Hz", f);
  else                 snprintf(saida, n, "%.2f kHz", f / 1000.0);
}

// Impedancia legivel: "834.2 ohm" / "12.35 kohm" / "1.23 Mohm".
static void fmtZ(double z, char *saida, size_t n) {
  if (z < 1000.0)            snprintf(saida, n, "%.1f ohm", z);
  else if (z < 1000000.0)    snprintf(saida, n, "%.2f kohm", z / 1e3);
  else                       snprintf(saida, n, "%.2f Mohm", z / 1e6);
}

// Corrente estimada legivel: "1.23 mA" / "45.6 uA".
static void fmtI(double iA, char *saida, size_t n) {
  double a = fabs(iA);
  if (a >= 1e-3)      snprintf(saida, n, "%.2f mA", iA * 1e3);
  else if (a >= 1e-6) snprintf(saida, n, "%.1f uA", iA * 1e6);
  else                snprintf(saida, n, "%.0f nA", iA * 1e9);
}

// --------------------------- base ---------------------------------
void inicia() {
  tft.init();
  tft.setRotation(1);            // paisagem 160x80
  tft.fillScreen(TFT_BLACK);

  // Backlight com PWM (dimming pelos botoes).
  ledcSetup(BL_CANAL, 5000, 8);
  ledcAttachPin(BL_PIN, BL_CANAL);
  ledcWrite(BL_CANAL, BL_NIVEIS[blIndice]);

  // Tela de abertura.
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(COR_TITULO, TFT_BLACK);
  tft.drawString("AMOSTRAS FRA", 80, 26, 4);
  tft.setTextColor(COR_FRACO, TFT_BLACK);
  tft.drawString("AD5933 - EIS ao vivo", 80, 52, 2);
}

void alternaBrilho() {
  blIndice = (blIndice + 1) % (sizeof(BL_NIVEIS) / sizeof(BL_NIVEIS[0]));
  ledcWrite(BL_CANAL, BL_NIVEIS[blIndice]);
}

// --------------------------- telas --------------------------------
void estado(bool chipOk, double tempC) {
  tft.fillScreen(TFT_BLACK);
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(COR_TITULO, TFT_BLACK);
  tft.drawString("AMOSTRAS FRA", 4, 2, 2);

  char linha[40];
  if (chipOk) {
    tft.setTextColor(COR_OK, TFT_BLACK);
    snprintf(linha, sizeof(linha), "AD5933 OK  %.1f C", tempC);
    tft.drawString(linha, 4, 22, 2);
  } else {
    tft.setTextColor(COR_ERRO, TFT_BLACK);
    tft.drawString("AD5933 NAO detectado!", 4, 22, 2);
    tft.setTextColor(COR_FRACO, TFT_BLACK);
    tft.drawString("Confira SDA21 SCL22 GND 5V", 4, 38, 2);
  }

  tft.setTextColor(COR_FRACO, TFT_BLACK);
  tft.drawString("PC: 115200 baud (COM)", 4, 48, 2);
  tft.setTextColor(COR_TEXTO, TFT_BLACK);
  tft.drawString("BTN1 varrer  BTN2 brilho", 4, 64, 2);
}

void configuracao(double f0, double f1, uint16_t n,
                  int vppMv, int pga, uint16_t settle) {
  vppConfigMv = vppMv;
  tft.fillScreen(TFT_BLACK);
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(COR_TITULO, TFT_BLACK);
  tft.drawString("Config recebida", 4, 2, 2);

  char a[24], b[24], linha[52];
  fmtFreq(f0, a, sizeof(a));
  fmtFreq(f1, b, sizeof(b));
  tft.setTextColor(COR_TEXTO, TFT_BLACK);
  snprintf(linha, sizeof(linha), "%s -> %s", a, b);
  tft.drawString(linha, 4, 20, 2);
  snprintf(linha, sizeof(linha), "n=%u  acomod=%u", n, settle);
  tft.drawString(linha, 4, 36, 2);
  snprintf(linha, sizeof(linha), "%d mVpp  PGA x%d", vppMv, pga);
  tft.drawString(linha, 4, 52, 2);

  tft.setTextColor(COR_FRACO, TFT_BLACK);
  tft.drawString("aguardando 'S' ou BTN1...", 4, 66, 2);
}

void iniciaVarredura(uint16_t nPontos, int vppMv) {
  nHistorico = 0;
  nTotal = (nPontos > 512) ? 512 : nPontos;
  vppConfigMv = vppMv;
  tft.fillScreen(TFT_BLACK);
  tft.drawRect(0, 73, 160, 7, COR_FRACO);   // moldura do progresso
}

void ponto(uint16_t i, uint16_t n, double f,
           double zmod, double faseGraus) {
  if (nHistorico < 512) historico[nHistorico++] = (float)zmod;

  char freqTxt[24], zTxt[24], iTxt[24], linha[56];

  // Cabecalho: i/N e frequencia.
  fmtFreq(f, freqTxt, sizeof(freqTxt));
  snprintf(linha, sizeof(linha), "%3u/%-3u  %s", i + 1, n, freqTxt);
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(COR_TEXTO, TFT_BLACK);
  tft.setTextPadding(160);
  tft.drawString(linha, 2, 0, 2);

  // |Z| em destaque.
  fmtZ(zmod, zTxt, sizeof(zTxt));
  tft.setTextColor(COR_TITULO, TFT_BLACK);
  tft.drawString(zTxt, 2, 17, 4);

  // Fase e corrente estimada (Ipp = Vpp/|Z|; rotulo "est").
  double iEst = (zmod > 0) ? (vppConfigMv / 1000.0) / zmod : 0.0;
  fmtI(iEst, iTxt, sizeof(iTxt));
  snprintf(linha, sizeof(linha), "fase %+.1f  I est %s",
           faseGraus, iTxt);
  tft.setTextColor(COR_FASE, TFT_BLACK);
  tft.drawString(linha, 2, 45, 2);
  tft.setTextPadding(0);

  // Sparkline de |Z| (min..max do historico).
  tft.fillRect(0, 61, 160, 10, TFT_BLACK);
  if (nHistorico >= 2) {
    float zMin = historico[0], zMax = historico[0];
    for (uint16_t k = 1; k < nHistorico; k++) {
      if (historico[k] < zMin) zMin = historico[k];
      if (historico[k] > zMax) zMax = historico[k];
    }
    float faixa = (zMax > zMin) ? (zMax - zMin) : 1.0f;
    for (uint16_t k = 0; k < nHistorico; k++) {
      int x = (int)((uint32_t)k * 159 / (nTotal > 1 ? nTotal - 1 : 1));
      int y = 70 - (int)((historico[k] - zMin) / faixa * 9.0f);
      tft.drawPixel(x, y, COR_SPARK);
    }
  }

  // Barra de progresso.
  int larg = (int)((uint32_t)(i + 1) * 156 / (n ? n : 1));
  tft.fillRect(2, 75, larg, 3, COR_BARRA);
}

void fimVarredura(uint16_t n, double zMin, double zMax) {
  char a[24], b[24], linha[56];
  tft.fillRect(0, 0, 160, 60, TFT_BLACK);
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(COR_OK, TFT_BLACK);
  tft.drawString("Varredura concluida", 2, 0, 2);

  fmtZ(zMin, a, sizeof(a));
  fmtZ(zMax, b, sizeof(b));
  tft.setTextColor(COR_TEXTO, TFT_BLACK);
  snprintf(linha, sizeof(linha), "%u pontos enviados", n);
  tft.drawString(linha, 2, 18, 2);
  snprintf(linha, sizeof(linha), "|Z| %s a %s", a, b);
  tft.drawString(linha, 2, 34, 2);
  tft.setTextColor(COR_FRACO, TFT_BLACK);
  tft.drawString("BTN1: nova varredura", 2, 50, 2);
}

void calibracao(double gainFactor, double faseSistema) {
  tft.fillScreen(TFT_BLACK);
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(COR_FASE, TFT_BLACK);
  tft.drawString("MODO CALIBRACAO", 4, 2, 2);
  char linha[52];
  tft.setTextColor(COR_TEXTO, TFT_BLACK);
  snprintf(linha, sizeof(linha), "GF %.4e", gainFactor);
  tft.drawString(linha, 4, 24, 2);
  snprintf(linha, sizeof(linha), "fase sist %.4f rad", faseSistema);
  tft.drawString(linha, 4, 40, 2);
  tft.setTextColor(COR_FRACO, TFT_BLACK);
  tft.drawString("anote no monitor serial", 4, 60, 2);
}

void erro(const char *mensagem) {
  tft.fillRect(0, 0, 160, 18, COR_ERRO);
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(TFT_WHITE, COR_ERRO);
  tft.drawString(mensagem, 2, 1, 2);
}

}  // namespace telas
