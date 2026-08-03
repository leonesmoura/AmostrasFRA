# Firmware TTGO T-Display ↔ AD5933 (AMOSTRAS FRA 2.0)

Ponte entre a placa **AD5933 (kit KDT5933-013)** e o **AmostrasFRA**,
com interface local no display. Placa: **TTGO T-Display** (ESP32) com o
display original trocado por um **NFP096H-01AY (IPS 0,96", ST7735,
80×160)** — o `platformio.ini` já traz o setup validado
(`ST7735_REDTAB160x80`, sem inversão de cor; **não** use o setup TTGO
padrão).

> Para um ESP32 genérico **sem display**, use o firmware mínimo em
> `../esp32_ad5933/esp32_ad5933.ino` (Arduino IDE) — o protocolo serial
> é idêntico.

## Ligação (conector P1 da placa AD5933, XH2.54 4 pinos)

| P1 | Sinal  | T-Display |
|----|--------|-----------|
| 1  | GND    | GND       |
| 2  | SCL    | GPIO 22   |
| 3  | SDA    | GPIO 21   |
| 4  | 5V-VIN | 5V        |

O I²C da placa opera em **3,3 V** (reguladores internos) — ligação
direta, sem conversor de nível. Os GPIOs 21/22 ficam livres no header
do T-Display (o display usa 19/18/5/16/23/4; botões 0/35).

## Gravação

```console
pio run -t upload
```

Porta padrão: **COM22** (ajuste `upload_port`/`monitor_port` no
`platformio.ini` se mudar). Monitor: `pio device monitor` (115200).

## Telas

1. **Abertura/estado** — detecção do AD5933 (0x0D), temperatura do
   chip, dica dos botões;
2. **Configuração** — mostra o que o AmostrasFRA enviou pelo comando
   `C` (faixa, nº de pontos, Vpp, PGA, acomodação);
3. **Varredura** — ponto i/N, frequência, **|Z| em destaque**, fase,
   corrente **estimada** (Ipp ≈ Vpp/|Z|), *sparkline* de |Z| ao vivo e
   barra de progresso;
4. **Resumo** — pontos enviados e faixa de |Z| medida.

> O AD5933 mede **impedância** (|Z| e fase). A tensão exibida é a de
> excitação **configurada** e a corrente é **estimada** — o display as
> rotula assim de propósito.

## Botões

- **BTN1 (GPIO 0)** — inicia a varredura local; durante uma varredura,
  **cancela**;
- **BTN2 (GPIO 35)** — alterna o brilho (100% → 50% → 20%).

## Protocolo serial (115200 baud)

- `S` — executa a varredura; cada ponto sai como
  `f=<Hz> z'=<ohm> z''=<ohm>` (o formato rotulado que o AmostrasFRA
  reconhece automaticamente);
- `T` — temperatura do chip;
- `C f0=<Hz> df=<Hz> n=<pts> vpp=<mV> pga=<1|5> st=<ciclos>` —
  configuração enviada pela janela "Conexão Serial → AD5933" do
  AmostrasFRA (responde `# CFG ok: ...`).

## Calibração (fase 3 do plano)

1. Defina `MODO_CALIBRACAO 1` em `src/main.cpp` e ligue um resistor
   conhecido (`R_CALIBRACAO`, padrão 1 kΩ) no lugar do DUT;
2. Grave, rode uma varredura e anote `GAIN_FACTOR` e `FASE_SISTEMA`
   impressos no monitor serial (o display também mostra);
3. Volte `MODO_CALIBRACAO 0`, cole os dois valores nas constantes e
   regrave.

O clock interno (16,776 MHz) cobre ~1–100 kHz. Para <1 kHz será
injetado clock externo no SMA P5 (fase 4 do plano — `AD5933_MCLK_HZ` e
`USAR_CLOCK_EXTERNO`).
