"""Guia do usuário (AMOSTRAS FRA 2.0).

Janela de ajuda completa, acessível pelo menu Ajuda → Guia do usuário
ou pela tecla padrão F1.  À esquerda, uma árvore de tópicos; à
direita, o conteúdo em HTML com capturas de tela do próprio programa
(``assets/ajuda/*.png``, geradas por ``assets/gerar_ajuda.py``).

O conteúdo cobre todas as abas, menus, docks e janelas do software,
na ordem típica de uso: entrada de dados → visualização → validação →
ajuste → exportação.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import util


def _img(name: str, width: int = 640) -> str:
    """HTML de uma captura de tela do guia (se o arquivo existir).

    A imagem é exibida no tamanho natural do arquivo (que já é gerado
    na largura do guia, com filtro suave — reescalar no HTML borra).
    Clicar na imagem abre a versão em resolução original
    (``<nome>_full.png``) no visualizador do sistema.

    Args:
        name: Nome do arquivo em ``assets/ajuda`` (ex.: ``"dados.png"``).
        width: Ignorado (mantido por compatibilidade das chamadas).

    Returns:
        Tag ``<img>`` centralizada e clicável, ou string vazia se a
        imagem não existir (o guia continua funcional sem as figuras).
    """
    path = Path(util.resource_path(f"assets/ajuda/{name}"))
    if not path.is_file():
        return ""
    full = path.with_name(f"{path.stem}_full{path.suffix}")
    target = full if full.is_file() else path
    return (
        f'<p style="text-align:center;">'
        f'<a href="{target.as_uri()}"><img src="{path.as_uri()}"/></a>'
        f'<br><span style="color:#888888; font-size:11px;">'
        f'(clique na imagem para ampliar)</span></p>'
    )


# ---------------------------------------------------------------------------
# Conteúdo do guia: lista de (id, título, html, id_do_pai). Subtópicos
# usam o id do tópico principal como pai para montar a árvore.
# ---------------------------------------------------------------------------
def _sections() -> list[tuple[str, str, str, Optional[str]]]:
    """Monta as seções do guia: (id, título, html, id_do_pai)."""
    s: list[tuple[str, str, str, Optional[str]]] = []

    # -- Visão geral -------------------------------------------------------
    s.append(("visao", "Visão geral", f"""
<h1>AMOSTRAS FRA 2.0 — Guia do usuário</h1>
<p>O AMOSTRAS FRA é um software de <b>Espectroscopia de Impedância
Eletroquímica (EIS/FRA)</b> voltado à detecção e classificação de
falhas em módulos fotovoltaicos. Ele importa, visualiza, valida e
ajusta espectros de impedância, além de curvas I-V dos módulos.</p>
{_img("principal.png", 720)}
<p>A janela principal tem três regiões:</p>
<ul>
<li><b>Dock "Amostras"</b> (esquerda): lista de medições; a caixa de
seleção de cada uma define o que aparece nos gráficos.</li>
<li><b>Abas centrais</b>: Dados, Curva I-V, Nyquist, Bode Magnitude,
Bode Fase, Kramers-Kronig, Circuito Equivalente, Comparação e
Parâmetros.</li>
<li><b>Dock "Opções de gráfico"</b> (direita): estilo dos gráficos
(marcador, linha, grade, cores de fundo e por curva).</li>
</ul>
<p><b>Fluxo típico:</b> importar dados (ou receber pela serial) →
criar medições → conferir Nyquist/Bode → validar por Kramers-Kronig →
corrigir o instrumento (se necessário) → ajustar circuito equivalente
e/ou modelo de diodo → comparar amostras → exportar/salvar projeto.</p>
<p><b>Convenção de sinais:</b> o programa usa a coluna −Z'' (parte
imaginária com sinal trocado); em capacitivos, o semicírculo de
Nyquist aparece <i>acima</i> do eixo, como nos livros de EIS.</p>
""", None))

    # -- Primeiros passos --------------------------------------------------
    s.append(("passos", "Primeiros passos (tutorial)", """
<h1>Primeiros passos — do arquivo ao ajuste em 8 passos</h1>
<p>Um roteiro completo com uma medição típica:</p>
<ol>
<li><b>Importe o espectro</b> — aba <b>Dados</b> → "Importar…" e
escolha o CSV/Excel do seu instrumento (ou cole com Ctrl+V direto do
Excel). Confira se as colunas foram reconhecidas.</li>
<li><b>Crie a medição</b> — clique em "Adicionar como medição" e dê
um nome (ex.: <code>FRA0F</code>). Ela aparece no dock
<b>Amostras</b>, já marcada.</li>
<li><b>Veja os gráficos</b> — abas <b>Nyquist</b> e <b>Bode</b>.
Repita os passos 1–2 para as demais amostras; marque/desmarque as
caixas para compará-las.</li>
<li><b>Valide o espectro</b> — aba <b>Kramers-Kronig</b> →
"Validar Kramers-Kronig". Resíduos aleatórios dentro de ±1–2%?
Dados bons. Forma sistemática? Desconfie (deriva, ruído,
não-linearidade) e considere repetir a medição.</li>
<li><b>Corrija o instrumento</b> (se você tem a medição de um
resistor padrão) — menu <b>Análise → Correção do Instrumento</b>.
Duplique a medição antes de aplicar, para manter a original.</li>
<li><b>Ajuste o circuito equivalente</b> — aba <b>Circuito
Equivalente</b>: escolha um modelo (ou monte no editor), clique em
"Ajustar circuito" e avalie R², χ² e a sobreposição no gráfico.</li>
<li><b>Curva I-V</b> (opcional) — importe na aba <b>Curva I-V</b>,
associe à medição FRA e rode "Ajustar modelo de diodo…" para obter
os 5 parâmetros elétricos do módulo.</li>
<li><b>Veja a degradação</b> — aba <b>Parâmetros</b>: informe o
número de pancadas de cada amostra e plote R<sub>s</sub>,
R<sub>p</sub> etc. em função dele, com barras de erro. É o gráfico
de resultado do trabalho.</li>
<li><b>Salve o projeto</b> — <b>Arquivo → Salvar projeto…</b>
(<code>.fra</code>). Amanhã, "Abrir projeto…" devolve tudo:
medições, correções, ajustes, o número de pancadas, cores e
marcações.</li>
</ol>
<p>Para gerar figuras de artigo ao final: dock Opções → "Fundo claro
(publicação)" e <b>Ferramentas → Criador de gráficos…</b> (com zoom
de destaque). Para registrar o ensaio: <b>Arquivo → Exportar →
Relatório PDF</b>.</p>
""", None))

    # -- Aba Dados ---------------------------------------------------------
    s.append(("dados", "Aba Dados", f"""
<h1>Aba Dados</h1>
{_img("dados.png", 720)}
<p>É a porta de entrada dos espectros. A tabela tem 7 colunas
canônicas: <b>Frequência (Hz), Z' (Ω), −Z'' (Ω), |Z| (Ω), Fase (°),
Tensão (V) e Corrente (A)</b>. Não é preciso preencher todas: o
programa completa o que puder (ex.: de Z' e −Z'' ele calcula |Z| e
fase, e vice-versa).</p>
<h2>Botões</h2>
<ul>
<li><b>Importar…</b> — abre arquivo CSV, TXT, Excel (.xlsx/.xls) ou
ODS. O separador (vírgula, ponto e vírgula, tabulação) e a vírgula
decimal são detectados automaticamente; os nomes de coluna são
reconhecidos por sinônimos (f, freq, Z', Zre, Zimag, fase, etc.).
Um CSV exportado pelo próprio programa traz todas as medições e
curvas I-V de uma vez.</li>
<li><b>Adicionar linhas</b> — acrescenta 20 linhas vazias para
digitação manual.</li>
<li><b>Limpar tabela</b> — esvazia a tabela (as medições já criadas
não são afetadas).</li>
<li><b>Adicionar como medição</b> — transforma o conteúdo da tabela
em uma medição nomeada (ex.: FRA0F), que vai para o dock Amostras.</li>
<li><b>Atualizar medição selecionada</b> — regrava a medição
selecionada no dock com o conteúdo atual da tabela.</li>
</ul>
<p>Também é possível <b>colar</b> dados direto do Excel
(Ctrl+V ou menu Editar → Colar na tabela).</p>
""", None))

    # -- Aba Curva I-V -----------------------------------------------------
    s.append(("iv", "Aba Curva I-V", f"""
<h1>Aba Curva I-V</h1>
{_img("curva_iv.png", 720)}
<p>Recebe as curvas corrente-tensão dos módulos, medidas no
simulador solar ou traçador. A tabela tem colunas <b>Tensão (V)</b> e
<b>Corrente (A)</b>.</p>
<h2>Botões</h2>
<ul>
<li><b>Importar…</b> — aceita dois formatos: (a) duas colunas V/I;
(b) <b>matriz multi-curva</b>, em que a 1ª coluna é a tensão e cada
coluna seguinte é a corrente de uma amostra (o cabeçalho vira o nome
da curva).</li>
<li><b>Adicionar linhas / Limpar tabela</b> — como na aba Dados.</li>
<li><b>Adicionar como curva I-V</b> — cria uma curva nomeada.</li>
<li><b>Atualizar curva selecionada</b> — regrava a curva escolhida
com o conteúdo da tabela.</li>
<li><b>Carregar curva na tabela</b> — traz a curva selecionada de
volta para edição.</li>
<li><b>Associar curvas I-V…</b> — vincula cada curva a uma medição
FRA (o botão "Associar por nome" tenta casar automaticamente pelos
nomes). A associação é usada na aba Comparação e nos relatórios.</li>
<li><b>Ajustar modelo de diodo…</b> — abre a janela de ajuste do
modelo de diodo único (ver tópico específico).</li>
<li><b>Exportar Excel…</b> — salva as curvas em planilha.</li>
</ul>
""", None))

    # -- Ajuste de diodo ---------------------------------------------------
    s.append(("diodo", "Ajuste do modelo de diodo", f"""
<h1>Ajuste do modelo de diodo único</h1>
{_img("diodo.png", 700)}
<p>Ajusta a curva I-V medida ao <b>modelo de diodo único de 5
parâmetros</b>:</p>
<p style="text-align:center;"><i>I = I<sub>L</sub> −
I₀[exp((V + I·R<sub>s</sub>)/a) − 1] −
(V + I·R<sub>s</sub>)/R<sub>p</sub></i></p>
<ul>
<li><b>I<sub>L</sub></b> — corrente fotogerada (A);</li>
<li><b>I₀</b> — corrente de saturação do diodo (A);</li>
<li><b>R<sub>s</sub></b> — resistência série (Ω);</li>
<li><b>R<sub>p</sub></b> — resistência paralela/shunt (Ω);</li>
<li><b>a = n·N<sub>s</sub>·V<sub>t</sub></b> — fator de idealidade
modificado (V).</li>
</ul>
<p>Informe o <b>número de células em série</b> e a <b>temperatura</b>
para o programa converter <i>a</i> no fator de idealidade <i>n</i>.
O painel "Qualidade do ajuste" mostra R², RMSE e os pontos
característicos (Isc, Voc, Pmp).</p>
<ul>
<li><b>Ajustar</b> — ajusta a curva selecionada no seletor.</li>
<li><b>Ajustar todas…</b> — ajusta todas as curvas em sequência.</li>
<li>Ao <b>trocar a curva no seletor</b>, o gráfico e os parâmetros
atualizam automaticamente (o resultado fica em cache; se os dados da
curva mudarem, o ajuste é refeito).</li>
</ul>
<p><b>Atenção:</b> a partir de uma única curva I-V os parâmetros
R<sub>s</sub>, R<sub>p</sub> e <i>a</i> são correlacionados — pequenas
diferenças entre ajustes são esperadas. Use as medições de EIS para
desacoplar (é a proposta central da dissertação).</p>
""", "iv"))

    # -- Gráficos ----------------------------------------------------------
    s.append(("graficos", "Abas de gráficos (Nyquist e Bode)", f"""
<h1>Nyquist, Bode Magnitude e Bode Fase</h1>
{_img("nyquist.png", 720)}
<p>As três abas mostram as medições <b>marcadas</b> no dock
Amostras:</p>
<ul>
<li><b>Nyquist</b> — −Z'' vs. Z' com eixos em escala igual (aspecto
1:1), como manda a boa prática de EIS;</li>
<li><b>Bode Magnitude</b> — |Z| vs. frequência (log-log);</li>
<li><b>Bode Fase</b> — fase vs. frequência (semilog).</li>
</ul>
<p>A barra de navegação de cada gráfico traz, da esquerda para a
direita: <b>casa</b> (restaura a visão original), <b>setas</b>
(desfaz/refaz o zoom), <b>cruz</b> (pan — arrastar o gráfico),
<b>lupa</b> (zoom por retângulo), <b>ajustes</b> (margens),
<b>disquete</b> (salvar a figura como imagem). O botão
<b>Cursor</b> liga um cursor de leitura que mostra as coordenadas
do ponto sob o mouse — útil para ler frequências características
direto do gráfico.</p>
<p>Os gráficos redesenham automaticamente ao marcar/desmarcar
medições no dock Amostras ou mudar qualquer estilo no dock
Opções.</p>
<h2>Dock "Opções de gráfico"</h2>
<ul>
<li><b>Marcador</b> (símbolo e tamanho) e <b>linha</b> (espessura e
estilo);</li>
<li><b>Grade</b> liga/desliga;</li>
<li><b>Cores de fundo</b> — figura, área dos eixos, grade e texto;
o botão <b>"Fundo claro (publicação)"</b> aplica um tema branco
pronto para artigos, e <b>"Restaurar cores do tema"</b> volta ao
padrão escuro;</li>
<li><b>Cor por curva</b> — selecione a medição no dock Amostras e use
"Cor da curva…" (escolha manual) ou "Cor automática".</li>
</ul>
""", None))

    # -- Dock amostras -----------------------------------------------------
    s.append(("amostras", "Dock Amostras", f"""
<h1>Dock Amostras</h1>
{_img("amostras.png", 380)}
<p>Lista todas as medições criadas. A <b>caixa de seleção</b> de cada
uma controla sua presença nos gráficos, na validação KK, nos ajustes
em lote e nas exportações.</p>
<ul>
<li><b>Carregar na tabela</b> — envia a medição para a aba Dados
(para inspecionar ou editar);</li>
<li><b>Renomear / Duplicar / Remover</b> — gestão das medições
(duplicar é útil antes de aplicar uma correção, para preservar a
original);</li>
<li><b>Cor da curva… / Cor automática</b> — cor da medição nos
gráficos;</li>
<li><b>Marcar todas / Desmarcar todas</b> — seleção em massa.</li>
</ul>
<p>Medições corrigidas pela Correção do Instrumento exibem um
indicador e mantêm a anotação de qual correção foi usada (essa
informação é preservada ao salvar o projeto .fra).</p>
""", None))

    # -- KK ----------------------------------------------------------------
    s.append(("kk", "Aba Kramers-Kronig", f"""
<h1>Validação de Kramers-Kronig</h1>
{_img("kk.png", 720)}
<p>Verifica a <b>consistência física</b> do espectro (linearidade,
causalidade e estabilidade durante a medição) pelo método
<i>lin-KK</i> (ajuste a uma soma de circuitos RC). Dados que violam
KK não devem ser ajustados a circuitos.</p>
<ul>
<li>Escolha a medição e clique em <b>Validar Kramers-Kronig</b>;</li>
<li>O gráfico mostra os <b>resíduos</b> de Z' e Z'' em função da
frequência;</li>
<li><b>Critério prático:</b> resíduos aleatórios dentro de ±1–2% →
espectro consistente; resíduos com forma sistemática (rabo, corcova)
→ deriva, não-linearidade ou artefato do instrumento.</li>
</ul>
<p><b>Nota de convenção:</b> seguindo a convenção de sinais do
programa (−Z''), os sinais dos resíduos podem aparecer invertidos em
relação a alguns livros-texto; a interpretação (magnitude e forma)
é a mesma.</p>
""", None))

    # -- Circuito equivalente ---------------------------------------------
    s.append(("circuito", "Aba Circuito Equivalente", f"""
<h1>Ajuste de circuito equivalente</h1>
{_img("circuito.png", 720)}
<p>Ajusta o espectro a um <b>circuito equivalente</b> (Randles,
RC séries/paralelos, CPE, Warburg…). Os parâmetros ajustados
(R, C, Q, n, σ) são os "biomarcadores" das falhas do módulo.</p>
<ul>
<li>Escolha um <b>modelo pronto</b> na lista ou monte o seu no
<b>Editor de circuito…</b>;</li>
<li>Dê chutes iniciais (ou aceite os padrões) e clique em
<b>Ajustar circuito</b>;</li>
<li>O resultado mostra os parâmetros com incertezas e o χ²; o
gráfico sobrepõe o ajuste aos dados.</li>
</ul>
<h2>Editor de circuito (estilo NOVA/ZView)</h2>
{_img("editor_circuito.png", 640)}
<p>Monte topologias livres combinando elementos:</p>
<ul>
<li><b>Adicionar elemento</b> — R, C, L, CPE (Q), Warburg (W);</li>
<li><b>Grupo paralelo / Grupo série</b> — aninham elementos;</li>
<li><b>▲ Subir / ▼ Descer / Remover</b> — organizam a árvore;</li>
<li><b>Carregar modelo</b> — parte de um template (ex.: Randles).</li>
</ul>
<p>O circuito é descrito pela notação <code>R0-p(R1,C1)</code>
(série com hífen; paralelo com <code>p(...)</code>), compatível com o
pacote <i>impedance.py</i>.</p>
""", None))

    # -- Método CNLS (subtópico do circuito) -------------------------------
    s.append(("cnls", "Método de ajuste (CNLS)", """
<h1>O método de regressão: CNLS</h1>
<p>O ajuste usa <b>mínimos quadrados não lineares complexos</b>
(CNLS — <i>Complex Nonlinear Least Squares</i>), o método padrão da
literatura de EIS e dos softwares comerciais (ZView, NOVA, EC-Lab).
Não confundir com regressão <i>linear</i>: os parâmetros entram no
modelo em denominadores, produtos e expoentes, exigindo solução
iterativa.</p>
<h2>Função objetivo</h2>
<p>As partes real e imaginária são ajustadas <b>simultaneamente</b>
(são faces da mesma função, ligadas por Kramers-Kronig):</p>
<p style="text-align:center;"><i>S(θ) = Σ<sub>k</sub> w<sub>k</sub>
{ [Z'<sub>k</sub> − Z'(f<sub>k</sub>;θ)]² +
[Z''<sub>k</sub> − Z''(f<sub>k</sub>;θ)]² }</i></p>
<p>Geometricamente: cada termo é a distância ao quadrado, no plano
complexo, entre o ponto medido e o do modelo naquela frequência.</p>
<h2>Ponderação pelo módulo</h2>
<p>O programa usa <b>w<sub>k</sub> = 1/|Z<sub>k</sub>|²</b>
(ponderação proporcional). Como |Z| varia ordens de grandeza no
espectro, sem ponderação as baixas frequências dominariam e a região
de alta frequência (onde está o R<sub>s</sub>) seria ignorada. A
ponderação pelo módulo equivale a assumir erro <i>percentual</i>
constante do instrumento — a recomendação de Boukamp e de
Orazem &amp; Tribollet.</p>
<h2>Algoritmo</h2>
<ol>
<li><b>Estimativa inicial derivada dos dados</b> — R<sub>s</sub> =
intercepto de alta frequência; R<sub>p</sub> = diâmetro do
semicírculo; C da frequência do pico de −Z''
(ω·R<sub>p</sub>·C = 1). Determinística: duas execuções dão o mesmo
resultado;</li>
<li><b>Iteração Trust Region Reflective</b> (via
<code>scipy.optimize.curve_fit</code>, encapsulado pelo
<i>impedance.py</i>) — lineariza localmente (Jacobiano), resolve o
passo de Gauss-Newton dentro de uma região de confiança e
<b>respeita as restrições de positividade</b> (R, C, Q &gt; 0),
nunca visitando valores sem sentido físico;</li>
<li><b>Convergência</b> — para quando a variação da soma de
quadrados e dos parâmetros fica abaixo das tolerâncias (se não
convergir, o programa avisa — normalmente estimativa inicial ruim ou
modelo inadequado aos dados).</li>
</ol>
<h2>O que sai do ajuste</h2>
<ul>
<li><b>Parâmetros com incerteza</b> — o erro-padrão vem da matriz de
covariância no mínimo; parâmetros de incerteza enorme indicam
correlação (ex.: Q e n do CPE) ou dados insuficientes;</li>
<li><b>χ² ponderado e χ² reduzido</b> = χ²/(2N − p), com 2N porque
cada frequência contribui com dois dados (real e imaginário);</li>
<li><b>RMSE e R²</b> sobre as componentes concatenadas.</li>
</ul>
<p><b>Critério de modelo:</b> resíduos aleatórios + χ² reduzido
estável = modelo adequado; se adicionar um elemento ao circuito
quase não baixa o χ², é sobreparametrização.</p>
<h2>Referências clássicas</h2>
<ul>
<li>Macdonald &amp; Garber, <i>J. Electrochem. Soc.</i> 124 (1977) —
formulação do CNLS;</li>
<li>Boukamp, <i>Solid State Ionics</i> 20 (1986) — EQIVCT e ligação
com a validação KK;</li>
<li>Orazem &amp; Tribollet, <i>Electrochemical Impedance
Spectroscopy</i>, Wiley — capítulos de regressão e ponderação.</li>
</ul>
""", "circuito"))

    # -- Comparação --------------------------------------------------------
    s.append(("comparacao", "Aba Comparação", f"""
<h1>Aba Comparação</h1>
{_img("comparacao.png", 720)}
<p>Sobrepõe <b>várias medições no mesmo gráfico</b>, em um layout
dedicado à comparação visual entre amostras — é aqui que a
assinatura de cada falha salta aos olhos (ex.: semicírculo maior =
mais resistência de transferência; achatamento = dispersão/CPE).</p>
<h2>Como usar</h2>
<ol>
<li>Na lista à esquerda, marque as medições a comparar (ou clique em
<b>Selecionar todas</b>);</li>
<li>Escolha o <b>tipo de gráfico</b>:
<ul>
<li><b>Nyquist</b> — −Z'' vs. Z', escala 1:1;</li>
<li><b>Bode — Magnitude</b> — |Z| vs. f (log-log);</li>
<li><b>Bode — Fase</b> — fase vs. f (semilog);</li>
<li><b>Bode completo</b> — |Z| e fase juntos, em dois painéis
alinhados pela frequência (prático para relatórios);</li>
</ul></li>
<li>O gráfico usa as cores por curva definidas no dock Amostras —
padronize as cores antes para manter a identidade de cada amostra em
todas as figuras.</li>
</ol>
<h2>Comparação de parâmetros do modelo de diodo</h2>
<p>Após <b>"Ajustar todas…"</b> na janela do modelo de diodo (aba
Curva I-V), abre-se a janela <b>"Comparação — modelo de diodo entre
amostras"</b>: uma tabela com I<sub>L</sub>, I₀, R<sub>s</sub>,
R<sub>p</sub> e <i>a</i> de todas as curvas lado a lado, além do R²
de cada ajuste. É o resumo ideal para a análise de degradação
(R<sub>s</sub> subindo → corrosão/solda; R<sub>p</sub> caindo →
PID/shunt; I₀ subindo → degradação da junção).</p>
""", None))

    # -- Parâmetros --------------------------------------------------------
    s.append(("parametros", "Aba Parâmetros", f"""
<h1>Aba Parâmetros — degradação em função do ensaio</h1>
{_img("parametros.png", 720)}
<p>Plota os <b>parâmetros extraídos dos ajustes</b> (R<sub>s</sub>,
R<sub>p</sub>, C, CPE Q e n, Warburg, ou os 5 do modelo de diodo) em
função das amostras ou de uma <b>variável de ensaio</b> — por padrão
o <b>número de pancadas</b>. É o gráfico que mostra a assinatura da
degradação e que normalmente vai para a dissertação.</p>
<h2>Passo a passo</h2>
<ol>
<li>Ajuste as amostras primeiro (aba Circuito Equivalente, ou
"Ajustar modelo de diodo…" na aba Curva I-V). Só amostras ajustadas
aparecem aqui;</li>
<li>Escolha a <b>fonte dos parâmetros</b>: circuito equivalente ou
modelo de diodo;</li>
<li>Marque os <b>parâmetros a plotar</b> na lista;</li>
<li>Em <b>"Valor por amostra"</b>, digite o número de pancadas de
cada amostra (0, 1, 2, …). O nome da variável é editável — troque
por "ciclos térmicos", "horas de PID" ou o que seu ensaio usar;</li>
<li>O gráfico atualiza sozinho a cada mudança.</li>
</ol>
<h2>Controles</h2>
<ul>
<li><b>Eixo X</b> — "Variável de ensaio" (nº de pancadas) ou
"Amostras (ordem)", que usa os nomes como eixo categórico;</li>
<li><b>Gráfico</b> — linha com marcadores (mostra tendência) ou
barras (comparação ponto a ponto; com um único parâmetro, cada barra
usa a cor da amostra definida no dock Amostras);</li>
<li><b>Eixo Y logarítmico</b> — essencial para I₀ e Q, que variam
ordens de grandeza;</li>
<li><b>Normalizar (% da 1ª amostra)</b> — expressa tudo em
porcentagem do módulo íntegro. É o que permite pôr R<sub>s</sub> e
R<sub>p</sub> no mesmo eixo apesar das unidades diferentes:
"R<sub>s</sub> subiu para 280% e R<sub>p</sub> caiu para 46% após 3
pancadas".</li>
</ul>
<h2>Barras de erro</h2>
<p>As barras vêm das <b>incertezas 1σ do próprio ajuste</b> (matriz
de covariância do CNLS) — não é preciso calcular nada à parte. Uma
barra grande avisa que aquele parâmetro está mal determinado (típico
de Q e n, que são correlacionados) e que a conclusão sobre ele
precisa de cautela.</p>
<h2>Exportação</h2>
<ul>
<li><b>Exportar imagem…</b> — PNG/SVG/PDF (SVG e PDF são vetoriais,
ideais para LaTeX);</li>
<li><b>Exportar tabela…</b> — CSV com uma linha por amostra e
colunas de valor <i>e</i> incerteza de cada parâmetro, além da
variável de ensaio — pronto para o Origin ou para uma tabela da
dissertação.</li>
</ul>
<p><b>Observação:</b> se as amostras foram ajustadas com modelos
diferentes (ex.: uma com Randles e outra com CPE), cada parâmetro é
plotado apenas com as amostras que o possuem — nada é inventado.
Amostras sem valor da variável de ensaio ficam fora do gráfico e são
listadas no aviso abaixo dele.</p>
""", None))

    # -- Correção ----------------------------------------------------------
    s.append(("correcao", "Correção do Instrumento", f"""
<h1>Correção do Instrumento</h1>
{_img("correcao.png", 700)}
<p>Remove do espectro a resposta do próprio instrumento/cabos
(função de transferência H(f)), medida com um <b>padrão conhecido</b>
(ex.: resistor de precisão).</p>
<p><b>A ideia:</b> medindo um padrão de valor conhecido
Z<sub>nominal</sub>, tudo o que o instrumento "acrescenta" aparece
na razão <i>H(f) = Z<sub>medido</sub>(f) / Z<sub>nominal</sub></i>.
Ao aplicar a correção, cada medição é dividida por H(f) — ganho e
fase espúrios de cabos, shunt e eletrônica são descontados em toda a
faixa de frequência. Vale para o mesmo arranjo físico: se trocar
cabos ou faixa do instrumento, gere nova correção.</p>
<p><b>Passo a passo:</b></p>
<ol>
<li>Meça o padrão conhecido no instrumento e importe o espectro;</li>
<li>Em Análise → Correção do Instrumento, informe o valor nominal do
padrão e clique em <b>Calcular H(f)</b>;</li>
<li><b>Salvar correção na lista</b> — a correção fica na biblioteca,
com nome e observações;</li>
<li>Use Análise → <b>Aplicar correção à medição…</b> para corrigir
qualquer medição (recomenda-se <b>duplicar</b> a medição antes).</li>
</ol>
<ul>
<li><b>Importar… / Exportar…</b> — troca correções entre
computadores (arquivo próprio);</li>
<li><b>Remover correção</b> — exclui da biblioteca.</li>
</ul>
<p>Medições corrigidas guardam a referência da correção aplicada —
tudo é preservado no projeto <code>.fra</code>.</p>
""", None))

    # -- Serial ------------------------------------------------------------
    s.append(("serial", "Conexão Serial", f"""
<h1>Conexão Serial (Ferramentas → Conexão Serial…)</h1>
<p>Recebe pontos de medição de um sistema embarcado em tempo real.
Ao abrir, escolha o tipo de dispositivo:</p>
<h2>1. Dispositivo genérico (porta COM)</h2>
{_img("serial_generico.png", 700)}
<p>Para qualquer embarcado que envie uma linha por ponto
(terminada em <code>\\n</code>):</p>
<ul>
<li><b>Porta</b> e <b>Baud</b> (padrão 115200) — "Atualizar portas"
relê as portas do sistema;</li>
<li><b>Configuração da comunicação</b> — bits de dados (5–8),
paridade (nenhuma/par/ímpar), bits de parada (1/1,5/2) e controle de
fluxo (nenhum, RTS/CTS, XON/XOFF). O padrão <b>8N1 sem fluxo</b> é o
usado por Arduino/ESP32 e conversores USB-serial; só mude se o manual
do seu equipamento pedir. O painel trava enquanto conectado;</li>
<li><b>Formato dos dados</b> — ordem das colunas no formato
posicional (ex.: <code>10000,10.2,0.00012,-80.2</code>). Linhas
<b>rotuladas</b> — <code>f=10000 V=10,2 I=0,00012 pha=-80,2</code> ou
<code>f=1000 z'=998 z''=-12</code> — são reconhecidas automaticamente
em qualquer ordem;</li>
<li>Vírgula decimal e separadores vírgula/;/tab/espaço são aceitos;
um marcador inicial (#, $, &gt;) é ignorado — o firmware pode usá-lo
para distinguir dados de mensagens de log.</li>
</ul>
<h2>2. AD5933 — analisador de impedância (via ESP32)</h2>
{_img("serial_ad5933.png", 700)}
<p>Modo dedicado à placa AD5933 (kit KDT5933-013) ligada a um ESP32
com o firmware do projeto (<code>firmware/esp32_ad5933/</code>).
Configure a varredura como no software da Analog Devices:</p>
<ul>
<li><b>Freq. inicial / Freq. final / Nº de pontos</b> — o incremento
é calculado automaticamente;</li>
<li><b>Excitação</b> — 2 / 1 / 0,4 / 0,2 Vpp (cada opção indica o
offset DC da senoide de saída);</li>
<li><b>Ganho PGA</b> — ×1 ou ×5 no receptor;</li>
<li><b>Acomodação</b> — ciclos de espera antes de cada DFT.</li>
</ul>
<p><b>Ordem de uso:</b> Conectar → <b>Ler temperatura</b> (testa o
I²C) → <b>Enviar configuração</b> → <b>Iniciar varredura</b>. Os
pontos chegam no formato <code>f= z'= z''=</code> e aparecem na
prévia.</p>
<h2>Em ambos os modos</h2>
<ul>
<li><b>Pontos recebidos</b> — prévia nas 7 colunas canônicas;</li>
<li><b>Log da porta serial</b> — texto bruto (inclui respostas do
firmware, ex.: <code># CFG ok</code> e temperatura);</li>
<li><b>Criar medição</b> — transforma os pontos em uma medição;</li>
<li><b>Enviar para a tabela de dados</b> — manda os pontos à aba
Dados;</li>
<li><b>Limpar pontos</b> — descarta prévia e log.</li>
</ul>
""", None))

    # -- Calibração --------------------------------------------------------
    s.append(("calibracao", "Calibração do instrumento", """
<h1>Calibração do instrumento (botão "Calibrar instrumento…")</h1>

<h2>Por que calibrar</h2>
<p>O AD5933 <b>não mede ohms</b>. Ele devolve, para cada frequência, um
par de números inteiros — real e imaginário — proporcional à
<b>corrente</b> que atravessa a amostra. Sem calibração esses números
não são impedância: são contagens do conversor. Uma varredura feita com
o instrumento descalibrado produz gráficos com aparência perfeitamente
normal e valores errados por ordens de grandeza.</p>

<h2>O que a calibração determina</h2>
<ul>
<li><b>O ganho do caminho de medição</b>, <code>K(f)</code>. Ele depende
sobretudo do resistor de transimpedância da placa (o <code>R9</code>),
que é escolhido conforme a década de impedância que se quer medir.</li>
<li><b>A fase do sistema.</b> O caminho analógico e a própria DFT
introduzem um atraso, e atraso constante significa <b>fase proporcional
à frequência</b>. Na prática ela varre de cerca de 89° a 153° ao longo
da banda.</li>
<li><b>A resistência de saída do próprio chip</b>, o <code>ROUT</code>,
que fica eletricamente <b>em série</b> com a amostra.</li>
</ul>
<p>Os dois primeiros — ganho e fase — dependem do <b>ganho do PGA</b> e
da <b>banda de clock</b>, e por isso existe um jogo de coeficientes para
cada combinação: 3 bandas × 2 ganhos = <b>seis perfis</b>. O
<code>ROUT</code> é o oposto: é propriedade do estágio de saída do chip,
não muda com o PGA nem com o clock, e por isso é <b>um valor único</b>,
determinado uma vez e compartilhado por todos os perfis.</p>

<h2>Por que são dois padrões, e não um</h2>
<p>Este é o ponto que mais gera erro silencioso. O que o instrumento
mede é</p>
<p align="center"><code>mag = K(f) / (ROUT + |Z|)</code></p>
<p>e <b>não</b> <code>mag &prop; 1/|Z|</code>. Com um único padrão, o
ganho e o <code>ROUT</code> ficam indistinguíveis: qualquer combinação
dos dois que reproduza aquele ponto serve. O resultado é uma resposta
<i>afim</i> em vez de proporcional, e o erro cresce à medida que a
amostra se afasta do valor usado na calibração — podendo passar de
<b>90 %</b> nas impedâncias baixas.</p>
<p>O motivo é físico e fácil de ver com números: numa amostra de
150&nbsp;Ω, um <code>ROUT</code> de ~230&nbsp;Ω é <b>maior que a própria
amostra</b>. Confiar no valor "típico" do catálogo em vez de medir o do
seu exemplar custa dezenas de porcento. Medido nesta placa, o
<code>ROUT</code> ficou em 230,3&nbsp;Ω contra os 200&nbsp;Ω que o
datasheet publica como típico.</p>
<p>A partir da <b>segunda subfaixa</b> um padrão só é suficiente: o
<code>ROUT</code> é uma propriedade do chip, não muda com o ganho do
PGA, e o assistente reaproveita o valor já determinado.</p>

<h2>Por que a fase não pode ser uma constante</h2>
<p>Um valor único de fase erraria por dezenas de graus nos extremos da
banda. Como o diagrama de Nyquist é justamente a parte real contra a
imaginária, um erro de fase <b>gira</b> o gráfico inteiro: semicírculos
aparecem deformados ou inclinados, e o ajuste de circuito equivalente
converge para elementos que não existem. Por isso a fase é ajustada por
uma reta em frequência, e o ganho por um polinômio de grau 2.</p>

<h2>Uma calibração para cada banda</h2>
<p>Para descer abaixo de 1&nbsp;kHz o instrumento troca o clock mestre —
é a <b>varredura por bandas</b> descrita no tópico <b>Clock externo e
bandas</b>. Isso obriga a calibrar cada banda separadamente, e o motivo
é o parágrafo anterior levado a sério.</p>
<p>O atraso do sistema tem duas parcelas: o caminho analógico e a
<b>janela da DFT</b>, que dura <code>16384 ÷ MCLK</code>. A segunda é
<i>proporcional ao clock</i> — de 0,98&nbsp;ms na banda 0 ela passa a
10&nbsp;ms na banda 1 e a 100&nbsp;ms na banda 2. Como a fase de um
atraso é <code>−2πfτ</code>, mudar o clock muda a <b>inclinação</b> da
reta de fase. Reaproveitar os coeficientes de uma banda em outra gira o
diagrama de Nyquist inteiro: os semicírculos aparecem inclinados e o
ajuste de circuito converge para elementos que não existem. O ganho
<code>K(f)</code> também muda, porque a faixa de frequência e a resposta
do filtro passam a ser outras.</p>
<p>Na prática:</p>
<ul>
<li>selecione a banda <b>antes</b> de abrir o assistente, e calibre-a
com padrões medidos <b>dentro da faixa útil dela</b>;</li>
<li>o <code>ROUT</code> só precisa dos dois padrões <b>uma vez</b>: nas
demais bandas e ganhos o assistente reaproveita o valor;</li>
<li>o comando <code>G</code> lista os seis perfis e informa, para cada
um, se veio da memória da placa ou dos valores compilados no
firmware;</li>
<li>uma banda <b>sem calibração recusa varrer</b>. Isso é proposital:
sem os coeficientes daquela banda, os inteiros do conversor não têm como
virar ohms.</li>
</ul>
<p>A prova de que o conjunto está coerente é a <b>emenda</b>: as bandas
se superpõem em quase uma década, e o mesmo ponto medido nas duas tem de
dar a mesma impedância. Um degrau na emenda é o sintoma clássico de
calibração ruim em uma delas.</p>


<h2>Escolhendo os padrões</h2>
<ul>
<li>Perto dos <b>extremos</b> da faixa que você vai medir — quanto mais
distantes entre si, melhor a separação do <code>ROUT</code>;</li>
<li><b>Medidos no multímetro</b>. O valor impresso no corpo do resistor
não serve: a calibração é tão exata quanto o padrão;</li>
<li>Resistores de <b>filme metálico 1&nbsp;%</b> e baixo coeficiente de
temperatura. Resistores de fio têm indutância e falseiam a fase.</li>
</ul>

<h2>Passo a passo do assistente</h2>
<ol>
<li><b>Apresentação</b> — o que será feito e o que ter em mãos.</li>
<li><b>Configuração da varredura</b> — ganho do PGA, excitação, faixa de
frequência, número de pontos e acomodação, sobre a <b>banda de clock que
estiver ativa</b> (selecione-a antes, com <code>B sel=…</code> no
terminal, se não for a banda 0). Use aqui <b>exatamente</b> a
configuração com que pretende medir as amostras: a calibração vale para
uma combinação específica de banda e ganho, e a faixa de frequência
precisa caber entre o piso e o teto da banda escolhida.</li>
<li><b>Primeiro padrão</b> — ligue-o entre os dois terminais da amostra,
digite o valor medido e clique em <b>Medir padrão</b>.</li>
<li><b>Segundo padrão</b> — idem, com o resistor do outro extremo. Há um
botão para <b>pular</b> esta etapa quando o <code>ROUT</code> já for
conhecido.</li>
<li><b>Resultado</b> — números de qualidade e o gráfico de erro. O botão
<b>Gravar na placa</b> guarda os coeficientes na memória não volátil do
ESP32, <b>no perfil daquela banda e daquele ganho</b>, de onde são lidos
a cada partida — não é preciso recompilar o firmware. Os outros perfis
não são tocados.</li>
</ol>

<h2>Como interpretar o resultado</h2>
<ul>
<li><b>Resíduo do ganho</b> — abaixo de ~0,5 % é bom. Muito acima disso
costuma indicar contato ruim, padrão instável ou nível de sinal
impróprio.</li>
<li><b>Resíduo da fase</b> — abaixo de ~1° é bom; ele piora quando o
sinal é fraco.</li>
<li><b>Magnitude saturada</b> (perto do teto do conversor) — o padrão é
pequeno demais para o resistor de transimpedância instalado. Nenhuma
matemática recupera um sinal ceifado: troque o padrão ou o
<code>R9</code>.</li>
<li><b>Magnitude fraca</b> (poucas centenas de contagens) — o padrão é
grande demais para a faixa; use o ganho ×5 ou um padrão menor.</li>
</ul>
<p><b>Cuidado com a circularidade:</b> o assistente mostra a impedância
reconstruída dos próprios padrões, mas eles participaram do ajuste, então
reproduzi-los bem é esperado e prova pouco. A verificação que vale é
medir depois um <b>terceiro resistor</b>, de valor conhecido, que não
tenha entrado na calibração.</p>

<h2>Quando recalibrar</h2>
<p>Sempre que mudar qualquer elo da cadeia: o resistor de
transimpedância da placa, a faixa de excitação, o ganho do PGA ou o
clock do AD5933. O clock é o caso mais radical — cada banda é uma
calibração inteira, e alterar o MCLK de uma banda (comando
<code>B i=… mclk=…</code>) invalida os perfis dela.</p>
<p>O botão <b>Restaurar calibração de fábrica</b> apaga a calibração
gravada e volta aos coeficientes compilados no firmware — o que hoje
significa a banda 0 calibrada e as bandas 1 e 2 novamente sem
calibração.</p>
""", "serial"))

    # -- O analisador AD5933 -----------------------------------------------
    s.append(("ad5933", "O analisador AD5933", f"""
<h1>O analisador de impedância AD5933</h1>
<p>Todo o hardware de aquisição deste projeto gira em torno de um único
circuito integrado, o <b>AD5933</b> da Analog Devices. Entender o que ele
faz — e sobretudo o que ele <i>não</i> faz — é pré-requisito para
interpretar qualquer espectro medido aqui, e para defender os resultados
com propriedade.</p>

{_img("ad5933_blocos.png")}

<h2>O que o chip é</h2>
<p>É um <b>conversor de impedância</b> completo num só encapsulamento,
reunindo três coisas que normalmente seriam instrumentos separados:</p>
<ul>
<li>um <b>gerador de sinal</b> por síntese digital direta (DDS), que
produz uma senoide de frequência programável;</li>
<li>um <b>receptor</b> com amplificador de transimpedância, ganho
programável, filtro e conversor A/D de 12 bits;</li>
<li>um <b>detector síncrono</b> — uma DFT de 1024 pontos implementada em
hardware, que extrai a componente do sinal <i>exatamente</i> na
frequência de excitação.</li>
</ul>
<p>Esse último item é o que torna possível fazer espectroscopia de
impedância com um chip barato: a DFT funciona como um amplificador
<i>lock-in</i>, rejeitando ruído e interferência em qualquer frequência
que não seja a da excitação. É por isso que uma medida limpa sai mesmo
num ambiente eletricamente sujo.</p>

<h2>Como a medida acontece</h2>
<ol>
<li>O DDS gera uma senoide na frequência programada, que sai pelo pino
<b>VOUT</b> com um nível contínuo próprio (o <i>offset</i>).</li>
<li>Essa tensão é aplicada à amostra. A corrente resultante entra no
pino <b>VIN</b>, que o chip mantém como <b>terra virtual</b> em
VDD/2 — ou seja, a amostra vê a diferença entre o offset do VOUT e
VDD/2 como polarização contínua.</li>
<li>O amplificador de transimpedância converte essa corrente em tensão,
com ganho dado pelo resistor externo <b>R<sub>FB</sub></b>.</li>
<li>O sinal passa pelo <b>PGA</b> (×1 ou ×5), por um filtro passa-baixas
e é digitalizado a MCLK/16.</li>
<li>A DFT acumula 1024 amostras e grava dois inteiros de 16 bits com
sinal: <b>REAL</b> e <b>IMAG</b>.</li>
</ol>

<h2>O ponto que mais gera erro</h2>
<p>O AD5933 <b>não devolve ohms</b>. REAL e IMAG são proporcionais à
<b>corrente</b>, não à impedância, e a constante de proporcionalidade
depende do R<sub>FB</sub>, do PGA, da faixa de excitação e do clock.
Transformar esses inteiros em impedância é papel da calibração. Um
instrumento descalibrado produz gráficos de aparência absolutamente
normal e valores errados por ordens de grandeza — não há como perceber
olhando o resultado.</p>

<h2>Registradores relevantes</h2>
<p>A comunicação é por <b>I²C</b>, no endereço <code>0x0D</code>. Neste
projeto quem fala I²C com o chip é um ESP32, que faz a ponte para a USB
do computador.</p>
<table border="1" cellpadding="4" cellspacing="0">
<tr><th>Endereço</th><th>Função</th></tr>
<tr><td><code>0x80</code>, <code>0x81</code></td><td>Controle: comando,
faixa de saída, ganho do PGA, <i>reset</i> e seleção de clock</td></tr>
<tr><td><code>0x82</code>–<code>0x84</code></td><td>Frequência inicial
(24 bits)</td></tr>
<tr><td><code>0x85</code>–<code>0x87</code></td><td>Incremento de
frequência (24 bits)</td></tr>
<tr><td><code>0x88</code>–<code>0x89</code></td><td>Número de
incrementos (9 bits, máx. 511)</td></tr>
<tr><td><code>0x8A</code>–<code>0x8B</code></td><td>Tempo de acomodação:
contagem de 9 bits + multiplicador de 2 bits</td></tr>
<tr><td><code>0x8F</code></td><td>Status: temperatura válida, dado
válido, fim da varredura</td></tr>
<tr><td><code>0x92</code>–<code>0x93</code></td><td>Temperatura do
chip</td></tr>
<tr><td><code>0x94</code>–<code>0x97</code></td><td>REAL e IMAG</td></tr>
</table>
<p>A palavra de frequência é calculada por</p>
<p align="center"><code>código = (f ÷ (MCLK ÷ 4)) × 2<sup>27</sup></code></p>
<p>o que dá uma resolução de MCLK/2<sup>29</sup> — cerca de
0,03&nbsp;Hz com o oscilador interno.</p>

<h2>Sensor de temperatura</h2>
<p>O chip traz um sensor interno com resolução de 0,03&nbsp;°C, exposto
no botão <b>Ler temperatura</b> da janela de conexão. Ele serve a dois
propósitos: é o teste mais rápido de que o I²C está funcionando, e
documenta a temperatura do ensaio — útil porque tanto o R<sub>FB</sub>
quanto a própria amostra têm deriva térmica.</p>
""", None))

    s.append(("ad5933_freq", "Limites de frequência", f"""
<h1>Limites de frequência</h1>

<h2>O piso: por que existe e onde fica</h2>
<p>A DFT do AD5933 sempre integra <b>1024 amostras</b>, e o conversor
sempre amostra a <b>MCLK/16</b>. Isso significa que a janela de análise
tem duração <b>fixa</b>, independente da frequência que se está
medindo:</p>
<p align="center"><code>janela = 1024 × 16 ÷ MCLK</code></p>
<p>Com o oscilador interno de 16,776&nbsp;MHz, essa janela vale
<b>0,98&nbsp;ms</b>. Para que a DFT tenha algum significado é preciso
que ao menos <b>um ciclo completo</b> da excitação caiba nela, o que
estabelece</p>
<p align="center"><code>f<sub>mín</sub> = MCLK ÷ 16384 ≈ 1024 Hz</code></p>

{_img("ad5933_dft.png")}

<p>Abaixo desse piso o chip continua gerando a senoide e continua
devolvendo números — mas a DFT integra apenas uma fração de ciclo, e o
par REAL/IMAG deixa de ser uma medida de impedância. A 10&nbsp;Hz, por
exemplo, a janela cobre menos de 1&nbsp;% de um ciclo. <b>O resultado é
lixo com aparência de dado</b>, que é o pior tipo de falha num trabalho
científico.</p>
<p>Por isso o firmware deste projeto <b>recusa</b> frequências iniciais
abaixo do piso e explica o motivo, em vez de deixar passar.</p>

<h2>O teto</h2>
<p>O datasheet especifica <b>100&nbsp;kHz</b> como frequência máxima de
excitação. Acima disso o desempenho do estágio analógico e a rejeição do
filtro deixam de ser garantidos. A placa deste projeto foi caracterizada
até 100&nbsp;kHz.</p>
<p>O teto também acompanha o clock, na proporção
<code>f<sub>máx</sub> = MCLK ÷ 167,76</code> — que dá justamente
100&nbsp;kHz com o oscilador interno. Como piso e teto são ambos
proporcionais ao MCLK, a razão entre eles é fixa em
16384/167,76 ≈ <b>97,7</b>: <b>um clock cobre pouco menos de duas
décadas</b>, qualquer que seja ele.</p>

<h2>Resolução</h2>
<p>A palavra de frequência tem 24 bits e o passo é
MCLK/2<sup>29</sup> ≈ 0,03&nbsp;Hz. Na prática a resolução nunca é o
fator limitante: o número de pontos por varredura é que é limitado a
<b>511 incrementos</b> pelo registrador <code>0x88</code>.</p>

<h2>Para descer abaixo de 1 kHz</h2>
<p>O piso é proporcional ao clock, e não uma limitação absoluta do chip.
Fornecendo um clock mais lento pelo conector SMA, a faixa inteira desce
junto. Como cada clock cobre pouco menos de duas décadas, ir de
100&nbsp;Hz a 100&nbsp;kHz exige <b>mais de um clock</b>: a varredura
passa a ser feita por bandas, cada uma com seu MCLK e sua calibração —
ver o tópico <b>Clock externo e bandas</b>. É o caminho para alcançar a
faixa de dezenas de hertz, onde ficam os fenômenos lentos de um módulo
fotovoltaico.</p>
""", "ad5933"))

    s.append(("ad5933_imped", "Limites de impedância", f"""
<h1>Limites de impedância</h1>

<h2>Quem define a faixa</h2>
<p>A corrente que atravessa a amostra é convertida em tensão pelo
amplificador de transimpedância, e o ganho dessa conversão é o resistor
externo <b>R<sub>FB</sub></b> (na placa deste projeto, o
<code>R9</code>). Uma corrente pequena demais some no ruído; uma grande
demais satura o estágio. Como a corrente é inversamente proporcional à
impedância, <b>o R<sub>FB</sub> escolhe a década que a placa consegue
medir</b>.</p>
<p>A própria Analog Devices publica suas faixas nesses termos, uma
década por vez, com o R<sub>FB</sub> da ordem do menor valor da faixa:</p>

{_img("ad5933_faixa.png")}

<table border="1" cellpadding="4" cellspacing="0">
<tr><th>R<sub>FB</sub></th><th>Faixa</th><th>Erro medido pelo
fabricante</th></tr>
<tr><td>100 Ω</td><td>100 Ω – 1 kΩ</td><td>até 7 %</td></tr>
<tr><td>1 kΩ</td><td>1 – 10 kΩ</td><td>até 2 %</td></tr>
<tr><td>10 kΩ</td><td>10 – 100 kΩ</td><td>± 0,3 %</td></tr>
<tr><td>100 kΩ</td><td>100 kΩ – 1 MΩ</td><td>−3,5 a +1 %</td></tr>
</table>
<p>Note que <b>a década mais baixa é sempre a menos exata</b>. Isso é
intrínseco ao chip e vale a pena registrar ao reportar incertezas.</p>

<h2>A placa deste projeto</h2>
<p>O kit vem de fábrica com <b>R<sub>FB</sub> = 200 kΩ</b>, o que o
coloca na faixa de 100&nbsp;kΩ a 1&nbsp;MΩ — o fabricante anuncia
1&nbsp;kΩ a 10&nbsp;MΩ, mas na prática qualquer amostra abaixo de
~98&nbsp;kΩ satura. Para medir módulos fotovoltaicos, que ficam na
década de centenas de ohms, soldou-se um resistor de <b>330 Ω em
paralelo</b> com o original, levando a faixa útil para
<b>150 Ω – 15 kΩ</b>.</p>

<h2>Como reconhecer saturação</h2>
<p>Saturação não se anuncia: a leitura simplesmente <b>trava num valor
constante</b>, igual para qualquer amostra abaixo do limite. O teste
decisivo é mudar o PGA de ×1 para ×5 — numa medida válida a leitura
muda; num sinal ceifado ela praticamente não se altera, porque
amplificar cinco vezes um sinal já ceifado não muda nada. O assistente
de calibração faz esse diagnóstico automaticamente.</p>

<h2>A resistência de saída do chip</h2>
<p>Há um segundo limite, mais sutil. O AD5933 tem <b>resistência de
saída própria</b> (R<sub>OUT</sub>) em <b>série</b> com a amostra: 200 Ω
na faixa de 2 Vpp, 2,4 kΩ na de 1 Vpp, segundo o datasheet. Nesta placa
o valor medido foi <b>230,3 Ω</b>.</p>
<p>Isso tem duas consequências. Primeira: a tensão que efetivamente
chega à amostra é dividida entre ela e o R<sub>OUT</sub>, então
impedâncias muito baixas recebem pouca excitação — em 10 Ω sobrariam
apenas 4 % do sinal. Segunda, e mais importante: o que o instrumento
mede é <code>R<sub>OUT</sub> + Z</code>, não <code>Z</code>. Numa
amostra de 150 Ω o R<sub>OUT</sub> é <i>maior que a própria amostra</i>,
e ignorá-lo introduziria erro de dezenas de porcento. É por isso que a
calibração deste projeto usa dois padrões e resolve o R<sub>OUT</sub>
explicitamente.</p>
""", "ad5933"))

    s.append(("ad5933_pga", "Ganho PGA e acomodação", f"""
<h1>Ganho PGA e tempo de acomodação</h1>

<h2>Ganho PGA</h2>
<p>O PGA (<i>programmable gain amplifier</i>) fica no <b>lado da
recepção</b>, depois do amplificador de transimpedância e antes do
conversor A/D. Ele multiplica o sinal medido por <b>1</b> ou por
<b>5</b>, selecionado pelo bit D8 do registrador de controle. Ele
<b>não</b> altera a excitação aplicada à amostra.</p>
<p>Sua função é aproveitar a escala do conversor. Como a corrente cai
com o aumento da impedância, amostras de alta impedância geram sinal
fraco e usam poucos bits do conversor; o ×5 recupera resolução. Em
contrapartida, ligar o ×5 numa amostra de baixa impedância satura.</p>

{_img("ad5933_pga.png")}

<p>Na prática o PGA <b>desloca a janela útil</b> em cerca de uma
década — o que permite cobrir uma faixa ampla com o mesmo
R<sub>FB</sub>. Nesta placa, com R<sub>FB</sub> ≈ 330 Ω, a divisão
ficou assim:</p>
<ul>
<li><b>PGA ×1</b> — de 150 Ω a ~15 kΩ;</li>
<li><b>PGA ×5</b> — de ~1,3 kΩ a 75 kΩ.</li>
</ul>
<p><b>Atenção:</b> o ganho efetivo medido foi <b>4,858</b>, e não 5
exatos. Isso não é problema, porque a calibração absorve o valor real —
mas significa que <b>cada ganho tem sua própria calibração</b>. Trocar o
PGA sem recalibrar produz erro sistemático.</p>

<h2>Tempo de acomodação</h2>
<p>Ao mudar de frequência, o chip gera um número programável de ciclos
da excitação <b>antes</b> de começar a integrar a DFT. Esse intervalo
existe para que a amostra e toda a cadeia analógica cheguem ao
<b>regime permanente</b>: medir durante o transitório falseia módulo e
fase.</p>
<p>O detalhe que costuma surpreender é que a contagem é em
<b>ciclos</b>, não em tempo. A duração é portanto</p>
<p align="center"><code>t<sub>acomodação</sub> = N ÷ f</code></p>
<p>o que significa que os mesmos 100 ciclos custam 1&nbsp;ms a
100&nbsp;kHz e <b>100&nbsp;ms a 1&nbsp;kHz</b>. Uma varredura que começa
em frequência baixa é legitimamente lenta, e não há nada de errado
nisso.</p>

{_img("ad5933_acomodacao.png")}

<h2>O limite de 511</h2>
<p>A contagem fica nos registradores <code>0x8A</code>/<code>0x8B</code>,
num campo de <b>9 bits</b> — daí o máximo de
2<sup>9</sup> − 1 = <b>511</b>. Os bits D10 e D9 do mesmo registrador
trazem um <b>multiplicador</b> de ×1, ×2 ou ×4, o que eleva o máximo
efetivo a 2.044 ciclos. O firmware deste projeto mantém o multiplicador
em ×1.</p>

<h2>Como escolher</h2>
<ul>
<li><b>Amostras resistivas</b> (resistores de calibração): 100 ciclos é
folgado.</li>
<li><b>Amostras capacitivas</b> — e um módulo fotovoltaico é bastante
capacitivo — precisam de mais tempo para carregar. Se o espectro
apresentar dispersão anômala nas primeiras frequências, aumente a
acomodação e verifique se o resultado muda: se mudar, ainda não estava
em regime permanente.</li>
<li><b>Frequências muito baixas</b>: reduza a acomodação para a
varredura não se tornar impraticável, mas confira o efeito no
resultado.</li>
</ul>
""", "ad5933"))

    s.append(("ad5933_clock", "Clock externo e bandas", f"""
<h1>Clock externo e varredura por bandas</h1>

<h2>O princípio: tudo pende do clock</h2>
<p>Tudo no AD5933 é derivado do clock mestre: a frequência sintetizada
pelo DDS, a taxa de amostragem do conversor (MCLK/16) e, por
consequência, a duração da janela da DFT. Os <b>dois</b> extremos da
faixa útil são proporcionais ao MCLK:</p>
<p align="center"><code>f<sub>mín</sub> = MCLK ÷ 16384</code>
&nbsp;&nbsp;&nbsp;
<code>f<sub>máx</sub> = MCLK ÷ 167,76</code></p>
<p>O piso vem de exigir <b>ao menos um ciclo completo</b> da excitação
dentro da janela de 1024 amostras da DFT. O teto vem do outro lado: em
<code>MCLK ÷ 167,76</code> o conversor ainda tira 167,76/16 ≈
<b>10,5 amostras por ciclo</b> — é a condição em que o chip foi
especificado (100&nbsp;kHz com o oscilador interno de 16,776&nbsp;MHz).
Mantida essa razão, a faixa inteira desliza com o clock sem alterar as
condições de operação do caminho analógico.</p>

{_img("ad5933_clock.png")}

<h2>Por que um clock só não basta</h2>
<p>Como piso e teto são proporcionais ao <i>mesmo</i> MCLK, a razão
entre eles é uma <b>constante do chip</b>, e não uma escolha de
projeto:</p>
<p align="center"><code>f<sub>máx</sub> ÷ f<sub>mín</sub> =
16384 ÷ 167,76 ≈ 97,7</code></p>
<p>Isto é: qualquer clock cobre <b>1,99 décadas</b> — pouco menos de
duas. Medir de 100&nbsp;Hz a 100&nbsp;kHz são <b>três décadas</b>
(razão 1000), e nenhum clock faz isso sozinho: baixá-lo até alcançar os
100&nbsp;Hz derruba o teto para ~9,8&nbsp;kHz; mantê-lo alto para chegar
aos 100&nbsp;kHz sobe o piso para ~1&nbsp;kHz. A varredura passa então a
ser feita <b>por bandas</b>, cada uma com seu MCLK e sua própria
calibração.</p>

<h2>As três bandas</h2>
<table border="1" cellpadding="4" cellspacing="0">
<tr><th>Banda</th><th>MCLK</th><th>Origem do clock</th>
<th>f<sub>mín</sub></th><th>f<sub>máx</sub></th></tr>
<tr><td><b>0</b></td><td>16,776 MHz</td><td>oscilador interno</td>
<td>1023,9 Hz</td><td>100,0 kHz</td></tr>
<tr><td><b>1</b></td><td>1,6384 MHz</td><td>ESP32 (externo)</td>
<td>100,0 Hz</td><td>9,77 kHz</td></tr>
<tr><td><b>2</b></td><td>163,84 kHz</td><td>ESP32 (externo)</td>
<td>10,0 Hz</td><td>977 Hz</td></tr>
</table>

{_img("ad5933_bandas.png")}

<p>As bandas <b>0 e 1</b> já cobrem, juntas, o objetivo de
<b>100&nbsp;Hz a 100&nbsp;kHz</b>; a banda 2 é o degrau extra, até
<b>10&nbsp;Hz</b>, onde ficam os fenômenos lentos de um módulo
fotovoltaico. Esses são os valores de fábrica do firmware e podem ser
trocados pelo comando <code>B</code> — o piso e o teto são recalculados
a partir do MCLK que estiver configurado.</p>
<p><b>O preço da banda baixa é o tempo.</b> A janela da DFT vale
<code>16384 ÷ MCLK</code>: 0,98&nbsp;ms na banda 0, <b>10&nbsp;ms</b> na
banda 1 e <b>100&nbsp;ms</b> na banda 2 — e a isso se soma a acomodação,
que é contada em ciclos (N ÷ f) e portanto também estica. Uma varredura
de baixa frequência é legitimamente lenta; não há nada de errado
nisso.</p>

<h2>A sobreposição entre bandas não é desperdício</h2>
<p>Repare que as faixas se <b>superpõem</b>: 100&nbsp;Hz a 977&nbsp;Hz é
comum às bandas 2 e 1; 1,02&nbsp;kHz a 9,77&nbsp;kHz é comum às bandas 1
e 0. Quase uma década de superposição em cada emenda — e isso é
deliberado.</p>
<p>Na região comum, o <b>mesmo ponto físico</b> da mesma amostra é
medido por duas cadeias que só têm a amostra em comum: clocks
diferentes, janelas de DFT diferentes, calibrações independentes. Se as
duas derem a mesma impedância, é evidência forte de que o espectro
emendado é uma curva física única, e não um artefato do procedimento. Se
aparecer um <b>degrau na emenda</b>, ele denuncia o quê:</p>
<ul>
<li><b>degrau em |Z|</b> — erro de ganho: o <code>K(f)</code> de uma das
bandas está mal ajustado, ou o padrão usado naquela banda estava fora da
faixa útil do R<sub>FB</sub>;</li>
<li><b>degrau só na fase</b> — a reta de fase de uma das bandas está
errada. É o defeito mais comum, justamente porque a inclinação dela
depende do clock;</li>
<li><b>discrepância que cresce em direção à borda</b> — a varredura foi
levada até o limite da banda; recue um pouco de
f<sub>mín</sub>/f<sub>máx</sub>.</li>
</ul>
<p>É a única verificação interna disponível sem um segundo instrumento.
Vale registrá-la no relatório do ensaio, junto com a validação de
Kramers-Kronig do espectro emendado.</p>

<h2>Por que 200 kHz está fora de especificação</h2>
<p>A pergunta é natural: se baixar o clock desce a faixa, subir o clock
não subiria? Não — e o limite é duplo:</p>
<ul>
<li>o datasheet especifica <b>100&nbsp;kHz</b> como frequência máxima de
excitação, acima da qual o estágio analógico e a rejeição do filtro
deixam de ser garantidos;</li>
<li>o datasheet especifica <b>16,776&nbsp;MHz</b> como MCLK máximo, e
chegar a 200&nbsp;kHz exigiria
200&nbsp;kHz × 167,76 = <b>33,552&nbsp;MHz</b> — o <b>dobro</b> do
permitido.</li>
</ul>
<p>Por isso o teto do sistema é <b>fixo em 100&nbsp;kHz</b>: as bandas
só andam para baixo. Forçar o chip acima disso continuaria produzindo
números, e números fora de especificação não se distinguem de uma medida
boa olhando o gráfico.</p>

<h2>Ligação física</h2>
<p>Na placa KDT5933-013 o conector <b>SMA P5</b> está ligado diretamente
ao pino <b>MCLK</b> (pino 8) do AD5933, com um resistor de 1&nbsp;kΩ
como <i>pull-down</i>. É o ponto de injeção do clock externo:</p>
<ul>
<li><b>Sinal</b> — do GPIO do ESP32 (padrão <b>GPIO&nbsp;26</b>,
constante <code>PINO_MCLK</code> no firmware, ajustável) para o
<b>pino central</b> do SMA P5.</li>
<li><b>Terra comum</b> — GND do ESP32 à malha do SMA, pelo caminho mais
curto possível. Sem referência comum não existe "onda quadrada de
3,3&nbsp;V": existe ruído.</li>
<li><b>Resistor de ~100&nbsp;Ω em série</b> na saída do ESP32. As bordas
do LEDC são de poucos nanossegundos e o cabo se comporta como linha de
transmissão: os 100&nbsp;Ω amortecem a reflexão, matam o <i>ringing</i>
na entrada de clock e reduzem o quanto esse chaveamento se acopla ao
caminho analógico do receptor, que está na mesma placa.</li>
</ul>
<p>Os 100&nbsp;Ω em série com o <i>pull-down</i> de 1&nbsp;kΩ formam um
divisor: o nível alto chega em 3,3&nbsp;V × 1000/1100 ≈
<b>3,0&nbsp;V</b>, confortavelmente acima do V<sub>IH</sub> da entrada,
e a corrente exigida do GPIO fica em ~3&nbsp;mA. O nível é
<b>3,3&nbsp;V</b> porque o MCLK é uma entrada digital alimentada pelo
DVDD do chip.</p>
<p><b>Alternativa sem cabo:</b> o footprint <b>U5</b>, que vem vazio,
está na <b>mesma rede</b> do MCLK — soldar ali um oscilador encapsulado
do valor desejado dá um clock de cristal, mais exato e mais limpo que o
LEDC, ao custo de ser fixo (um oscilador por banda).</p>

<h2>Como trocar de banda</h2>
<p>Nada disso exige recompilar: o firmware guarda <b>três bandas</b>, e
o <b>ESP32 gera o clock</b> das duas externas por hardware. Na janela
<i>Conexão Serial</i>, no modo AD5933, o seletor <b>Banda</b> mostra as
três com o clock e a faixa útil de cada uma; enviar a configuração já
aplica a banda escolhida antes de programar a varredura.</p>
<ol>
<li>A <b>banda 0</b> usa o oscilador interno de 16,776&nbsp;MHz e cobre
de ~1&nbsp;kHz a 100&nbsp;kHz. É a única que vem calibrada de fábrica.</li>
<li>As <b>bandas 1 e 2</b> usam o clock do ESP32 e descem a faixa na
mesma proporção. Ao selecioná-las o firmware liga o gerador e o bit
<b>D3</b> do registrador de controle (<code>0x81</code>), que faz o chip
ignorar o oscilador interno.</li>
<li>O clock que vale é o <b>efetivamente sintetizado</b> pelo divisor do
ESP32, não o valor nominal pedido — o firmware devolve esse número, e é
ele que aparece no seletor. Como a frequência de excitação é
proporcional ao MCLK, usar o nominal deslocaria todo o eixo do espectro.</li>
<li><b>Recalibrar cada banda.</b> O ganho e sobretudo a fase do sistema
dependem do clock — o atraso equivalente muda, e com ele toda a correção
de fase. Por isso existe um jogo de coeficientes por banda e por ganho
do PGA, e o firmware <b>recusa a varredura</b> numa banda ainda não
calibrada, em vez de emitir ohms sem sentido.</li>
</ol>
<p><b>Cuidado:</b> o driver de referência do fabricante contém um erro
justamente nesse bit — a constante está comentada como
<code>1&lt;&lt;3</code> mas vale <code>1&lt;&lt;2</code>. Não copie de
lá.</p>

<h2>Por que vale a frequência sintetizada, e não a nominal</h2>
<p>O LEDC não sintetiza qualquer frequência: ele divide os 80&nbsp;MHz
do APB por um divisor de <b>ponto fixo</b>, de modo que o valor pedido é
arredondado para o mais próximo que o divisor consegue produzir. A sobra
costuma ser da ordem de <b>0,1&nbsp;%</b> — pequena, mas não desprezível
pelo motivo a seguir.</p>
<p>A frequência de excitação é <b>proporcional ao MCLK</b>, porque é
dele que se calcula a palavra de frequência. Um erro no MCLK adotado não
espalha ruído: ele <b>desloca todo o eixo de frequência do espectro</b>
pelo mesmo fator, de forma sistemática e invisível no gráfico. As
frequências características lidas do Nyquist e do Bode — e tudo o que se
extrai delas, como o C obtido de ω·R<sub>p</sub>·C&nbsp;=&nbsp;1 —
sairiam enviesadas na mesma proporção.</p>
<p>Por isso o firmware <b>lê de volta</b> o valor que o
<code>ledcSetup()</code> devolve, que é a frequência realmente
sintetizada, e adota <i>esse</i> número como o MCLK da banda — nunca o
nominal que foi pedido. É ele que aparece na resposta dos comandos
<code>B</code> e que alimenta a palavra de frequência, o piso da DFT, o
teto da banda e o tempo-limite de cada ponto.</p>
<p>Com um <b>oscilador encapsulado</b> em U5 o problema muda de figura:
a exatidão passa a ser a do cristal (dezenas de ppm), mas o firmware não
tem como lê-la. Nesse caso <b>meça</b> a frequência com frequencímetro
ou osciloscópio e informe-a com <code>B i=… mclk=…</code>, em vez de
confiar no valor impresso no componente.</p>

<h2>Roteiro completo de uso</h2>
<ol>
<li><b>Ligue o clock</b> — GPIO 26 ao pino central do SMA P5, com os
~100&nbsp;Ω em série, e os terras juntos. A banda 0 não precisa de nada
disso: ela usa o oscilador interno.</li>
<li><b>Confira as bandas</b> — mande <code>B</code> e leia as três
linhas. Confirme que o MCLK efetivo de cada banda externa é o esperado e
que o piso e o teto anunciados cobrem a faixa que você pretende varrer.
Se usar outro oscilador, ajuste com
<code>B i=… mclk=… ext=1</code>.</li>
<li><b>Calibre a banda 0</b> — <code>B sel=0</code> e depois o
assistente de calibração, com <b>dois padrões</b>. É aqui que o
R<sub>OUT</sub> é determinado; como ele é do chip, vale para todas as
bandas.</li>
<li><b>Calibre a banda 1</b> — <code>B sel=1</code> e repita o
assistente <i>dentro da faixa daquela banda</i> (ex.: 120&nbsp;Hz a
9&nbsp;kHz). Com o R<sub>OUT</sub> já conhecido, um padrão basta. Depois
repita para a banda 2. Cada ganho de PGA que você pretenda usar precisa
da sua própria calibração.</li>
<li><b>Varra banda por banda</b> — uma varredura por banda, cada uma
dentro dos seus limites e com folga nas bordas, fazendo questão de
incluir alguns pontos <b>dentro da superposição</b> com a banda
vizinha.</li>
<li><b>Confira a emenda</b> — crie uma medição por banda e compare-as no
Bode (magnitude e fase) da aba <b>Comparação</b>. Sem degrau na região
comum, os pontos podem ser unidos numa medição só; com degrau, volte à
calibração da banda suspeita <i>antes</i> de qualquer análise.</li>
<li><b>Valide</b> — rode Kramers-Kronig no espectro emendado. Uma emenda
mal feita costuma aparecer como resíduo sistemático concentrado na
frequência da junção.</li>
</ol>

<h2>Estado neste projeto</h2>
<p>A <b>banda 0</b> (oscilador interno) é a que está calibrada e
validada, de 2&nbsp;kHz a 100&nbsp;kHz. As <b>bandas 1 e 2</b> saem de
fábrica <b>sem calibração</b>, e o firmware <b>recusa varrer</b> nelas
até que sejam calibradas, explicando o motivo — em vez de emitir ohms
que não têm lastro em padrão nenhum. Uma varredura recusada é um
aborrecimento; um espectro em ohms inventados, defendido numa
dissertação, é outra coisa.</p>
""", "ad5933"))

    # -- Simulação ---------------------------------------------------------
    s.append(("simulacao", "Simulação do módulo FV", f"""
<h1>Simulação do módulo fotovoltaico</h1>
{_img("simulacao.png", 700)}
<p>(Ferramentas → Simulação do módulo FV) Janela didática com uma
<b>animação física do módulo</b>, pensada para apresentações, aulas
e as figuras conceituais da dissertação. Tem duas abas:</p>
<ul>
<li><b>Módulo (corte)</b> — corte transversal com as camadas reais
(vidro, EVA, célula, backsheet, moldura) e os <b>fótons chegando e
gerando pares elétron-lacuna</b>, com o fluxo de portadores até os
contatos;</li>
<li><b>Modelo atômico (Si, dopagem n/p)</b> — a rede cristalina do
silício com os dopantes (fósforo/boro), mostrando eletrão livre e
lacuna e o campo da junção p-n.</li>
</ul>
<h2>Controles</h2>
<ul>
<li><b>Tecnologia</b> — mono-Si, poli-Si, filme fino etc.; o corte e
a legenda técnica mudam conforme a tecnologia escolhida;</li>
<li><b>Irradiância</b> — controla quantos fótons por segundo chegam
(mais luz = mais pares gerados na animação);</li>
<li><b>Velocidade</b> — acelera/desacelera a animação (ex.: 0,5×
para explicar com calma, 2× para demonstração rápida);</li>
<li><b>Pausar</b> — congela o quadro atual (bom para capturar a tela
para um slide);</li>
<li><b>Caixa de mapeamento</b> — realça a correspondência entre as
regiões do corte e os elementos do modelo atômico.</li>
</ul>
""", None))

    # -- Criador de gráficos ----------------------------------------------
    s.append(("criador", "Criador de gráficos", f"""
<h1>Criador de gráficos com zoom de destaque</h1>
{_img("criador_graficos.png", 700)}
<p>(Ferramentas → Criador de gráficos…) Ambiente dedicado a montar
<b>figuras prontas para publicação</b>, independente das abas de
visualização. Os grupos de controles:</p>
<h2>Medições</h2>
<ul>
<li><b>Sincronizar medições</b> — traz para a lista as medições da
sessão; use <b>Todas/Nenhuma</b> para marcar em massa;</li>
<li><b>Fonte</b> — escolha entre os dados FRA ou as curvas I-V.</li>
</ul>
<h2>Gráfico</h2>
<ul>
<li><b>Tipo</b> — Nyquist, Bode etc.;</li>
<li><b>Eixo X/Y logarítmico</b> e <b>Grade</b> — controle fino das
escalas (num Bode, X log é o usual);</li>
</ul>
<h2>Cores</h2>
<ul>
<li><b>Mapa de cores</b> — aplica uma paleta (colormap) a todas as
curvas de uma vez — útil para uma série FRA0F→FRA5F em gradiente;</li>
<li><b>Fundo claro (publicação)</b> — tema branco para artigo;</li>
<li><b>Limpar cores das curvas</b> — volta às cores automáticas.</li>
</ul>
<h2>Marcador, linha e legenda</h2>
<ul>
<li>Símbolo e tamanho do marcador, espessura e estilo da linha;</li>
<li><b>Exibir legenda</b> e a <b>posição</b> dela (ex.: canto
superior direito, fora do gráfico…).</li>
</ul>
<h2>Zoom de destaque (inset)</h2>
<ol>
<li>Marque <b>"Ativar zoom de destaque"</b>;</li>
<li>Clique em <b>"Selecionar região"</b> e arraste um retângulo
sobre a área de interesse no gráfico (tipicamente a região de alta
frequência do Nyquist, colada na origem);</li>
<li>Escolha o <b>alvo do zoom</b> (qual curva/painel amplia) e a
<b>posição do inset</b> na figura;</li>
<li>O retângulo de origem e as linhas de ligação são desenhados
automaticamente, no estilo das figuras de artigos de EIS.</li>
</ol>
<p>Por fim, <b>Atualizar gráfico</b> re-renderiza com os ajustes e
<b>Exportar imagem…</b> salva em PNG/SVG/PDF de alta resolução
(SVG/PDF são vetoriais — ideais para a dissertação em LaTeX).</p>
""", None))

    # -- Menus / arquivos --------------------------------------------------
    s.append(("menus", "Menus e barra de ferramentas", """
<h1>Menus</h1>
<h2>Arquivo</h2>
<ul>
<li><b>Abrir projeto… / Salvar projeto…</b> — sessão completa em um
arquivo <code>.fra</code> (ver tópico "Projetos e arquivos"). Abrir
substitui a sessão atual — o programa pede confirmação;</li>
<li><b>Importar…</b> (Ctrl+I) — abre o arquivo na aba ativa (Dados
ou Curva I-V);</li>
<li><b>Exportar ▸</b>
<ul>
<li><b>Excel…</b> — planilha com uma aba por medição marcada;</li>
<li><b>CSV…</b> — arquivo único autocontido (FRA + I-V), que o
próprio programa reimporta por completo;</li>
<li><b>Imagem do gráfico…</b> — salva a aba de gráfico ativa em
PNG/SVG/PDF;</li>
<li><b>Relatório PDF…</b> — abre a janela de observações e gera um
PDF com os gráficos, os parâmetros dos ajustes e as suas notas do
ensaio;</li>
</ul></li>
<li><b>Sair</b> (Ctrl+Q).</li>
</ul>
<h2>Editar</h2>
<ul><li>Colar na tabela (Ctrl+V), Adicionar 20 linhas, Limpar
tabela.</li></ul>
<h2>Medições</h2>
<ul><li>Espelha as ações do dock Amostras (adicionar, atualizar,
carregar, renomear, duplicar, remover, marcar/desmarcar
todas).</li></ul>
<h2>Análise</h2>
<ul>
<li><b>Validar Kramers-Kronig</b> — atalho para a validação da
medição selecionada (equivale à aba Kramers-Kronig);</li>
<li><b>Ajustar circuito equivalente</b> — leva à aba de ajuste;</li>
<li><b>Correção do Instrumento</b> — abre a biblioteca de correções
(calcular H(f) com padrão conhecido, salvar, importar/exportar);</li>
<li><b>Aplicar correção à medição…</b> — escolhe uma correção da
biblioteca e aplica à medição selecionada (duplique antes para
preservar a original).</li>
</ul>
<h2>Ferramentas</h2>
<ul>
<li><b>Conexão Serial…</b> — recebe pontos de um embarcado
(dispositivo genérico ou AD5933 via ESP32);</li>
<li><b>Criador de gráficos…</b> — figuras de publicação com zoom de
destaque;</li>
<li><b>Simulação do módulo FV</b> — animação didática do módulo.</li>
</ul>
<h2>Exibir</h2>
<ul><li>Mostra/oculta os docks <b>Amostras</b> e <b>Opções de
gráfico</b>. Os docks também podem ser arrastados para outra borda
da janela ou destacados como janelas flutuantes — a posição é
lembrada entre sessões.</li></ul>
<h2>Ajuda</h2>
<ul><li><b>Guia do usuário</b> (F1) — esta janela;
<b>Sobre…</b> — versão do programa e créditos.</li></ul>
<p>A <b>barra de ferramentas</b> repete os comandos mais usados:
abrir/salvar projeto, importar, adicionar medição, KK, ajuste,
correção, serial, criador de gráficos, simulação e relatório.</p>
""", None))

    # -- Projetos e arquivos ----------------------------------------------
    s.append(("arquivos", "Projetos e arquivos", """
<h1>Projetos e formatos de arquivo</h1>
<h2>Projeto .fra (recomendado)</h2>
<p><b>Arquivo → Salvar projeto…</b> grava a sessão <i>inteira</i> em
um único arquivo JSON com extensão <code>.fra</code>: medições (com
flag e anotação de correção), curvas I-V e associações, biblioteca de
correções, ajustes de circuito e de diodo, validações KK, cores e
marcação das amostras. <b>Abrir projeto…</b> restaura tudo — é o
formato para retomar o trabalho exatamente de onde parou.</p>
<h2>CSV autocontido</h2>
<p><b>Exportar CSV</b> gera um arquivo longo com colunas "Medição" e
"Tipo" (EIS/I-V) contendo todas as medições e curvas marcadas; ao
reimportar esse CSV, tudo volta de uma vez. Bom para levar os
<i>dados</i> a outros programas (Excel, Origin, Python).</p>
<h2>Excel / imagem / PDF</h2>
<p>Planilhas para análise externa, figuras dos gráficos e o
relatório PDF com observações.</p>
<h2>O que usar quando?</h2>
<ul>
<li>Continuar o trabalho amanhã → <b>.fra</b>;</li>
<li>Dados brutos para outro software → <b>CSV/Excel</b>;</li>
<li>Figura para o artigo → <b>imagem</b> (use o fundo claro);</li>
<li>Registro do ensaio → <b>relatório PDF</b>.</li>
</ul>
""", None))

    # -- Atalhos -----------------------------------------------------------
    s.append(("atalhos", "Atalhos de teclado", """
<h1>Atalhos de teclado</h1>
<table border="0" cellpadding="4">
<tr><td><b>F1</b></td><td>Guia do usuário (esta janela)</td></tr>
<tr><td><b>Ctrl+O</b></td><td>Abrir projeto</td></tr>
<tr><td><b>Ctrl+S</b></td><td>Salvar projeto</td></tr>
<tr><td><b>Ctrl+I</b></td><td>Importar dados</td></tr>
<tr><td><b>Ctrl+V</b></td><td>Colar na tabela</td></tr>
<tr><td><b>Ctrl+Q</b></td><td>Sair</td></tr>
</table>
<p>Nos gráficos (barra do matplotlib): <b>lupa</b> = zoom por
retângulo, <b>setas cruzadas</b> = pan, <b>casa</b> = visão
original, <b>disquete</b> = salvar figura.</p>
""", None))

    return s


class HelpDialog(QDialog):
    """Janela "Guia do usuário" com árvore de tópicos e conteúdo HTML."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Guia do usuário — {util.APP_NAME}")
        self.resize(1080, 720)
        self.setWindowFlag(Qt.WindowType.Window, True)

        self._sections = _sections()
        self._html: dict[str, str] = {
            sid: html for sid, _t, html, _p in self._sections
        }

        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(240)
        items: dict[str, QTreeWidgetItem] = {}
        for sid, title, _html, parent_id in self._sections:
            if parent_id and parent_id in items:
                item = QTreeWidgetItem(items[parent_id], [title])
            else:
                item = QTreeWidgetItem(self.tree, [title])
            item.setData(0, Qt.ItemDataRole.UserRole, sid)
            items[sid] = item
        self.tree.expandAll()
        self.tree.currentItemChanged.connect(self._on_topic_changed)

        self.browser = QTextBrowser(self)
        self.browser.setOpenExternalLinks(True)
        # Estilo base do conteúdo (legível nos temas claro e escuro).
        self.browser.document().setDefaultStyleSheet("""
            h1 { font-size: 20px; }
            h2 { font-size: 15px; margin-top: 14px; }
            p, li, td { font-size: 13px; }
            code { font-family: Consolas, monospace; }
        """)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.browser)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(splitter)
        layout.addLayout(row)

        self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _on_topic_changed(
        self,
        current: Optional[QTreeWidgetItem],
        _previous: Optional[QTreeWidgetItem],
    ) -> None:
        """Mostra o conteúdo do tópico selecionado."""
        if current is None:
            return
        sid = current.data(0, Qt.ItemDataRole.UserRole)
        self.browser.setHtml(self._html.get(sid, ""))

    def show_topic(self, section_id: str) -> None:
        """Seleciona um tópico pelo id (para ajuda contextual futura)."""
        for i in range(self.tree.topLevelItemCount()):
            stack = [self.tree.topLevelItem(i)]
            while stack:
                item = stack.pop()
                if item.data(0, Qt.ItemDataRole.UserRole) == section_id:
                    self.tree.setCurrentItem(item)
                    return
                stack.extend(
                    item.child(j) for j in range(item.childCount())
                )
