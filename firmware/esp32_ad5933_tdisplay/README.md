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

**3. A faixa de impedância é definida pelo R9, e esta placa foi
modificada.** O resistor de realimentação do amplificador de
transimpedância é o **R9** (0603, entre os pinos 4/RFB e 5/VIN do
AD5933) — o próprio fabricante documenta que ele é para o usuário trocar,
e o datasheet publica uma faixa por década (Fig. 26 a 31): RFB de 100 Ω
para 100 Ω–1 kΩ, 1 kΩ para 1–10 kΩ, 10 kΩ para 10–100 kΩ, e assim por
diante.

De fábrica o R9 é de **200 kΩ**, o que põe a placa na década de
100 kΩ–1 MΩ: qualquer DUT abaixo de ~98 kΩ satura o estágio I-V e lê
sempre o mesmo valor, sem aviso. Esta placa recebeu um **330 Ω soldado em
paralelo** com o R9 original (330 ∥ 200,4 k = 329,5 Ω; o de 200 k
contribui com 0,17 %, absorvido pela calibração), o que a levou para a
faixa de **150 Ω a 15 kΩ**. Soldar em paralelo evita retrabalhar um 0603
encostado nos pinos do AD5933, onde o risco é levantar a ilha.

Se precisar de outra faixa, o critério é `RFB ≈ Z_min` da década desejada,
e **toda troca exige recalibrar**.

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

**Já calibrado** (04/08/2026, com o R9 modificado — ver abaixo). Duas
subfaixas, selecionadas automaticamente pelo PGA que o host pedir:

| Subfaixa | Padrões usados | Cobertura | Verificação |
|----------|----------------|-----------|-------------|
| PGA ×1 | 147,6 Ω e 332,5 Ω | 150 Ω – 15 kΩ | 147,608 Ω (+0,01 %), rms 0,28 %, fase +0,66° |
| PGA ×5 | 21,92 kΩ | 1,3 kΩ – 75 kΩ | 21.925 Ω (+0,02 %), rms 0,30 %, fase +0,01° |

Enquanto `CALIBRADO` for `false` o firmware **recusa** varrer, em vez de
emitir ohms errados por ordens de grandeza com cara de medida válida.

Dois pontos do modelo merecem atenção, porque são o que separa uma
medida correta de uma apenas plausível:

**A resistência de saída do chip entra em série com a amostra.** O que a
magnitude bruta mede é `K(f)/(ROUT + |Z|)`, não `1/|Z|`. Em 220 kΩ o ROUT
pesa 0,09 % e some no ruído; em 150 Ω ele é *maior que a própria amostra*.
Por isso a subfaixa ×1 foi calibrada com **dois** padrões, resolvendo o
ROUT explicitamente: deu **230,3 Ω**, com desvio de 0,5 Ω em 99
frequências. O datasheet dá 200 Ω como *típico* — usar o valor de catálogo
teria introduzido 20 % de erro num DUT de 147 Ω. A subtração do ROUT é
**complexa** e feita depois da rotação de fase. A subfaixa ×5 precisou de
um padrão só, porque o ROUT é do chip e não depende do PGA.

**A fase do sistema não é constante.** Ela varre de 89° a 153° na banda —
um atraso de 1,77 µs (2,08 µs em ×5). Um valor único daria dezenas de
graus de erro, o que destrói qualquer diagrama de Nyquist. Por isso
`K(f)` é quadrático e `FASE(f)` linear, que é a calibração multiponto
recomendada pelo datasheet para varreduras largas.

**Refaça a calibração se trocar R9, a faixa de saída ou o clock** — os
coeficientes valem só para a combinação medida.

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
