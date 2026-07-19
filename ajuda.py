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

    Args:
        name: Nome do arquivo em ``assets/ajuda`` (ex.: ``"dados.png"``).
        width: Largura de exibição em pixels.

    Returns:
        Tag ``<img>`` centralizada, ou string vazia se a imagem não
        estiver disponível (o guia continua funcional sem as figuras).
    """
    path = Path(util.resource_path(f"assets/ajuda/{name}"))
    if not path.is_file():
        return ""
    return (
        f'<p style="text-align:center;"><img src="{path.as_uri()}" '
        f'width="{width}"/></p>'
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
Bode Fase, Kramers-Kronig, Circuito Equivalente e Comparação.</li>
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
<p>A barra do matplotlib (embaixo de cada gráfico) permite zoom,
pan e salvar a figura. Os gráficos redesenham automaticamente ao
marcar/desmarcar medições ou mudar o estilo no dock Opções.</p>
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

    # -- Comparação --------------------------------------------------------
    s.append(("comparacao", "Aba Comparação", f"""
<h1>Aba Comparação</h1>
{_img("comparacao.png", 720)}
<p>Compara os <b>parâmetros ajustados entre amostras</b> — tanto os
do circuito equivalente quanto os do modelo de diodo — em gráficos
de barras/dispersão. Útil para enxergar a assinatura de cada falha
(ex.: aumento de R<sub>s</sub> por corrosão, queda de R<sub>p</sub>
por PID).</p>
<p>Use <b>Selecionar todas</b> para incluir todas as amostras com
ajuste; a janela "Comparação — modelo de diodo entre amostras"
resume os 5 parâmetros lado a lado.</p>
""", None))

    # -- Correção ----------------------------------------------------------
    s.append(("correcao", "Correção do Instrumento", f"""
<h1>Correção do Instrumento</h1>
{_img("correcao.png", 700)}
<p>Remove do espectro a resposta do próprio instrumento/cabos
(função de transferência H(f)), medida com um <b>padrão conhecido</b>
(ex.: resistor de precisão).</p>
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

    # -- Simulação ---------------------------------------------------------
    s.append(("simulacao", "Simulação do módulo FV", f"""
<h1>Simulação do módulo fotovoltaico</h1>
{_img("simulacao.png", 700)}
<p>(Ferramentas → Simulação do módulo FV) Janela didática com uma
<b>animação do módulo</b>: escolha a tecnologia da célula
(mono-Si, poli-Si, filme fino…) e veja a estrutura de camadas e o
modelo atômico correspondente, com a geração de portadores animada.
Útil para apresentações e para o texto da dissertação.</p>
""", None))

    # -- Criador de gráficos ----------------------------------------------
    s.append(("criador", "Criador de gráficos", f"""
<h1>Criador de gráficos com zoom de destaque</h1>
{_img("criador_graficos.png", 700)}
<p>(Ferramentas → Criador de gráficos…) Monta figuras prontas para
publicação combinando as medições marcadas, com um <b>inset de
zoom</b> (retângulo de destaque ampliado) sobre a região de
interesse — típico em Nyquist para mostrar a região de alta
frequência. Escolha o tipo de gráfico, a região do zoom e exporte em
PNG/SVG de alta resolução.</p>
""", None))

    # -- Menus / arquivos --------------------------------------------------
    s.append(("menus", "Menus e barra de ferramentas", """
<h1>Menus</h1>
<h2>Arquivo</h2>
<ul>
<li><b>Abrir projeto… / Salvar projeto…</b> — sessão completa em um
arquivo <code>.fra</code> (ver tópico "Projetos e arquivos");</li>
<li><b>Importar…</b> — dados para a aba ativa;</li>
<li><b>Exportar ▸ Excel / CSV / Imagem do gráfico / Relatório
PDF</b> — o relatório PDF reúne gráficos, parâmetros de ajuste e um
campo de observações;</li>
<li><b>Sair</b>.</li>
</ul>
<h2>Editar</h2>
<ul><li>Colar na tabela (Ctrl+V), Adicionar 20 linhas, Limpar
tabela.</li></ul>
<h2>Medições</h2>
<ul><li>Espelha as ações do dock Amostras (adicionar, atualizar,
carregar, renomear, duplicar, remover, marcar/desmarcar
todas).</li></ul>
<h2>Análise</h2>
<ul><li>Validar Kramers-Kronig; Ajustar circuito equivalente;
Correção do Instrumento; Aplicar correção à medição.</li></ul>
<h2>Ferramentas</h2>
<ul><li>Conexão Serial…; Criador de gráficos…; Simulação do módulo
FV.</li></ul>
<h2>Exibir</h2>
<ul><li>Mostra/oculta os docks Amostras e Opções de gráfico.</li></ul>
<h2>Ajuda</h2>
<ul><li>Guia do usuário (F1) — esta janela; Sobre…</li></ul>
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
