/*
 * AMOSTRAS FRA 2.0 - exemplo de firmware para envio serial
 * ---------------------------------------------------------
 * Modelo para Arduino / ESP32 / STM32 (framework Arduino).
 *
 * Envia uma linha por ponto de medicao pela porta serial, no formato
 * reconhecido pela janela "Conexao Serial" do software:
 *
 *     frequencia,tensao,corrente,fase\n
 *
 * - Uma linha por ponto, terminada por '\n'.
 * - Valores separados por virgula (tambem aceita ';', tab ou espaco).
 * - Use ponto como separador decimal (o software tambem aceita virgula).
 *
 * No software: Ferramentas -> Conexao Serial..., selecione a porta,
 * baud 115200, formato "Frequencia, Tensao, Corrente, Fase" e conecte.
 * O |Z| = V/I e as demais colunas sao calculados automaticamente.
 *
 * Substitua a funcao medir_ponto() pela sua aquisicao real (ADC,
 * detector de fase, ganho, etc.). Os valores abaixo sao apenas um
 * exemplo (circuito RC sintetico) para testar a comunicacao.
 */

const long BAUD = 115200;

// Faixa de frequencias da varredura (Hz), em decadas.
const float F_MIN = 1.0;
const float F_MAX = 100000.0;
const int   N_PONTOS = 30;

// Parametros do circuito RC de exemplo (troque pela medicao real).
const float RS = 10.0;      // resistencia serie (ohm)
const float RP = 100.0;     // resistencia paralelo (ohm)
const float C  = 1.0e-6;    // capacitancia (F)
const float TENSAO = 1.0;   // tensao de excitacao (V)

// Calcula tensao, corrente e fase de um ponto (exemplo RC).
void medir_ponto(float f, float &v, float &i, float &fase_deg) {
  float w = 2.0 * PI * f;
  // Z = Rs + Rp / (1 + j*w*Rp*C)
  float den = 1.0 + (w * RP * C) * (w * RP * C);
  float zr = RS + RP / den;              // parte real
  float zi = -(RP * w * RP * C) / den;   // parte imaginaria
  float zmod = sqrt(zr * zr + zi * zi);
  v = TENSAO;
  i = v / zmod;                          // corrente = V / |Z|
  fase_deg = atan2(zi, zr) * 180.0 / PI; // fase de Z, em graus
}

void setup() {
  Serial.begin(BAUD);
  while (!Serial) { ; }  // aguarda a porta (placas com USB nativo)
}

void loop() {
  // Varredura logaritmica de F_MIN a F_MAX.
  for (int k = 0; k < N_PONTOS; k++) {
    float frac = (float)k / (float)(N_PONTOS - 1);
    float f = F_MIN * pow(F_MAX / F_MIN, frac);

    float v, i, fase;
    medir_ponto(f, v, i, fase);

    // Envia: frequencia,tensao,corrente,fase
    Serial.print(f, 4);
    Serial.print(',');
    Serial.print(v, 6);
    Serial.print(',');
    Serial.print(i, 8);
    Serial.print(',');
    Serial.println(fase, 4);

    delay(200);  // ritmo de envio (ajuste conforme sua aquisicao)
  }

  delay(3000);   // pausa entre varreduras
}
