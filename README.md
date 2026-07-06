# AMOSTRAS FRA 2.0

Software científico de **Espectroscopia de Impedância (EIS/FRA)** para
detecção e classificação de falhas em módulos fotovoltaicos, desenvolvido
para uso em dissertação de mestrado. Interface e fluxo de trabalho
inspirados nos softwares Metrohm NOVA, ZView e EC-Lab.

> Software sem fins lucrativos, desenvolvido pelo
> **Eng. Leones Moura dos Santos**.

## Recursos

- **Entrada de dados tipo Excel** diretamente na interface (QTableWidget):
  - Digitação manual;
  - Colagem com **Ctrl+V** a partir do Excel, do Metrohm NOVA ou de
    arquivos TXT, com detecção automática de delimitadores (tabulação,
    vírgula, ponto e vírgula, espaços) e de vírgula decimal;
  - Botão **Importar** para arquivos CSV, TXT, XLSX e ODS. Arquivos
    que contêm várias medições identificadas por uma coluna de nome
    (``Medição``, gerada pela exportação CSV/Excel do próprio
    software) são reconhecidos: o programa pergunta se deve recriar
    cada medição separadamente na lista lateral, restaurando a sessão
    como estava;
  - Colunas: `Frequência (Hz)`, `Z' (Ω)`, `-Z'' (Ω)`, `|Z| (Ω)`,
    `Fase (°)`, `Tensão (V)` e `Corrente (A)` — as colunas ausentes são
    calculadas automaticamente em cascata: `Tensão` e `Corrente` geram
    `|Z| = V/I`; com a `Fase`, `Z'` e `-Z''` também são calculados;
  - Colagens com linha de cabeçalho têm as colunas reconhecidas
    automaticamente (inclusive tensão/corrente); sem cabeçalho, o
    formato posicional é escolhido no seletor "Colar sem cabeçalho
    como:" (Z', |Z|/Fase ou Tensão/Corrente/Fase).
- **Múltiplas medições** em lista lateral com caixas de seleção
  (ex.: `FRA0F`, `FRA1F`, `3 pancadas`, `5 pancadas`, …), com carregar,
  renomear, duplicar e remover.
- **Gráficos** em abas, com zoom, pan, salvamento de imagem, grade,
  legendas e cursor de dados. O dock **"Estilo dos gráficos"** permite
  personalizar marcador, espessura, estilo de linha e **cores** (fundo
  da figura, fundo do gráfico, grade e texto/eixos), com preset de
  fundo claro para publicação; a **cor de cada curva** é escolhida
  selecionando a medição na lista e usando **"Cor da curva…"**:
  - **Nyquist** (`Z'` × `-Z''`, aspecto igual, marcadores e espessura
    configuráveis, cores automáticas);
  - **Bode Magnitude** (`|Z|` × f, log-log) e **Bode Fase** (fase × f,
    semilog);
  - **Kramers-Kronig**, **Circuito Equivalente** e **Comparação**.
- **Correção do instrumento** com **biblioteca de correções nomeadas**:
  janela própria onde se cadastram várias correções (uma por
  instrumento/resistor padrão), cada uma com nome, resistência nominal e
  os dados de frequência/magnitude/fase. Calcula a impedância complexa e
  a função de transferência `H(f) = Z_med / R_nominal` e aplica
  `Z_corr = Z_med / H(f)`. Ao corrigir, escolhe-se **qual** correção
  aplicar às medições marcadas — assim, amostras medidas com um
  instrumento que não precisa de correção ficam sem correção, enquanto
  outras recebem a correção adequada (NumPy vetorizado, interpolação em
  log-frequência).
- **Validação de Kramers-Kronig** com todas as frequências medidas
  (nenhuma é eliminada), Valor Principal de Cauchy tratado analiticamente
  (singularidade removível via L'Hôpital), reconstrução das partes real e
  imaginária e métricas: RMSE, erro médio, erro máximo e erro percentual.
- **Ajuste de circuito equivalente** com `impedance.py` (mínimos quadrados
  não lineares, ponderação pelo módulo):
  - Modelos prontos: Randles, Randles + CPE, Randles + Warburg e
    Randles + CPE + Warburg;
  - **Editor de circuito livre** (estilo NOVA 2/ZView): monte qualquer
    circuito em série/paralelo com os elementos R, C, L, CPE,
    W (Warburg semi-infinito), Wo ("O", Warburg finito aberto),
    Ws ("T", Warburg finito curto), Gerischer (G/Gs), La, Zarc, TLMQ,
    K e eletrodo poroso (T de Paasch) — com desenho esquemático do
    circuito, string na sintaxe do `impedance.py` e estimativas
    iniciais editáveis (sugeridas automaticamente a partir do
    espectro);
  - Resultados: parâmetros com incertezas (1σ), χ², χ² reduzido,
    RMSE e R²; os valores ajustados aparecem sob cada elemento no
    desenho do circuito.
- **Curva I-V do módulo** (aba "Curva I-V"): tipo de entrada dedicado,
  apenas com tensão e corrente (a potência ``P = V·I`` é calculada
  automaticamente). Suporta digitação, colagem e importação
  (CSV/TXT/XLSX/ODS, com reconhecimento dos cabeçalhos de tensão e
  corrente em qualquer ordem), múltiplas curvas em lista com caixas de
  seleção, gráfico I×V com P×V no eixo direito e marcação do ponto de
  máxima potência, parâmetros extraídos automaticamente (Isc, Voc,
  Pmáx, Vmp, Imp e fator de forma FF) e exportação para Excel.
- **Criador de gráficos** (Ferramentas → Criador de gráficos…):
  janelas independentes para compor gráficos de publicação com
  qualquer quantidade de medições (ex.: ganho e fase de Bode de 30
  amostras) — fontes de dados EIS (Bode completo/|Z|/fase e Nyquist)
  e curva I-V (I×V, P×V e painel duplo I×V + P×V), cores de fundo
  (figura/gráfico/grade/texto) com preset claro, cor por curva (duplo
  clique na lista), paletas de cor
  (viridis, plasma, tab20, ...), título/rótulos/escala/grade/legenda
  configuráveis (inclusive legenda externa com colunas) e **zoom de
  destaque (inset)** com seleção da região por arrasto do mouse e
  linhas de indicação; exportação em PNG/PDF/SVG.
- A simulação oferece **4 tecnologias de módulo** — silício tipo p
  (PERC/Al-BSF), silício tipo n (TOPCon, com fluxo de portadores
  invertido: lacunas coletadas na frente e elétrons no contato
  traseiro), perovskita (TCO/ETL/absorvedor/HTL/Au, sem fingers) e
  CdTe (filme fino) — e uma aba com o **modelo atômico do silício**:
  rede cristalina com ligações covalentes animadas, fósforo doador
  (elétron livre) e boro aceitador (lacuna saltando entre ligações).
- **Simulação do módulo fotovoltaico** (Ferramentas → Simulação do
  módulo FV…): animação didática do corte do módulo (vidro, EVA,
  emissor n⁺, base p, contato traseiro, EVA, backsheet) com fingers e
  busbar, fótons gerando pares elétron-lacuna e elétrons percorrendo o
  circuito externo, com a correspondência física ↔ circuito
  equivalente (fótons → I_ph; junção p-n → D ∥ C ∥ Rp; metalização e
  cabos → Rs), controles de irradiância, velocidade e pausa e medidor
  de corrente.
- **Exportação**: PNG, PDF, SVG (figuras), Excel (planilhas por medição +
  resumo + ajustes + métricas KK), CSV e **relatório PDF completo**
  (resumo, tabela de parâmetros, Nyquist, Bode, Kramers-Kronig, circuito
  equivalente e observações).

## Instalação

Requer **Python 3.11 ou 3.12** (Windows, Linux ou macOS).

```console
pip install -r requirements.txt
```

## Execução

```console
python AmostrasFRA.py
```

## Fluxo de trabalho típico

1. Na aba **Dados**, cole (Ctrl+V) ou importe o espectro de impedância.
2. Clique em **Adicionar como medição** e dê um nome (ex.: `FRA0F`).
3. Repita para as demais medições (ex.: `3 pancadas`, `5 pancadas`, …).
4. Marque as medições desejadas na lista lateral — os diagramas de
   Nyquist e Bode são atualizados automaticamente.
5. (Opcional) Configure **Análise → Correção do Instrumento…** com os
   dados do resistor padrão e aplique a correção às medições marcadas.
6. Valide a consistência dos dados na aba **Kramers-Kronig**.
7. Ajuste um circuito equivalente na aba **Circuito Equivalente**.
8. Compare medições na aba **Comparação**.
9. Exporte os resultados em **Arquivo → Exportar** (Excel, CSV, imagem ou
   relatório PDF).

## Estrutura do projeto

| Arquivo           | Conteúdo                                             |
| ----------------- | ---------------------------------------------------- |
| `AmostrasFRA.py`  | Ponto de entrada da aplicação                        |
| `gui.py`          | Janela principal, tabela de dados, docks e diálogos  |
| `plots.py`        | Canvas Matplotlib/Qt, temas, cursores e gráficos     |
| `kk.py`           | Validação de Kramers-Kronig (PV de Cauchy)           |
| `correcao.py`     | Correção do instrumento (resistor padrão, `H(f)`)    |
| `circuitos.py`    | Modelos e ajuste de circuitos equivalentes           |
| `exportacao.py`   | Exportação de imagens, Excel, CSV e relatório PDF    |
| `graficos.py`     | Criador de gráficos com zoom de destaque (inset)     |
| `simulacao.py`    | Simulação animada do módulo FV (camadas e elétrons)  |
| `util.py`         | Medições, parsing de dados, importação e logging     |

## Compilação com PyInstaller

```console
pip install pyinstaller
pyinstaller --noconfirm --windowed --name AmostrasFRA AmostrasFRA.py
```

O executável é gerado em `dist/AmostrasFRA/`. Para um único arquivo:

```console
pyinstaller --noconfirm --windowed --onefile --name AmostrasFRA AmostrasFRA.py
```

## Notas técnicas

- **Convenção de sinais**: internamente `Z = Z' + jZ''`; a tabela e o
  diagrama de Nyquist exibem `-Z''` (positivo para sistemas capacitivos).
  A fase é a de `Z` (negativa para sistemas capacitivos).
- **Kramers-Kronig**: como o espectro medido é finito (a integral teórica
  vai de 0 a ∞), o nível `R∞` é ajustado por mínimos quadrados e os
  resíduos podem crescer nas extremidades da faixa de frequência — um
  comportamento esperado da transformada em janela finita.
- **Logs**: gravados em `~/.amostras_fra/amostras_fra.log`.
