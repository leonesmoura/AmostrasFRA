"""Gráficos científicos incorporados ao Qt (AMOSTRAS FRA 2.0).

Fornece:

* :class:`PlotCanvas` — widget Qt com ``FigureCanvasQTAgg``, barra de
  navegação do Matplotlib (zoom, pan, salvar imagem) e cursor de dados
  ativável que exibe os valores do ponto mais próximo do clique.
* Funções de plotagem para Nyquist, Bode (magnitude e fase),
  Kramers-Kronig, ajuste de circuito equivalente e comparação de
  medições.
* Temas escuro (interface) e claro (relatórios) via dicionários de
  ``rcParams``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Sequence

import matplotlib

matplotlib.use("QtAgg")

import numpy as np
from matplotlib.axes import Axes
from matplotlib.backend_bases import MouseEvent
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg,
    NavigationToolbar2QT,
)
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QHBoxLayout,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from circuitos import FitResult
from kk import KKResult
from util import IVCurve, Measurement, format_engineering

logger = logging.getLogger(__name__)

#: Cores do tema escuro da aplicação.
DARK_BG = "#1e1e1e"
DARK_AXES_BG = "#252526"
DARK_FG = "#d4d4d4"
DARK_GRID = "#3c3c3c"

#: ``rcParams`` do tema escuro (gráficos da interface).
DARK_RC: dict[str, object] = {
    "figure.facecolor": DARK_BG,
    "figure.edgecolor": DARK_BG,
    "axes.facecolor": DARK_AXES_BG,
    "axes.edgecolor": DARK_FG,
    "axes.labelcolor": DARK_FG,
    "axes.titlecolor": DARK_FG,
    "axes.grid": True,
    "grid.color": DARK_GRID,
    "grid.linestyle": "--",
    "grid.linewidth": 0.6,
    "xtick.color": DARK_FG,
    "ytick.color": DARK_FG,
    "text.color": DARK_FG,
    "legend.facecolor": DARK_AXES_BG,
    "legend.edgecolor": DARK_GRID,
    "legend.framealpha": 0.9,
    "savefig.facecolor": DARK_BG,
    "savefig.edgecolor": DARK_BG,
    "font.size": 9.0,
    "axes.prop_cycle": matplotlib.cycler(
        color=[
            "#4fc3f7", "#ffb74d", "#81c784", "#e57373", "#ba68c8",
            "#f06292", "#4db6ac", "#fff176", "#a1887f", "#90a4ae",
        ]
    ),
}

#: ``rcParams`` do tema claro (relatórios em PDF).
LIGHT_RC: dict[str, object] = {
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "black",
    "axes.labelcolor": "black",
    "axes.titlecolor": "black",
    "axes.grid": True,
    "grid.color": "#c0c0c0",
    "grid.linestyle": "--",
    "grid.linewidth": 0.6,
    "xtick.color": "black",
    "ytick.color": "black",
    "text.color": "black",
    "legend.facecolor": "white",
    "legend.edgecolor": "#808080",
    "savefig.facecolor": "white",
    "font.size": 9.0,
    "axes.prop_cycle": matplotlib.cycler(
        color=[
            "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
            "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
        ]
    ),
}


def apply_dark_theme_to_matplotlib() -> None:
    """Aplica o tema escuro global ao Matplotlib (chamado no início)."""
    matplotlib.rcParams.update(DARK_RC)
    logger.debug("Tema escuro aplicado ao Matplotlib.")


class ColorButton(QPushButton):
    """Botão que exibe e escolhe uma cor via :class:`QColorDialog`.

    Emite :attr:`colorChanged` sempre que a cor muda.  A cor ``None``
    representa "usar o tema" (o botão exibe ``"Automático"``).
    """

    colorChanged = Signal()

    def __init__(
        self,
        color: Optional[str] = None,
        default: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._color: Optional[str] = color
        self._default = default
        self.clicked.connect(self._choose)
        self._update_swatch()

    def color(self) -> Optional[str]:
        """Cor atual (``"#rrggbb"``) ou ``None`` para automática."""
        return self._color

    def set_color(self, color: Optional[str]) -> None:
        """Define a cor e atualiza a aparência do botão."""
        self._color = color
        self._update_swatch()
        self.colorChanged.emit()

    def reset(self) -> None:
        """Restaura a cor padrão (ou automática)."""
        self.set_color(self._default)

    def _choose(self) -> None:
        initial = QColor(self._color or self._default or "#808080")
        chosen = QColorDialog.getColor(initial, self, "Escolher cor")
        if chosen.isValid():
            self.set_color(chosen.name())

    def _update_swatch(self) -> None:
        if self._color is None:
            self.setText("Automático")
            self.setStyleSheet("")
            return
        text_color = (
            "#000000" if QColor(self._color).lightnessF() > 0.55
            else "#ffffff"
        )
        self.setText(self._color)
        self.setStyleSheet(
            f"background-color: {self._color}; color: {text_color};"
        )


#: Opções de marcador exibidas ao usuário (rótulo, símbolo).
MARKER_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Círculo (o)", "o"),
    ("Quadrado (s)", "s"),
    ("Triângulo (^)", "^"),
    ("Triângulo inv. (v)", "v"),
    ("Losango (D)", "D"),
    ("X", "x"),
    ("Cruz (+)", "+"),
    ("Estrela (*)", "*"),
    ("Nenhum", ""),
)

#: Opções de estilo de linha exibidas ao usuário (rótulo, estilo).
LINE_STYLE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Contínua", "-"),
    ("Tracejada", "--"),
    ("Pontilhada", ":"),
    ("Traço-ponto", "-."),
    ("Nenhuma", "none"),
)


@dataclass
class PlotStyle:
    """Opções de estilo configuráveis pelo usuário.

    Attributes:
        marker: Símbolo do marcador ('o', 's', '^', 'v', 'D', 'x',
            '+', '*' ou '' para nenhum).
        marker_size: Tamanho do marcador, em pontos.
        line_width: Espessura da linha, em pontos.
        line_style: Estilo de linha ('-', '--', ':', '-.' ou 'none').
        show_grid: Exibe a grade dos gráficos.
        figure_color: Cor de fundo da figura (borda externa) ou
            ``None`` para manter o tema.
        axes_color: Cor de fundo da área de plotagem ou ``None`` para
            manter o tema.
        grid_color: Cor da grade ou ``None`` para manter o tema.
        text_color: Cor de rótulos, títulos e marcações dos eixos, ou
            ``None`` para manter o tema.
        colors: Mapeamento ``{nome da curva: cor}`` para cores por
            curva definidas pelo usuário.  Curvas ausentes usam as
            cores automáticas.
    """

    marker: str = "o"
    marker_size: float = 4.5
    line_width: float = 1.4
    line_style: str = "-"
    show_grid: bool = True
    figure_color: Optional[str] = None
    axes_color: Optional[str] = None
    grid_color: Optional[str] = None
    text_color: Optional[str] = None
    colors: dict[str, object] = field(default_factory=dict)

    def line_kwargs(self) -> dict[str, object]:
        """Argumentos de estilo para ``Axes.plot``."""
        return {
            "marker": self.marker if self.marker else "",
            "markersize": self.marker_size,
            "linewidth": self.line_width,
            "linestyle": self.line_style if self.line_style else "none",
        }

    def line_kwargs_for(self, name: str) -> dict[str, object]:
        """Argumentos de ``Axes.plot`` para a curva ``name``.

        Inclui a cor personalizada quando definida em :attr:`colors`.
        """
        kwargs = self.line_kwargs()
        color = self.colors.get(name)
        if color is not None:
            kwargs["color"] = color
        return kwargs


# ---------------------------------------------------------------------------
# Cursor de dados
# ---------------------------------------------------------------------------
class DataCursor:
    """Cursor que anota o ponto de dados mais próximo do clique.

    O cursor considera todas as linhas (:class:`Line2D`) dos eixos sob
    o clique.  Linhas plotadas pelas funções deste módulo carregam o
    atributo ``_fra_freq`` com a frequência de cada ponto, exibida na
    anotação quando disponível.
    """

    _PICK_RADIUS_PX: float = 18.0

    def __init__(
        self,
        canvas: FigureCanvasQTAgg,
        toolbar: NavigationToolbar2QT,
    ) -> None:
        self._canvas = canvas
        self._toolbar = toolbar
        self._active = False
        self._annotation = None
        self._cid = canvas.mpl_connect(
            "button_press_event", self._on_click
        )

    @property
    def active(self) -> bool:
        """Indica se o cursor está ativo."""
        return self._active

    def set_active(self, active: bool) -> None:
        """Ativa/desativa o cursor, limpando a anotação atual."""
        self._active = active
        if not active:
            self.clear()

    def clear(self) -> None:
        """Remove a anotação atual, se houver."""
        if self._annotation is not None:
            try:
                self._annotation.remove()
            except (ValueError, NotImplementedError):
                pass
            self._annotation = None
            self._canvas.draw_idle()

    def _on_click(self, event: MouseEvent) -> None:
        """Trata o clique do mouse, anotando o ponto mais próximo."""
        if not self._active or event.inaxes is None:
            return
        if self._toolbar.mode:
            # Zoom ou pan ativos: não interferir.
            return
        ax = event.inaxes
        best: Optional[tuple[float, float, float, Optional[float]]] = None
        for line in ax.get_lines():
            if not isinstance(line, Line2D):
                continue
            if line.get_transform() is not ax.transData:
                # Linhas de referência (axhline/axvline) usam
                # coordenadas mistas; não são pontos de dados.
                continue
            xdata = np.asarray(line.get_xdata(), dtype=float)
            ydata = np.asarray(line.get_ydata(), dtype=float)
            if xdata.size == 0:
                continue
            points = ax.transData.transform(
                np.column_stack([xdata, ydata])
            )
            dx = points[:, 0] - event.x
            dy = points[:, 1] - event.y
            distances = np.hypot(dx, dy)
            index = int(np.argmin(distances))
            distance = float(distances[index])
            if distance > self._PICK_RADIUS_PX:
                continue
            freq_array = getattr(line, "_fra_freq", None)
            freq_value: Optional[float] = None
            if freq_array is not None and index < len(freq_array):
                freq_value = float(freq_array[index])
            if best is None or distance < best[0]:
                best = (
                    distance,
                    float(xdata[index]),
                    float(ydata[index]),
                    freq_value,
                )
        if best is None:
            self.clear()
            return
        _, x_val, y_val, freq_val = best
        lines = [f"x = {x_val:.6g}", f"y = {y_val:.6g}"]
        if freq_val is not None:
            lines.insert(0, f"f = {format_engineering(freq_val, 'Hz')}")
        text = "\n".join(lines)

        if self._annotation is not None:
            try:
                self._annotation.remove()
            except (ValueError, NotImplementedError):
                pass
        self._annotation = ax.annotate(
            text,
            xy=(x_val, y_val),
            xytext=(12, 12),
            textcoords="offset points",
            fontsize=8,
            bbox={
                "boxstyle": "round,pad=0.4",
                "fc": DARK_AXES_BG,
                "ec": "#4fc3f7",
                "alpha": 0.95,
            },
            arrowprops={"arrowstyle": "->", "color": "#4fc3f7"},
        )
        self._canvas.draw_idle()


# ---------------------------------------------------------------------------
# Widget de canvas
# ---------------------------------------------------------------------------
class PlotCanvas(QWidget):
    """Canvas Matplotlib incorporado ao Qt com toolbar e cursor.

    A barra de navegação padrão fornece zoom, pan, ajuste de eixos e
    salvamento de imagem.  Um botão adicional ativa o cursor de dados.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.figure = Figure(constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.cursor = DataCursor(self.canvas, self.toolbar)

        self._cursor_button = QToolButton(self)
        self._cursor_button.setText("Cursor")
        self._cursor_button.setToolTip(
            "Ativa o cursor de dados: clique próximo a um ponto para "
            "ver frequência e valores."
        )
        self._cursor_button.setCheckable(True)
        self._cursor_button.toggled.connect(self.cursor.set_active)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.addWidget(self.toolbar, 1)
        top_bar.addWidget(
            self._cursor_button, 0, Qt.AlignmentFlag.AlignRight
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addLayout(top_bar)
        layout.addWidget(self.canvas, 1)

    def clear(self) -> None:
        """Limpa a figura e a anotação do cursor."""
        self.cursor.clear()
        for ax in list(self.figure.axes):
            # Restaura escala linear antes de limpar para evitar o
            # aviso de xlim não positivo em eixos logarítmicos.
            try:
                ax.set_xscale("linear")
                ax.set_yscale("linear")
            except (ValueError, RuntimeError):
                pass
        self.figure.clear()

    def draw(self) -> None:
        """Redesenha o canvas."""
        self.canvas.draw_idle()


# ---------------------------------------------------------------------------
# Funções de plotagem
# ---------------------------------------------------------------------------
def mathtext_to_pixmap(
    expression: str,
    fontsize: float = 20.0,
    color: Optional[str] = None,
    dpi: int = 220,
) -> QPixmap:
    """Renderiza uma expressão *mathtext* (LaTeX) do Matplotlib em pixmap.

    Produz uma imagem nítida (fundo transparente) da fórmula, própria
    para exibir num ``QLabel`` — muito mais legível que HTML com
    subscritos.

    Args:
        expression: Expressão em sintaxe mathtext, entre ``$…$``.
        fontsize: Tamanho da fonte (em pontos).
        color: Cor do texto (qualquer cor Matplotlib); ``None`` usa a
            cor de texto do tema atual.
        dpi: Resolução de renderização (maior = mais nítido).

    Returns:
        :class:`~PySide6.QtGui.QPixmap` com a fórmula (densidade de
        pixels ajustada para exibição em tamanho lógico correto).
    """
    import io

    from matplotlib.backends.backend_agg import FigureCanvasAgg

    if color is None:
        color = matplotlib.rcParams.get("text.color", "black")
    fig = Figure(figsize=(0.1, 0.1))
    fig.patch.set_alpha(0.0)
    fig.text(0.0, 0.0, expression, fontsize=fontsize, color=color)
    FigureCanvasAgg(fig)
    buffer = io.BytesIO()
    fig.savefig(
        buffer,
        format="png",
        dpi=dpi,
        transparent=True,
        bbox_inches="tight",
        pad_inches=0.06,
    )
    buffer.seek(0)
    pixmap = QPixmap()
    pixmap.loadFromData(buffer.getvalue(), "PNG")
    # Renderizado em dpi alto; ajusta a densidade para o tamanho lógico
    # ficar coerente e a imagem sair nítida em telas de alta resolução.
    pixmap.setDevicePixelRatio(dpi / 100.0)
    return pixmap


def _attach_frequency(line: Line2D, frequency: np.ndarray) -> None:
    """Anexa o vetor de frequências à linha, para o cursor de dados."""
    line._fra_freq = np.asarray(frequency, dtype=float)  # type: ignore[attr-defined]


def apply_background(ax: Axes, style: PlotStyle) -> None:
    """Aplica as cores de fundo, grade e texto do estilo aos eixos.

    Cores ``None`` mantêm o tema atual.  A cor da figura afeta toda a
    figura à qual ``ax`` pertence.

    Args:
        ax: Eixos de destino.
        style: Estilo com as cores desejadas.
    """
    if style.axes_color is not None:
        ax.set_facecolor(style.axes_color)
    if style.figure_color is not None and ax.figure is not None:
        ax.figure.set_facecolor(style.figure_color)
    if style.grid_color is not None:
        ax.grid(color=style.grid_color)
    if style.text_color is not None:
        color = style.text_color
        ax.title.set_color(color)
        ax.xaxis.label.set_color(color)
        ax.yaxis.label.set_color(color)
        ax.tick_params(axis="both", colors=color)
        for spine in ax.spines.values():
            spine.set_edgecolor(color)
    legend = ax.get_legend()
    if legend is not None:
        if style.axes_color is not None:
            legend.get_frame().set_facecolor(style.axes_color)
        if style.text_color is not None:
            for text in legend.get_texts():
                text.set_color(style.text_color)


def _finalize_axes(ax: Axes, style: PlotStyle) -> None:
    """Aplica grade, legenda e cores de fundo conforme o estilo."""
    ax.grid(style.show_grid, which="both")
    handles, labels = ax.get_legend_handles_labels()
    if labels:
        ax.legend(loc="best", fontsize=8)
    apply_background(ax, style)


def plot_nyquist(
    ax: Axes,
    measurements: Sequence[Measurement],
    style: Optional[PlotStyle] = None,
    title: str = "Diagrama de Nyquist",
) -> None:
    """Plota o diagrama de Nyquist (``Z'`` × ``-Z''``).

    O aspecto dos eixos é mantido igual (círculos aparecem como
    círculos), conforme a convenção de EIS.

    Args:
        ax: Eixos de destino.
        measurements: Medições a plotar (cores automáticas).
        style: Estilo de marcadores/linhas (opcional).
        title: Título do gráfico.
    """
    style = style or PlotStyle()
    for m in measurements:
        line, = ax.plot(
            m.z_real,
            m.minus_z_imag,
            label=m.name,
            **style.line_kwargs_for(m.name),
        )
        _attach_frequency(line, m.frequency)
    ax.set_xlabel("Z' (Ω)")
    ax.set_ylabel("-Z'' (Ω)")
    ax.set_title(title)
    ax.set_aspect("equal", adjustable="datalim")
    _finalize_axes(ax, style)


def plot_bode_magnitude(
    ax: Axes,
    measurements: Sequence[Measurement],
    style: Optional[PlotStyle] = None,
    title: str = "Bode — Magnitude",
) -> None:
    """Plota ``|Z|`` × frequência em escala log-log.

    Args:
        ax: Eixos de destino.
        measurements: Medições a plotar.
        style: Estilo de marcadores/linhas (opcional).
        title: Título do gráfico.
    """
    style = style or PlotStyle()
    for m in measurements:
        line, = ax.plot(
            m.frequency,
            m.magnitude,
            label=m.name,
            **style.line_kwargs_for(m.name),
        )
        _attach_frequency(line, m.frequency)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Frequência (Hz)")
    ax.set_ylabel("|Z| (Ω)")
    ax.set_title(title)
    _finalize_axes(ax, style)


def plot_bode_phase(
    ax: Axes,
    measurements: Sequence[Measurement],
    style: Optional[PlotStyle] = None,
    title: str = "Bode — Fase",
) -> None:
    """Plota a fase × frequência em escala semilogarítmica.

    Args:
        ax: Eixos de destino.
        measurements: Medições a plotar.
        style: Estilo de marcadores/linhas (opcional).
        title: Título do gráfico.
    """
    style = style or PlotStyle()
    for m in measurements:
        line, = ax.plot(
            m.frequency,
            m.phase_deg,
            label=m.name,
            **style.line_kwargs_for(m.name),
        )
        _attach_frequency(line, m.frequency)
    ax.set_xscale("log")
    ax.set_xlabel("Frequência (Hz)")
    ax.set_ylabel("Fase (°)")
    ax.set_title(title)
    _finalize_axes(ax, style)


def plot_iv(
    ax: Axes,
    curves: Sequence[IVCurve],
    style: Optional[PlotStyle] = None,
    title: str = "Curva I-V",
    annotate_pmax: bool = False,
) -> None:
    """Plota curvas I×V do módulo fotovoltaico.

    Args:
        ax: Eixos de destino.
        curves: Curvas I-V a plotar (cores automáticas).
        style: Estilo de marcadores/linhas (opcional).
        title: Título do gráfico.
        annotate_pmax: Marca o ponto de máxima potência de cada curva.
    """
    style = style or PlotStyle()
    for curve in curves:
        line, = ax.plot(
            curve.voltage,
            curve.current,
            label=curve.name,
            **style.line_kwargs_for(curve.name),
        )
        if annotate_pmax:
            ax.plot(
                [curve.v_mp],
                [curve.i_mp],
                marker="x",
                markersize=9,
                markeredgewidth=2.0,
                linestyle="none",
                color=line.get_color(),
            )
    ax.set_xlabel("Tensão (V)")
    ax.set_ylabel("Corrente (A)")
    ax.set_title(title)
    _finalize_axes(ax, style)


def plot_pv(
    ax: Axes,
    curves: Sequence[IVCurve],
    style: Optional[PlotStyle] = None,
    title: str = "Potência × Tensão",
    annotate_pmax: bool = False,
) -> None:
    """Plota curvas P×V do módulo fotovoltaico.

    Args:
        ax: Eixos de destino.
        curves: Curvas I-V a plotar (potência ``P = V·I``).
        style: Estilo de marcadores/linhas (opcional).
        title: Título do gráfico.
        annotate_pmax: Marca o ponto de máxima potência de cada curva.
    """
    style = style or PlotStyle()
    for curve in curves:
        line, = ax.plot(
            curve.voltage,
            curve.power,
            label=curve.name,
            **style.line_kwargs_for(curve.name),
        )
        if annotate_pmax:
            ax.plot(
                [curve.v_mp],
                [curve.p_max],
                marker="x",
                markersize=9,
                markeredgewidth=2.0,
                linestyle="none",
                color=line.get_color(),
            )
    ax.set_xlabel("Tensão (V)")
    ax.set_ylabel("Potência (W)")
    ax.set_title(title)
    _finalize_axes(ax, style)


def plot_kk(
    figure: Figure,
    result: KKResult,
    style: Optional[PlotStyle] = None,
) -> None:
    """Plota a comparação experimental × reconstrução de Kramers-Kronig.

    Quatro painéis: parte real × f, parte imaginária × f, resíduos
    relativos (%) × f e Nyquist sobreposto.

    Args:
        figure: Figura de destino (será preenchida; limpe antes).
        result: Resultado de :func:`kk.kk_transform`.
        style: Estilo de marcadores/linhas (opcional).
    """
    style = style or PlotStyle()
    axes = figure.subplots(2, 2)
    ax_re, ax_im = axes[0][0], axes[0][1]
    ax_res, ax_ny = axes[1][0], axes[1][1]
    freq = result.frequency

    marker_kwargs = {
        "marker": style.marker or "o",
        "markersize": style.marker_size,
        "linestyle": "none",
    }
    line_kwargs = {"linewidth": max(style.line_width, 1.0)}

    line, = ax_re.plot(
        freq, result.z_real_exp, label="Z' experimental",
        **marker_kwargs,
    )
    _attach_frequency(line, freq)
    line, = ax_re.plot(
        freq, result.z_real_kk, label="Z' reconstruído (KK)",
        **line_kwargs,
    )
    _attach_frequency(line, freq)
    ax_re.set_xscale("log")
    ax_re.set_xlabel("Frequência (Hz)")
    ax_re.set_ylabel("Z' (Ω)")
    ax_re.set_title("Parte real")

    line, = ax_im.plot(
        freq, -result.z_imag_exp, label="-Z'' experimental",
        **marker_kwargs,
    )
    _attach_frequency(line, freq)
    line, = ax_im.plot(
        freq, -result.z_imag_kk, label="-Z'' reconstruído (KK)",
        **line_kwargs,
    )
    _attach_frequency(line, freq)
    ax_im.set_xscale("log")
    ax_im.set_xlabel("Frequência (Hz)")
    ax_im.set_ylabel("-Z'' (Ω)")
    ax_im.set_title("Parte imaginária")

    line, = ax_res.plot(
        freq, result.residual_real_pct, label="Resíduo Z' (%)",
        marker=".", markersize=4, linewidth=1.0,
    )
    _attach_frequency(line, freq)
    line, = ax_res.plot(
        freq, result.residual_imag_pct, label="Resíduo Z'' (%)",
        marker=".", markersize=4, linewidth=1.0,
    )
    _attach_frequency(line, freq)
    ax_res.axhline(0.0, color="#888888", linewidth=0.8)
    ax_res.set_xscale("log")
    ax_res.set_xlabel("Frequência (Hz)")
    ax_res.set_ylabel("Resíduo (% de |Z|)")
    ax_res.set_title("Resíduos relativos")

    line, = ax_ny.plot(
        result.z_real_exp, -result.z_imag_exp, label="Experimental",
        **marker_kwargs,
    )
    _attach_frequency(line, freq)
    line, = ax_ny.plot(
        result.z_real_kk, -result.z_imag_kk,
        label="Reconstruído (KK)", **line_kwargs,
    )
    _attach_frequency(line, freq)
    ax_ny.set_xlabel("Z' (Ω)")
    ax_ny.set_ylabel("-Z'' (Ω)")
    ax_ny.set_title("Nyquist")
    ax_ny.set_aspect("equal", adjustable="datalim")

    for ax in (ax_re, ax_im, ax_res, ax_ny):
        _finalize_axes(ax, style)
    figure.suptitle(
        f"Validação de Kramers-Kronig — {result.measurement_name}",
        fontsize=11,
    )


def plot_circuit_fit(
    figure: Figure,
    fit: FitResult,
    style: Optional[PlotStyle] = None,
) -> None:
    """Plota o resultado do ajuste de circuito equivalente.

    Painel esquerdo: Nyquist (dados × modelo).  Painéis direitos:
    Bode magnitude e fase (dados × modelo).

    Args:
        figure: Figura de destino (será preenchida; limpe antes).
        fit: Resultado de :func:`circuitos.fit_circuit`.
        style: Estilo de marcadores/linhas (opcional).
    """
    style = style or PlotStyle()
    gs = figure.add_gridspec(2, 2)
    ax_ny = figure.add_subplot(gs[:, 0])
    ax_mag = figure.add_subplot(gs[0, 1])
    ax_ph = figure.add_subplot(gs[1, 1])

    freq = fit.frequency
    z_exp = fit.z_exp
    z_fit = fit.z_fit

    marker_kwargs = {
        "marker": style.marker or "o",
        "markersize": style.marker_size,
        "linestyle": "none",
    }
    line_kwargs = {"linewidth": max(style.line_width, 1.2)}

    line, = ax_ny.plot(
        np.real(z_exp), -np.imag(z_exp), label="Experimental",
        **marker_kwargs,
    )
    _attach_frequency(line, freq)
    line, = ax_ny.plot(
        np.real(z_fit), -np.imag(z_fit), label="Modelo ajustado",
        **line_kwargs,
    )
    _attach_frequency(line, freq)
    ax_ny.set_xlabel("Z' (Ω)")
    ax_ny.set_ylabel("-Z'' (Ω)")
    ax_ny.set_title("Nyquist")
    ax_ny.set_aspect("equal", adjustable="datalim")

    line, = ax_mag.plot(
        freq, np.abs(z_exp), label="Experimental", **marker_kwargs,
    )
    _attach_frequency(line, freq)
    line, = ax_mag.plot(
        freq, np.abs(z_fit), label="Modelo", **line_kwargs,
    )
    _attach_frequency(line, freq)
    ax_mag.set_xscale("log")
    ax_mag.set_yscale("log")
    ax_mag.set_xlabel("Frequência (Hz)")
    ax_mag.set_ylabel("|Z| (Ω)")
    ax_mag.set_title("Bode — Magnitude")

    line, = ax_ph.plot(
        freq, np.degrees(np.angle(z_exp)), label="Experimental",
        **marker_kwargs,
    )
    _attach_frequency(line, freq)
    line, = ax_ph.plot(
        freq, np.degrees(np.angle(z_fit)), label="Modelo",
        **line_kwargs,
    )
    _attach_frequency(line, freq)
    ax_ph.set_xscale("log")
    ax_ph.set_xlabel("Frequência (Hz)")
    ax_ph.set_ylabel("Fase (°)")
    ax_ph.set_title("Bode — Fase")

    for ax in (ax_ny, ax_mag, ax_ph):
        _finalize_axes(ax, style)

    params_text = "\n".join(
        f"{name} = {value:.5g} {unit}".rstrip()
        for name, unit, value in zip(
            fit.param_names, fit.param_units, fit.param_values
        )
    )
    stats_text = (
        f"χ² = {fit.chi_squared:.4g}\n"
        f"RMSE = {fit.rmse:.4g} Ω\n"
        f"R² = {fit.r_squared:.6f}"
    )
    ax_ny.text(
        0.02,
        0.98,
        f"{fit.model_name}\n{params_text}\n{stats_text}",
        transform=ax_ny.transAxes,
        va="top",
        ha="left",
        fontsize=7.5,
        bbox={
            "boxstyle": "round,pad=0.4",
            "fc": _legend_color("legend.facecolor", ax_ny),
            "ec": _legend_color("legend.edgecolor", ax_ny),
            "alpha": 0.9,
        },
    )
    figure.suptitle(
        f"Ajuste de circuito — {fit.measurement_name} "
        f"({fit.circuit_string})",
        fontsize=11,
    )


def _legend_color(rc_key: str, ax) -> object:
    """Cor de legenda dos rcParams, resolvendo o valor ``"inherit"``.

    O padrão do matplotlib para ``legend.facecolor``/``edgecolor`` é a
    string ``"inherit"``, que um ``bbox`` de ``Axes.text`` não aceita.

    Args:
        rc_key: Chave do rcParams (``"legend.facecolor"`` ou
            ``"legend.edgecolor"``).
        ax: Eixos de onde herdar a cor quando necessário.

    Returns:
        Uma cor válida para o matplotlib.
    """
    value = matplotlib.rcParams[rc_key]
    if value != "inherit":
        return value
    if rc_key == "legend.facecolor":
        return ax.get_facecolor()
    return matplotlib.rcParams["axes.edgecolor"]


#: Nomes e unidades dos parâmetros do modelo de diodo (para rótulos).
_IV_PARAM_NAMES: tuple[str, ...] = ("I_L", "I_0", "R_s", "R_p", "a")
_IV_PARAM_UNITS: tuple[str, ...] = ("A", "A", "Ω", "Ω", "V")


def plot_diode_fit(
    figure: Figure,
    fit: "IVFitResult",
    style: Optional[PlotStyle] = None,
) -> None:
    """Plota o ajuste do modelo de diodo único à curva I-V.

    Painel principal: corrente experimental (marcadores) × modelo
    ajustado (linha).  Painel inferior: resíduos (dados − modelo).

    Args:
        figure: Figura de destino (será preenchida; limpe antes).
        fit: Resultado de :func:`iv_model.fit_single_diode`.
        style: Estilo de marcadores/linhas (opcional).
    """
    style = style or PlotStyle()
    gs = figure.add_gridspec(3, 1, hspace=0.08)
    ax = figure.add_subplot(gs[:2, 0])
    ax_res = figure.add_subplot(gs[2, 0], sharex=ax)

    v = fit.voltage
    ax.plot(
        v, fit.current_exp, label="Experimental",
        marker=style.marker or "o", markersize=style.marker_size,
        linestyle="none",
    )
    ax.plot(
        v, fit.current_fit, label="Modelo ajustado",
        linewidth=max(style.line_width, 1.4),
    )
    ax.set_ylabel("Corrente (A)")
    tipo = "escura (dark I-V)" if fit.dark else "iluminada"
    ax.set_title(f"Ajuste de diodo único — {fit.curve_name} ({tipo})")
    ax.tick_params(labelbottom=False)

    residual = fit.current_exp - fit.current_fit
    ax_res.plot(
        v, residual, marker=".", markersize=4, linestyle="-",
        linewidth=0.8,
    )
    ax_res.axhline(0.0, color="gray", linewidth=0.8, linestyle=":")
    ax_res.set_xlabel("Tensão (V)")
    ax_res.set_ylabel("Resíduo (A)")

    for axis in (ax, ax_res):
        _finalize_axes(axis, style)

    params_text = "\n".join(
        f"{name} = {value:.4g} {unit}".rstrip()
        for name, unit, value in zip(
            _IV_PARAM_NAMES, _IV_PARAM_UNITS, fit.param_values,
        )
    )
    stats_text = (
        f"RMSE = {fit.rmse:.4g} A\n"
        f"R² = {fit.r_squared:.6f}"
    )
    ax.text(
        0.02,
        0.02,
        f"{params_text}\n{stats_text}",
        transform=ax.transAxes,
        va="bottom",
        ha="left",
        fontsize=7.5,
        bbox={
            "boxstyle": "round,pad=0.4",
            "fc": _legend_color("legend.facecolor", ax),
            "ec": _legend_color("legend.edgecolor", ax),
            "alpha": 0.9,
        },
    )


def plot_comparison(
    figure: Figure,
    measurements: Sequence[Measurement],
    kind: str,
    style: Optional[PlotStyle] = None,
) -> None:
    """Plota a comparação sobreposta de várias medições.

    Args:
        figure: Figura de destino (será preenchida; limpe antes).
        measurements: Medições selecionadas para comparação.
        kind: ``"nyquist"``, ``"bode_mag"``, ``"bode_phase"`` ou
            ``"bode_completo"`` (magnitude e fase lado a lado).
        style: Estilo de marcadores/linhas (opcional).

    Raises:
        ValueError: Se ``kind`` for desconhecido.
    """
    style = style or PlotStyle()
    if kind == "nyquist":
        ax = figure.add_subplot(111)
        plot_nyquist(ax, measurements, style, title="Comparação — Nyquist")
    elif kind == "bode_mag":
        ax = figure.add_subplot(111)
        plot_bode_magnitude(
            ax, measurements, style, title="Comparação — |Z|"
        )
    elif kind == "bode_phase":
        ax = figure.add_subplot(111)
        plot_bode_phase(
            ax, measurements, style, title="Comparação — Fase"
        )
    elif kind == "bode_completo":
        ax1, ax2 = figure.subplots(1, 2)
        plot_bode_magnitude(
            ax1, measurements, style, title="Comparação — |Z|"
        )
        plot_bode_phase(ax2, measurements, style, title="Comparação — Fase")
    else:
        raise ValueError(f"Tipo de comparação desconhecido: '{kind}'.")
