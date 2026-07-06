"""Criador de gráficos personalizados (AMOSTRAS FRA 2.0).

Janela para compor gráficos de publicação com qualquer quantidade de
medições (por exemplo, ganho e fase de Bode de 30 amostras):

* Tipos: Bode completo (|Z| + fase empilhados), Bode magnitude,
  Bode fase e Nyquist;
* Paletas de cor adequadas a muitas curvas (viridis, plasma, tab20,
  coolwarm, ...);
* Título, rótulos dos eixos, escalas log/linear, grade e legenda
  (posição e número de colunas) configuráveis;
* **Zoom de destaque (inset)**: selecione a região de interesse
  arrastando um retângulo sobre o gráfico — ela é ampliada em um
  quadro interno com linhas de indicação
  (``Axes.indicate_inset_zoom``);
* Exportação da figura em PNG, PDF ou SVG.

Podem ser abertas várias janelas simultaneamente, cada uma com sua
própria configuração.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

import matplotlib
import numpy as np
from matplotlib.axes import Axes
from matplotlib.widgets import RectangleSelector
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import exportacao
from plots import (
    LINE_STYLE_OPTIONS,
    MARKER_OPTIONS,
    ColorButton,
    PlotCanvas,
    PlotStyle,
    plot_bode_magnitude,
    plot_bode_phase,
    plot_iv,
    plot_nyquist,
    plot_pv,
)
from util import IVCurve, Measurement, parse_number

logger = logging.getLogger(__name__)

#: Tipos de gráfico de impedância (rótulo, chave).
_CHART_KINDS: tuple[tuple[str, str], ...] = (
    ("Bode completo (|Z| + Fase)", "bode_full"),
    ("Bode — Magnitude (ganho)", "bode_mag"),
    ("Bode — Fase", "bode_phase"),
    ("Nyquist", "nyquist"),
)

#: Tipos de gráfico de curva I-V (rótulo, chave).
_IV_KINDS: tuple[tuple[str, str], ...] = (
    ("Curva I×V", "iv"),
    ("Potência P×V", "pv"),
    ("I×V + P×V (dois painéis)", "iv_pv"),
)

#: Tipos com dois painéis (habilitam a escolha do painel do zoom).
_TWO_PANEL_KINDS: frozenset[str] = frozenset({"bode_full", "iv_pv"})

#: Paletas de cor (rótulo, nome do colormap ou None p/ ciclo padrão).
_COLORMAPS: tuple[tuple[str, Optional[str]], ...] = (
    ("Automático (ciclo padrão)", None),
    ("Viridis (sequencial)", "viridis"),
    ("Plasma (sequencial)", "plasma"),
    ("Coolwarm (divergente)", "coolwarm"),
    ("Tab20 (categórico)", "tab20"),
    ("Turbo (arco-íris)", "turbo"),
)

#: Posições da legenda (rótulo, argumento do Matplotlib).
_LEGEND_POSITIONS: tuple[tuple[str, str], ...] = (
    ("Melhor posição", "best"),
    ("Superior direita", "upper right"),
    ("Superior esquerda", "upper left"),
    ("Inferior direita", "lower right"),
    ("Inferior esquerda", "lower left"),
    ("Fora, à direita", "__outside__"),
)

#: Cantos do zoom de destaque (rótulo, chave).
_INSET_POSITIONS: tuple[tuple[str, str], ...] = (
    ("Superior direito", "ne"),
    ("Superior esquerdo", "nw"),
    ("Inferior direito", "se"),
    ("Inferior esquerdo", "sw"),
)


class ChartBuilderDialog(QDialog):
    """Janela "Criador de gráficos".

    Args:
        parent: Widget pai.
        measurements_provider: Função que retorna o dicionário atual
            de medições de impedância da sessão.
        iv_provider: Função que retorna o dicionário atual de curvas
            I-V da sessão (opcional).
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        measurements_provider: Callable[[], dict[str, Measurement]],
        iv_provider: Optional[
            Callable[[], dict[str, IVCurve]]
        ] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Criador de gráficos")
        self.resize(1280, 780)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self._provider = measurements_provider
        self._iv_provider = iv_provider
        self._axes: list[Axes] = []
        self._inset_ax: Optional[Axes] = None
        self._selector: Optional[RectangleSelector] = None
        #: Cores manuais por curva (``{nome: "#rrggbb"}``).
        self._curve_colors: dict[str, str] = {}

        # -- Medições --------------------------------------------------
        self.measurement_list = QListWidget(self)
        self.measurement_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.measurement_list.itemChanged.connect(
            lambda _item: self.refresh()
        )
        self.measurement_list.itemDoubleClicked.connect(
            self._on_curve_double_clicked
        )
        sync_button = QPushButton("Sincronizar medições", self)
        sync_button.setToolTip(
            "Recarrega a lista com as medições atuais da sessão."
        )
        sync_button.clicked.connect(self.sync_measurements)
        all_button = QPushButton("Todas", self)
        all_button.clicked.connect(lambda: self._set_all(True))
        none_button = QPushButton("Nenhuma", self)
        none_button.clicked.connect(lambda: self._set_all(False))

        # -- Fonte de dados, tipo e aparência ------------------------------
        self.source_combo = QComboBox(self)
        self.source_combo.addItem("Impedância (EIS)", "eis")
        if iv_provider is not None:
            self.source_combo.addItem("Curva I-V", "iv")
        self.source_combo.currentIndexChanged.connect(
            self._on_source_changed
        )

        self.kind_combo = QComboBox(self)
        for label, kind in _CHART_KINDS:
            self.kind_combo.addItem(label, kind)
        self.kind_combo.currentIndexChanged.connect(
            self._on_kind_changed
        )

        self.title_edit = QLineEdit(self)
        self.title_edit.setPlaceholderText("(título automático)")
        self.title_edit.editingFinished.connect(self.refresh)
        self.xlabel_edit = QLineEdit(self)
        self.xlabel_edit.setPlaceholderText("(rótulo automático)")
        self.xlabel_edit.editingFinished.connect(self.refresh)
        self.ylabel_edit = QLineEdit(self)
        self.ylabel_edit.setPlaceholderText("(rótulo automático)")
        self.ylabel_edit.editingFinished.connect(self.refresh)

        self.xlog_checkbox = QCheckBox("Eixo X logarítmico", self)
        self.xlog_checkbox.toggled.connect(
            lambda _checked: self.refresh()
        )
        self.ylog_checkbox = QCheckBox("Eixo Y logarítmico", self)
        self.ylog_checkbox.toggled.connect(
            lambda _checked: self.refresh()
        )
        self.grid_checkbox = QCheckBox("Grade", self)
        self.grid_checkbox.setChecked(True)
        self.grid_checkbox.toggled.connect(
            lambda _checked: self.refresh()
        )

        self.colormap_combo = QComboBox(self)
        for label, name in _COLORMAPS:
            self.colormap_combo.addItem(label, name)
        self.colormap_combo.currentIndexChanged.connect(
            lambda _index: self.refresh()
        )

        # Cores de fundo (padrão: tema escuro dos gráficos).
        self.figure_color_button = ColorButton(
            color="#1e1e1e", default="#1e1e1e", parent=self
        )
        self.axes_color_button = ColorButton(
            color="#252526", default="#252526", parent=self
        )
        self.grid_color_button = ColorButton(
            color="#3c3c3c", default="#3c3c3c", parent=self
        )
        self.text_color_button = ColorButton(
            color="#d4d4d4", default="#d4d4d4", parent=self
        )
        for button in (
            self.figure_color_button,
            self.axes_color_button,
            self.grid_color_button,
            self.text_color_button,
        ):
            button.colorChanged.connect(self.refresh)

        light_button = QPushButton("Fundo claro (publicação)", self)
        light_button.clicked.connect(self._apply_light_preset)
        clear_colors_button = QPushButton("Limpar cores das curvas", self)
        clear_colors_button.clicked.connect(self._clear_curve_colors)

        self.marker_combo = QComboBox(self)
        for label, marker in MARKER_OPTIONS:
            self.marker_combo.addItem(label, marker)
        self.marker_combo.setCurrentIndex(len(MARKER_OPTIONS) - 1)
        self.marker_combo.currentIndexChanged.connect(
            lambda _index: self.refresh()
        )
        self.marker_size_spin = QDoubleSpinBox(self)
        self.marker_size_spin.setRange(1.0, 20.0)
        self.marker_size_spin.setValue(4.0)
        self.marker_size_spin.valueChanged.connect(
            lambda _value: self.refresh()
        )
        self.line_width_spin = QDoubleSpinBox(self)
        self.line_width_spin.setRange(0.2, 8.0)
        self.line_width_spin.setSingleStep(0.2)
        self.line_width_spin.setValue(1.3)
        self.line_width_spin.valueChanged.connect(
            lambda _value: self.refresh()
        )
        self.line_style_combo = QComboBox(self)
        for label, style in LINE_STYLE_OPTIONS:
            self.line_style_combo.addItem(label, style)
        self.line_style_combo.currentIndexChanged.connect(
            lambda _index: self.refresh()
        )

        # -- Legenda -----------------------------------------------------
        self.legend_checkbox = QCheckBox("Exibir legenda", self)
        self.legend_checkbox.setChecked(True)
        self.legend_checkbox.toggled.connect(
            lambda _checked: self.refresh()
        )
        self.legend_pos_combo = QComboBox(self)
        for label, pos in _LEGEND_POSITIONS:
            self.legend_pos_combo.addItem(label, pos)
        self.legend_pos_combo.currentIndexChanged.connect(
            lambda _index: self.refresh()
        )
        self.legend_cols_spin = QSpinBox(self)
        self.legend_cols_spin.setRange(1, 6)
        self.legend_cols_spin.setValue(1)
        self.legend_cols_spin.valueChanged.connect(
            lambda _value: self.refresh()
        )

        # -- Zoom de destaque (inset) ---------------------------------------
        self.inset_checkbox = QCheckBox("Ativar zoom de destaque", self)
        self.inset_checkbox.toggled.connect(
            lambda _checked: self.refresh()
        )
        self.pick_button = QPushButton(
            "Selecionar região no gráfico", self
        )
        self.pick_button.setToolTip(
            "Clique e arraste um retângulo sobre o gráfico para "
            "definir a região ampliada."
        )
        self.pick_button.clicked.connect(self._start_region_pick)

        self.inset_target_combo = QComboBox(self)
        self.inset_target_combo.addItem("Painel 1 (superior)", 0)
        self.inset_target_combo.addItem("Painel 2 (inferior)", 1)
        self.inset_target_combo.currentIndexChanged.connect(
            lambda _index: self.refresh()
        )

        self.inset_pos_combo = QComboBox(self)
        for label, pos in _INSET_POSITIONS:
            self.inset_pos_combo.addItem(label, pos)
        self.inset_pos_combo.currentIndexChanged.connect(
            lambda _index: self.refresh()
        )
        self.inset_size_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.inset_size_slider.setRange(20, 50)
        self.inset_size_slider.setValue(35)
        self.inset_size_slider.valueChanged.connect(
            lambda _value: self.refresh()
        )

        self.x1_edit = QLineEdit(self)
        self.x2_edit = QLineEdit(self)
        self.y1_edit = QLineEdit(self)
        self.y2_edit = QLineEdit(self)
        for edit, placeholder in (
            (self.x1_edit, "x mín"),
            (self.x2_edit, "x máx"),
            (self.y1_edit, "y mín"),
            (self.y2_edit, "y máx"),
        ):
            edit.setPlaceholderText(placeholder)
            edit.editingFinished.connect(self.refresh)

        # -- Canvas e ações --------------------------------------------------
        self.canvas = PlotCanvas(self)
        export_button = QPushButton("Exportar imagem…", self)
        export_button.clicked.connect(self._export_image)
        refresh_button = QPushButton("Atualizar gráfico", self)
        refresh_button.clicked.connect(self.refresh)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #9a9a9a;")

        # -- Layout -------------------------------------------------------------
        meas_box = QGroupBox("Medições", self)
        meas_layout = QVBoxLayout(meas_box)
        meas_layout.addWidget(self.measurement_list, 1)
        meas_buttons = QHBoxLayout()
        meas_buttons.addWidget(all_button)
        meas_buttons.addWidget(none_button)
        meas_buttons.addWidget(sync_button)
        meas_layout.addLayout(meas_buttons)

        chart_box = QGroupBox("Gráfico", self)
        chart_form = QFormLayout(chart_box)
        chart_form.addRow("Fonte de dados:", self.source_combo)
        chart_form.addRow("Tipo:", self.kind_combo)
        chart_form.addRow("Título:", self.title_edit)
        chart_form.addRow("Rótulo X:", self.xlabel_edit)
        chart_form.addRow("Rótulo Y:", self.ylabel_edit)
        scale_row = QHBoxLayout()
        scale_row.addWidget(self.xlog_checkbox)
        scale_row.addWidget(self.ylog_checkbox)
        scale_row.addWidget(self.grid_checkbox)
        chart_form.addRow(scale_row)
        chart_form.addRow("Paleta de cores:", self.colormap_combo)
        chart_form.addRow("Marcador:", self.marker_combo)
        chart_form.addRow("Tam. marcador:", self.marker_size_spin)
        chart_form.addRow("Espessura:", self.line_width_spin)
        chart_form.addRow("Linha:", self.line_style_combo)

        colors_box = QGroupBox("Cores", self)
        colors_form = QFormLayout(colors_box)
        colors_form.addRow("Fundo da figura:", self.figure_color_button)
        colors_form.addRow("Fundo do gráfico:", self.axes_color_button)
        colors_form.addRow("Grade:", self.grid_color_button)
        colors_form.addRow("Texto/eixos:", self.text_color_button)
        colors_form.addRow(light_button)
        colors_form.addRow(clear_colors_button)
        color_hint = QLabel(
            "Clique duas vezes numa curva da lista para escolher a cor "
            "dela.",
            self,
        )
        color_hint.setWordWrap(True)
        color_hint.setStyleSheet("color: #9a9a9a;")
        colors_form.addRow(color_hint)

        legend_box = QGroupBox("Legenda", self)
        legend_form = QFormLayout(legend_box)
        legend_form.addRow(self.legend_checkbox)
        legend_form.addRow("Posição:", self.legend_pos_combo)
        legend_form.addRow("Colunas:", self.legend_cols_spin)

        inset_box = QGroupBox("Zoom de destaque", self)
        inset_form = QFormLayout(inset_box)
        inset_form.addRow(self.inset_checkbox)
        inset_form.addRow(self.pick_button)
        inset_form.addRow("Painel:", self.inset_target_combo)
        limits_row1 = QHBoxLayout()
        limits_row1.addWidget(self.x1_edit)
        limits_row1.addWidget(self.x2_edit)
        inset_form.addRow("Região X:", limits_row1)
        limits_row2 = QHBoxLayout()
        limits_row2.addWidget(self.y1_edit)
        limits_row2.addWidget(self.y2_edit)
        inset_form.addRow("Região Y:", limits_row2)
        inset_form.addRow("Canto:", self.inset_pos_combo)
        inset_form.addRow("Tamanho:", self.inset_size_slider)

        left = QVBoxLayout()
        left.addWidget(meas_box)
        left.addWidget(chart_box)
        left.addWidget(colors_box)
        left.addWidget(legend_box)
        left.addWidget(inset_box)
        left.addStretch(1)
        left_inner = QWidget(self)
        left_inner.setLayout(left)
        left_widget = QScrollArea(self)
        left_widget.setWidget(left_inner)
        left_widget.setWidgetResizable(True)
        left_widget.setMinimumWidth(380)
        left_widget.setMaximumWidth(400)

        right = QVBoxLayout()
        right.addWidget(self.canvas, 1)
        actions = QHBoxLayout()
        actions.addWidget(self.status_label, 1)
        actions.addWidget(refresh_button)
        actions.addWidget(export_button)
        right.addLayout(actions)

        layout = QHBoxLayout(self)
        layout.addWidget(left_widget)
        layout.addLayout(right, 1)

        self.sync_measurements(check_all=True)
        self._on_kind_changed(0)

    # -- Fonte de dados e medições -------------------------------------------
    def _current_source(self) -> str:
        """Fonte de dados atual (``"eis"`` ou ``"iv"``)."""
        return str(self.source_combo.currentData() or "eis")

    def _current_provider(self) -> dict:
        """Dicionário de dados da fonte atual."""
        if self._current_source() == "iv" and self._iv_provider:
            return self._iv_provider()
        return self._provider()

    def _on_source_changed(self, _index: int) -> None:
        """Troca a fonte de dados (EIS ↔ curva I-V)."""
        kinds = (
            _IV_KINDS if self._current_source() == "iv" else _CHART_KINDS
        )
        self.kind_combo.blockSignals(True)
        try:
            self.kind_combo.clear()
            for label, kind in kinds:
                self.kind_combo.addItem(label, kind)
        finally:
            self.kind_combo.blockSignals(False)
        self.sync_measurements(check_all=True)
        self._on_kind_changed(0)

    def sync_measurements(self, check_all: bool = False) -> None:
        """Sincroniza a lista com os dados da fonte atual.

        Args:
            check_all: Marca todos os itens (usado na abertura e na
                troca de fonte).
        """
        checked = {
            self.measurement_list.item(i).text()
            for i in range(self.measurement_list.count())
            if self.measurement_list.item(i).checkState()
            == Qt.CheckState.Checked
        }
        self.measurement_list.blockSignals(True)
        try:
            self.measurement_list.clear()
            for name in self._current_provider():
                item = QListWidgetItem(name, self.measurement_list)
                item.setFlags(
                    item.flags() | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(
                    Qt.CheckState.Checked
                    if check_all or name in checked
                    else Qt.CheckState.Unchecked
                )
        finally:
            self.measurement_list.blockSignals(False)
        self._apply_list_item_colors()
        self.refresh()

    def _set_all(self, checked: bool) -> None:
        state = (
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        )
        self.measurement_list.blockSignals(True)
        try:
            for i in range(self.measurement_list.count()):
                self.measurement_list.item(i).setCheckState(state)
        finally:
            self.measurement_list.blockSignals(False)
        self.refresh()

    # -- Cores das curvas -----------------------------------------------------
    def _on_curve_double_clicked(self, item: QListWidgetItem) -> None:
        """Escolhe a cor da curva com duplo clique na lista."""
        name = item.text()
        initial = QColor(self._curve_colors.get(name, "#4fc3f7"))
        chosen = QColorDialog.getColor(
            initial, self, f"Cor de '{name}'"
        )
        if not chosen.isValid():
            return
        self._curve_colors[name] = chosen.name()
        self._apply_list_item_colors()
        self.refresh()

    def _clear_curve_colors(self) -> None:
        """Remove todas as cores manuais das curvas."""
        self._curve_colors.clear()
        self._apply_list_item_colors()
        self.refresh()

    def _apply_list_item_colors(self) -> None:
        """Colore o texto dos itens conforme a cor manual da curva."""
        default = QColor("#d4d4d4")
        for i in range(self.measurement_list.count()):
            item = self.measurement_list.item(i)
            color = self._curve_colors.get(item.text())
            item.setForeground(QColor(color) if color else default)

    def _apply_light_preset(self) -> None:
        """Aplica um esquema de fundo claro (para publicação)."""
        for button, color in (
            (self.figure_color_button, "#ffffff"),
            (self.axes_color_button, "#ffffff"),
            (self.grid_color_button, "#c0c0c0"),
            (self.text_color_button, "#000000"),
        ):
            button.blockSignals(True)
            button.set_color(color)
            button.blockSignals(False)
        self.refresh()

    def selected_measurements(self) -> list:
        """Itens marcados (medições ou curvas I-V), na ordem da lista."""
        data = self._current_provider()
        result: list = []
        for i in range(self.measurement_list.count()):
            item = self.measurement_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                entry = data.get(item.text())
                if entry is not None:
                    result.append(entry)
        return result

    # -- Configuração ----------------------------------------------------------
    def _on_kind_changed(self, _index: int) -> None:
        """Ajusta os padrões de escala ao trocar o tipo de gráfico."""
        kind = self.kind_combo.currentData()
        self.xlog_checkbox.blockSignals(True)
        self.ylog_checkbox.blockSignals(True)
        try:
            if kind == "bode_mag":
                self.xlog_checkbox.setChecked(True)
                self.ylog_checkbox.setChecked(True)
            elif kind in ("bode_full", "bode_phase"):
                self.xlog_checkbox.setChecked(True)
                self.ylog_checkbox.setChecked(False)
            else:
                # Nyquist e curvas I-V: escalas lineares.
                self.xlog_checkbox.setChecked(False)
                self.ylog_checkbox.setChecked(False)
        finally:
            self.xlog_checkbox.blockSignals(False)
            self.ylog_checkbox.blockSignals(False)
        self.inset_target_combo.setEnabled(kind in _TWO_PANEL_KINDS)
        self.ylog_checkbox.setEnabled(kind not in _TWO_PANEL_KINDS)
        self.refresh()

    def _style(self, colors: dict[str, object]) -> PlotStyle:
        return PlotStyle(
            marker=self.marker_combo.currentData(),
            marker_size=float(self.marker_size_spin.value()),
            line_width=float(self.line_width_spin.value()),
            line_style=self.line_style_combo.currentData(),
            show_grid=self.grid_checkbox.isChecked(),
            figure_color=self.figure_color_button.color(),
            axes_color=self.axes_color_button.color(),
            grid_color=self.grid_color_button.color(),
            text_color=self.text_color_button.color(),
            colors=colors,
        )

    def _build_colors(self, names: list[str]) -> dict[str, object]:
        """Mapeia cada curva à sua cor (paleta + overrides manuais).

        Args:
            names: Nomes das curvas selecionadas, em ordem.

        Returns:
            Dicionário ``{nome: cor}`` cobrindo todas as curvas.
        """
        n = len(names)
        cmap_name = self.colormap_combo.currentData()
        if cmap_name is None:
            cycle = matplotlib.rcParams["axes.prop_cycle"].by_key()[
                "color"
            ]
            base = [cycle[i % len(cycle)] for i in range(n)]
        else:
            cmap = matplotlib.colormaps[cmap_name]
            if cmap_name == "tab20":
                base = [cmap(i % 20) for i in range(n)]
            else:
                positions = np.linspace(0.05, 0.95, max(n, 2))[:n]
                base = [cmap(p) for p in positions]
        colors: dict[str, object] = {}
        for name, color in zip(names, base):
            colors[name] = self._curve_colors.get(name, color)
        return colors

    # -- Renderização ------------------------------------------------------------
    def refresh(self) -> None:
        """Redesenha o gráfico com a configuração atual."""
        self._selector = None
        self._inset_ax = None
        measurements = self.selected_measurements()
        names = [self._entry_name(m) for m in measurements]
        colors = self._build_colors(names)
        style = self._style(colors)
        kind = self.kind_combo.currentData()

        self.canvas.clear()
        self._axes = []
        figure = self.canvas.figure
        if not measurements:
            self.status_label.setText(
                "Marque ao menos uma medição para desenhar o gráfico."
            )
            self.canvas.draw()
            return
        self.status_label.setText(
            f"{len(measurements)} curva(s) no gráfico. Clique duas "
            "vezes numa curva da lista para mudar sua cor."
        )

        if kind in _TWO_PANEL_KINDS:
            ax_top, ax_bottom = figure.subplots(2, 1, sharex=True)
            if kind == "bode_full":
                plot_bode_magnitude(
                    ax_top, measurements, style, title=""
                )
                plot_bode_phase(
                    ax_bottom, measurements, style, title=""
                )
            else:  # iv_pv
                plot_iv(ax_top, measurements, style, title="")
                plot_pv(ax_bottom, measurements, style, title="")
            ax_top.set_xlabel("")
            self._axes = [ax_top, ax_bottom]
        else:
            ax = figure.add_subplot(111)
            if kind == "nyquist":
                plot_nyquist(ax, measurements, style, title="")
            elif kind == "bode_mag":
                plot_bode_magnitude(ax, measurements, style, title="")
            elif kind == "bode_phase":
                plot_bode_phase(ax, measurements, style, title="")
            elif kind == "iv":
                plot_iv(ax, measurements, style, title="")
            else:  # pv
                plot_pv(ax, measurements, style, title="")
            self._axes = [ax]

        self._apply_scales_and_labels(kind)
        self._apply_legend()
        if self.inset_checkbox.isChecked():
            self._apply_inset(measurements, style, kind)

        title = self.title_edit.text().strip()
        if title:
            figure.suptitle(title, fontsize=12)
        self.canvas.draw()

    @staticmethod
    def _entry_name(entry: object) -> str:
        """Nome de uma medição ou curva I-V."""
        return getattr(entry, "name", str(entry))

    def _apply_scales_and_labels(self, kind: str) -> None:
        """Aplica escalas log/linear e rótulos personalizados."""
        xlog = self.xlog_checkbox.isChecked()
        ylog = self.ylog_checkbox.isChecked()
        for i, ax in enumerate(self._axes):
            ax.set_xscale("log" if xlog else "linear")
            if kind in _TWO_PANEL_KINDS:
                # Bode: magnitude em log; fase linear.  I-V: ambos
                # lineares (corrente e potência podem cruzar zero).
                ax.set_yscale(
                    "log" if kind == "bode_full" and i == 0
                    else "linear"
                )
            else:
                if ylog:
                    try:
                        ax.set_yscale("log")
                    except ValueError:
                        ax.set_yscale("linear")
                else:
                    ax.set_yscale("linear")
            ax.grid(self.grid_checkbox.isChecked(), which="both")
        xlabel = self.xlabel_edit.text().strip()
        ylabel = self.ylabel_edit.text().strip()
        if xlabel:
            self._axes[-1].set_xlabel(xlabel)
        if ylabel:
            self._axes[0].set_ylabel(ylabel)

    def _apply_legend(self) -> None:
        """Aplica (ou remove) a legenda conforme a configuração."""
        show = self.legend_checkbox.isChecked()
        position = self.legend_pos_combo.currentData()
        columns = int(self.legend_cols_spin.value())
        axes_color = self.axes_color_button.color()
        text_color = self.text_color_button.color()
        for i, ax in enumerate(self._axes):
            legend = ax.get_legend()
            if legend is not None:
                legend.remove()
            if not show or i > 0:
                continue
            if position == "__outside__":
                legend = ax.legend(
                    loc="upper left",
                    bbox_to_anchor=(1.01, 1.0),
                    fontsize=8,
                    ncols=columns,
                )
            else:
                legend = ax.legend(
                    loc=position, fontsize=8, ncols=columns
                )
            if legend is not None:
                if axes_color is not None:
                    legend.get_frame().set_facecolor(axes_color)
                if text_color is not None:
                    for text in legend.get_texts():
                        text.set_color(text_color)

    def _inset_limits(
        self,
    ) -> Optional[tuple[float, float, float, float]]:
        """Limites (x1, x2, y1, y2) do zoom, se válidos."""
        values = [
            parse_number(edit.text() or "")
            for edit in (
                self.x1_edit, self.x2_edit, self.y1_edit, self.y2_edit
            )
        ]
        if any(v is None for v in values):
            return None
        x1, x2, y1, y2 = (float(v) for v in values)
        if x1 == x2 or y1 == y2:
            return None
        return (min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2))

    def _apply_inset(
        self,
        measurements: list[Measurement],
        style: PlotStyle,
        kind: str,
    ) -> None:
        """Cria o quadro de zoom de destaque no painel-alvo."""
        limits = self._inset_limits()
        if limits is None:
            self.status_label.setText(
                "Zoom de destaque: informe a região (use \"Selecionar "
                "região no gráfico\" ou digite os limites)."
            )
            return
        target_index = (
            int(self.inset_target_combo.currentData() or 0)
            if kind in _TWO_PANEL_KINDS
            else 0
        )
        target_index = min(target_index, len(self._axes) - 1)
        ax = self._axes[target_index]

        x1, x2, y1, y2 = limits
        if ax.get_xscale() == "log" and x1 <= 0.0:
            self.status_label.setText(
                "Zoom de destaque: os limites X devem ser positivos "
                "em eixo logarítmico."
            )
            return
        if ax.get_yscale() == "log" and y1 <= 0.0:
            self.status_label.setText(
                "Zoom de destaque: os limites Y devem ser positivos "
                "em eixo logarítmico."
            )
            return

        size = self.inset_size_slider.value() / 100.0
        width = size
        height = size * 0.9
        margin = 0.05
        corner = self.inset_pos_combo.currentData()
        x0 = margin if corner in ("nw", "sw") else 1.0 - margin - width
        y0 = margin if corner in ("se", "sw") else 1.0 - margin - height
        axins = ax.inset_axes([x0, y0, width, height])

        if kind == "nyquist":
            plot_nyquist(axins, measurements, style, title="")
            axins.set_aspect("auto")
        elif kind == "bode_phase" or (
            kind == "bode_full" and target_index == 1
        ):
            plot_bode_phase(axins, measurements, style, title="")
        elif kind in ("bode_mag", "bode_full"):
            plot_bode_magnitude(axins, measurements, style, title="")
        elif kind == "iv" or (kind == "iv_pv" and target_index == 0):
            plot_iv(axins, measurements, style, title="")
        else:  # pv ou iv_pv (painel de potência)
            plot_pv(axins, measurements, style, title="")

        axins.set_xscale(ax.get_xscale())
        axins.set_yscale(ax.get_yscale())
        axins.set_xlim(x1, x2)
        axins.set_ylim(y1, y2)
        axins.set_xlabel("")
        axins.set_ylabel("")
        axins.set_title("")
        legend = axins.get_legend()
        if legend is not None:
            legend.remove()
        axins.tick_params(labelsize=7)
        axins.grid(self.grid_checkbox.isChecked(), which="both",
                   linewidth=0.4)
        try:
            ax.indicate_inset_zoom(axins, edgecolor="#e0a030",
                                   linewidth=1.2)
        except ValueError:
            logger.warning(
                "indicate_inset_zoom falhou para a região %s.", limits
            )
        self._inset_ax = axins

    # -- Seleção interativa da região -----------------------------------------
    def _start_region_pick(self) -> None:
        """Ativa a seleção por arrasto da região do zoom."""
        if not self._axes:
            QMessageBox.information(
                self,
                "Zoom de destaque",
                "Desenhe um gráfico primeiro (marque medições).",
            )
            return
        kind = self.kind_combo.currentData()
        target_index = (
            int(self.inset_target_combo.currentData() or 0)
            if kind in _TWO_PANEL_KINDS
            else 0
        )
        target_index = min(target_index, len(self._axes) - 1)
        ax = self._axes[target_index]
        self.status_label.setText(
            "Arraste um retângulo sobre o gráfico para definir a "
            "região do zoom…"
        )

        def _on_select(eclick, erelease) -> None:
            x1, x2 = sorted((eclick.xdata, erelease.xdata))
            y1, y2 = sorted((eclick.ydata, erelease.ydata))
            if None in (x1, x2, y1, y2) or x1 == x2 or y1 == y2:
                return
            self.x1_edit.setText(f"{x1:.6g}")
            self.x2_edit.setText(f"{x2:.6g}")
            self.y1_edit.setText(f"{y1:.6g}")
            self.y2_edit.setText(f"{y2:.6g}")
            if self._selector is not None:
                self._selector.set_active(False)
                self._selector = None
            self.inset_checkbox.blockSignals(True)
            self.inset_checkbox.setChecked(True)
            self.inset_checkbox.blockSignals(False)
            logger.info(
                "Região de destaque selecionada: x=[%.4g, %.4g], "
                "y=[%.4g, %.4g].",
                x1, x2, y1, y2,
            )
            self.refresh()

        self._selector = RectangleSelector(
            ax,
            _on_select,
            useblit=True,
            button=[1],
            minspanx=2,
            minspany=2,
            spancoords="pixels",
            interactive=False,
            props={
                "facecolor": "#e0a030",
                "edgecolor": "#e0a030",
                "alpha": 0.25,
                "fill": True,
            },
        )
        self._selector.set_active(True)

    # -- Exportação ---------------------------------------------------------------
    def _export_image(self) -> None:
        """Exporta a figura atual para PNG/PDF/SVG."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar imagem",
            "grafico_personalizado.png",
            "Imagem PNG (*.png);;Documento PDF (*.pdf);;"
            "Imagem SVG (*.svg)",
        )
        if not path:
            return
        try:
            exportacao.export_figure(self.canvas.figure, path)
        except (OSError, ValueError) as exc:
            logger.exception("Falha ao exportar gráfico personalizado.")
            QMessageBox.critical(
                self,
                "Exportar imagem",
                f"Não foi possível exportar:\n{exc}",
            )
            return
        self.status_label.setText(f"Imagem exportada: {path}")
