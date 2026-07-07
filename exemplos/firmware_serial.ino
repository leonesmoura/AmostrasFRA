/*
 * AMOSTRAS FRA 2.0 - exemplo de firmware para envio serial
 * ---------------------------------------------------------
 * Modelo para Arduino / ESP32 / STM32 (framework Arduino).
 *
 * Envia uma linha por ponto de medicao (uma frequencia por linha)
 * pela porta serial. O software aceita DOIS formatos:
 *
 *   1) Posicional:  frequencia,tensao,corrente,fase\n
 *      Ex.:  10000,10.2,0.00012,-80.2
 *
 *   2) Rotulado (auto-descritivo, ordem livre):
 *          f=10000 V=10.2 I=0.00012 pha=-80.2\n
 *      Rotulos: f/freq, V/tensao, I/corrente, pha/fase, |z|, z', z''.
 *
 * - Uma linha por ponto, terminada por '\n'.
 * - Separadores: virgula, ';', tab ou espaco. Decimal com '.' ou ','.
 * - Um marcador inicial (#, $, >) e ignorado.
 *
 * Este exemplo usa o formato ROTULADO (recomendado: nao depende da
 * ordem). No software: Ferramentas -> Conexao Serial..., selecione a
 * porta, baud 115200 e conecte. O |Z| = V/I e as demais colunas sao
 * calculados automaticamente.
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

    // Envia (formato rotulado): f=... V=... I=... pha=...
    Serial.print("f=");
    Serial.print(f, 4);
    Serial.print(" V=");
    Serial.print(v, 6);
    Serial.print(" I=");
    Serial.print(i, 8);
    Serial.print(" pha=");
    Serial.println(fase, 4);

    delay(200);  // ritmo de envio (ajuste conforme sua aquisicao)
  }

  delay(3000);   // pausa entre varreduras
}
