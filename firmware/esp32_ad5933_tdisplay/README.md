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
  AmostrasFRA (responde `# CFG ok: ...`);
- `V` — liga a excitação **contínua** na frequência inicial e deixa
  ligada, para conferir os terminais do DUT no osciloscópio;
- `P` — desliga a excitação.

Linhas iniciadas por `#` são mensagens de diagnóstico e o parser do
AmostrasFRA as ignora.

## Limites reais da placa (medidos no esquemático e no datasheet)

Três limites explicam quase todo problema de bancada. Vale ler antes de
suspeitar do firmware.

**1. Frequência mínima ≈ 1 kHz com o clock interno.** A DFT integra 1024
amostras a MCLK/16, ou seja uma janela **fixa** de 0,98 ms. Abaixo de
MCLK/16384 = 1023,9 Hz não cabe nem um ciclo da excitação na janela e o
par real/imaginário deixa de ser uma medida. Pedir 10 Hz não dá erro de
conta: dá dado sem sentido — por isso o firmware **recusa** `f0` abaixo
desse limite e avisa. Para descer de verdade, injete um clock mais lento
no SMA **P5** (≈164 kHz para chegar a 10 Hz), ajuste `AD5933_MCLK_HZ` e
`USAR_CLOCK_EXTERNO` em `src/main.cpp` — o limite acompanha sozinho.

**2. Tempo por ponto cresce com 1/f.** A acomodação é contada em
**ciclos da excitação**: 100 ciclos são 100 ms a 1 kHz, mas 10 s a 10 Hz.
O timeout do firmware é calculado ponto a ponto a partir de `f` e de
`CICLOS_ACOMODACAO` — não o troque por um valor fixo. Em frequências
muito baixas, reduza a "Acomodação" na janela do AmostrasFRA.

**3. Faixa de impedância: ~150 kΩ a 10 MΩ como a placa vem de fábrica.**
O resistor de realimentação do amplificador de transimpedância é **R9 =
200 kΩ** (0603, entre os pinos 4/RFB e 5/VIN do AD5933) — o próprio
fabricante documenta que ele é para o usuário trocar. Com 200 kΩ, um DUT
de **1 kΩ satura o estágio I-V** e nenhuma calibração recupera o valor.
Para medir a década de 1 kΩ, troque R9 por 1 kΩ–1,5 kΩ (a janela útil
passa a ~0,5–10 kΩ e a placa deixa de medir alta impedância). Calibre
sempre com um padrão **dentro** da janela do R9 instalado — é o que
`R_CALIBRACAO` em `src/main.cpp` espera.

## Jumpers P2 e P7 — sem eles o DUT fica desligado

No esquemático **não existe cobre** entre o VOUT do AD5933 e o borne do
DUT: o caminho passa obrigatoriamente por dois headers 2x2.

| Caminho | Jumpers | Uso |
|---------|---------|-----|
| Direto | P2 pinos 1-2 **e** P7 pinos 1-2 | 1 kΩ – 10 MΩ (padrão) |
| Amplificado (AD820) | P2 pinos 3-4 **e** P7 pinos 3-4 | abaixo de 1 kΩ |

Os dois headers têm que estar no **mesmo par**. Jumper faltando, ou um
em cada fileira, deixa o terminal do DUT flutuando — e o multímetro lê
0 V em qualquer situação. O DUT vai entre **P6.1** (excitação, mesmo nó
do SMA P4) e **P6.2** (entrada de corrente, que vai a VIN); ligar o DUT
contra o GND não produz leitura válida.

Em repouso o VOUT fica **desligado** (power-down), então medir fora de
uma varredura dá 0 V mesmo com tudo certo — use o comando `V` para
energizar e medir com calma.

## Calibração (fase 3 do plano)

**Já calibrado** (04/08/2026, padrão de 220 kΩ, 2–100 kHz, 2 Vpp, PGA ×1,
clock interno). Verificação com o próprio padrão: |Z| médio **220.056 Ω**
(+0,03 %), erro rms 0,17 %, fase média **+0,03°** (rms 0,21°). Enquanto
`CALIBRADO` for `false` o firmware **recusa** varrer, em vez de emitir
ohms errados por ordens de grandeza com cara de medida válida.

A calibração usa **polinômios em frequência**, não constantes: a fase do
sistema anda de 89,5° a 160,8° na banda (atraso de ~1,96 µs do caminho
analógico mais a DFT). Um valor único daria ±36° de erro de fase, o que
destrói qualquer diagrama de Nyquist. `GF(f)` é quadrático e `FASE(f)`
linear — é a calibração multiponto que o datasheet recomenda para
varreduras largas. **Refaça a calibração se trocar R9, a faixa de saída,
o PGA ou o clock**, porque os coeficientes dependem dos quatro.

1. Defina `MODO_CALIBRACAO 1` em `src/main.cpp` e ligue um resistor
   conhecido no lugar do DUT, **dentro da janela do R9 instalado**
   (220 kΩ a 1 MΩ com o R9 de fábrica); ajuste `R_CALIBRACAO` para o
   valor real desse resistor;
2. Grave, rode uma varredura **na mesma faixa de frequência, Vpp e PGA
   que serão usados na medida** — a calibração depende dos três. Cada
   ponto sai como `# CAL f=... real=... imag=... mag=...`;
3. Ajuste os coeficientes: `GF(f)` é o ajuste quadrático de
   `1/(R_CALIBRACAO·mag)` contra `f`, e `FASE(f)` o ajuste linear de
   `atan2(imag, real)` desenrolado contra `f`. Confira as magnitudes: se
   passarem de ~30.000 contagens o estágio I-V está saturando (padrão
   pequeno demais para o R9), e se ficarem perto de zero o caminho até o
   DUT está aberto — quase sempre jumper de P2/P7;
4. Volte `MODO_CALIBRACAO 0`, cole os cinco coeficientes, ajuste
   `F_CAL_MIN`/`F_CAL_MAX` para a banda usada e regrave.
