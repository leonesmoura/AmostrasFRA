"""Interface gráfica principal (AMOSTRAS FRA 2.0).

Janela principal em PySide6 com tema escuro, toolbar, menus, barra de
status e docks, no estilo de softwares científicos de EIS (Metrohm
NOVA, ZView, EC-Lab).

Componentes:

* Tabela de entrada de dados tipo Excel (:class:`DataTable`) com
  colagem inteligente (Ctrl+V) de Excel, Metrohm NOVA e TXT, além de
  importação de CSV/TXT/XLSX/ODS.
* Lista lateral de medições com caixas de seleção.
* Abas de gráficos: Nyquist, Bode Magnitude, Bode Fase,
  Kramers-Kronig, Circuito Equivalente e Comparação.
* Janela de Correção do Instrumento (resistor padrão → ``H(f)``).
* Exportação de imagens, Excel, CSV e relatório PDF.
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Optional, Sequence

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtSerialPort import QSerialPort
from PySide6.QtGui import (
    QAction,
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPalette,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import ajuda
import circuitos
import exportacao
import iv_model
import kk as kk_module
import projeto
import serial_io
import util
from correcao import InstrumentCorrection
from graficos import ChartBuilderDialog
from simulacao import PVSimulationDialog
from plots import (
    ColorButton,
    PlotCanvas,
    PlotStyle,
    apply_background,
    plot_bode_magnitude,
    plot_bode_phase,
    plot_circuit_fit,
    plot_comparison,
    plot_diode_fit,
    plot_kk,
    plot_nyquist,
    mathtext_to_pixmap,
)
from util import (
    COL_CURR,
    COL_FREQ,
    COL_MINUS_ZIMAG,
    COL_PHASE,
    COL_VOLT,
    COL_ZMOD,
    COL_ZREAL,
    COLUMN_LABELS,
    Measurement,
    format_engineering,
    parse_number,
    unique_name,
)

logger = logging.getLogger(__name__)

#: Número de casas de exibição dos valores nas tabelas.
_CELL_FORMAT = "{:.6g}"

#: Opções de marcador exibidas ao usuário.
_MARKERS: tuple[tuple[str, str], ...] = (
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

#: Opções de estilo de linha exibidas ao usuário.
_LINE_STYLES: tuple[tuple[str, str], ...] = (
    ("Contínua", "-"),
    ("Tracejada", "--"),
    ("Pontilhada", ":"),
    ("Traço-ponto", "-."),
    ("Nenhuma", "none"),
)


def apply_dark_theme(app: QApplication) -> None:
    """Aplica o tema escuro (estilo Fusion + paleta + stylesheet).

    Args:
        app: Instância da aplicação Qt.
    """
    app.setStyle("Fusion")
    palette = QPalette()
    window = QColor(30, 30, 30)
    base = QColor(37, 37, 38)
    alt_base = QColor(45, 45, 48)
    text = QColor(212, 212, 212)
    disabled = QColor(120, 120, 120)
    highlight = QColor(14, 99, 156)

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, alt_base)
    palette.setColor(QPalette.ColorRole.ToolTipBase, alt_base)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, alt_base)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 85, 85))
    palette.setColor(QPalette.ColorRole.Link, QColor(79, 195, 247))
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(
        QPalette.ColorRole.HighlightedText, QColor(255, 255, 255)
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        disabled,
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.WindowText,
        disabled,
    )
    app.setPalette(palette)
    app.setStyleSheet(
        """
        QMainWindow, QDialog { background-color: #1e1e1e; }
        QTableWidget {
            gridline-color: #3c3c3c;
            selection-background-color: #0e639c;
        }
        QHeaderView::section {
            background-color: #2d2d30;
            color: #d4d4d4;
            border: 1px solid #3c3c3c;
            padding: 4px;
        }
        QTableCornerButton::section { background-color: #2d2d30; }
        QTabWidget::pane { border: 1px solid #3c3c3c; }
        QTabBar::tab {
            background: #2d2d30;
            color: #d4d4d4;
            padding: 6px 14px;
            border: 1px solid #3c3c3c;
            border-bottom: none;
        }
        QTabBar::tab:selected {
            background: #0e639c;
            color: white;
        }
        QDockWidget::title {
            background: #2d2d30;
            padding: 5px;
        }
        QToolBar {
            background: #2d2d30;
            border-bottom: 1px solid #3c3c3c;
            spacing: 3px;
        }
        QStatusBar { background: #2d2d30; color: #d4d4d4; }
        QGroupBox {
            border: 1px solid #3c3c3c;
            border-radius: 4px;
            margin-top: 8px;
            padding-top: 6px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
        }
        QPushButton {
            background-color: #2d2d30;
            border: 1px solid #3c3c3c;
            padding: 5px 12px;
            border-radius: 3px;
        }
        QPushButton:hover { background-color: #3e3e42; }
        QPushButton:pressed { background-color: #0e639c; }
        QToolButton:checked { background-color: #0e639c; }
        """
    )
    logger.debug("Tema escuro aplicado à interface Qt.")


# ---------------------------------------------------------------------------
# Tabelas com colagem inteligente
# ---------------------------------------------------------------------------
class PasteableTable(QTableWidget):
    """Tabela tipo Excel com copiar/colar e detecção de delimitadores.

    Suporta Ctrl+V (colar de Excel, NOVA ou TXT), Ctrl+C (copiar
    seleção como TSV), Delete (limpar células) e menu de contexto.
    """

    #: Emitido após uma colagem, com as linhas afetadas (início, fim).
    pasted = Signal(int, int)

    def __init__(
        self,
        columns: Sequence[str],
        initial_rows: int = 50,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(initial_rows, len(columns), parent)
        self.setHorizontalHeaderLabels(list(columns))
        self.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.setAlternatingRowColors(True)
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )

    # -- Entrada de teclado --------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802 (API Qt)
        """Trata Ctrl+V, Ctrl+C e Delete."""
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_from_clipboard()
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.clear_selected_cells()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 (API Qt)
        """Menu de contexto com operações de edição."""
        menu = QMenu(self)
        menu.addAction("Colar (Ctrl+V)", self.paste_from_clipboard)
        menu.addAction("Copiar (Ctrl+C)", self.copy_selection)
        menu.addAction("Limpar células", self.clear_selected_cells)
        menu.addSeparator()
        menu.addAction("Adicionar 10 linhas", lambda: self.add_rows(10))
        menu.addAction(
            "Remover linhas selecionadas", self.remove_selected_rows
        )
        menu.addAction("Limpar tabela", self.clear_all)
        menu.exec(event.globalPos())

    #: Papel (role) que guarda o valor float exato da célula.
    _ROLE_VALUE = Qt.ItemDataRole.UserRole
    #: Papel que guarda o texto formatado correspondente ao valor.
    _ROLE_TEXT = Qt.ItemDataRole.UserRole + 1

    # -- Operações ------------------------------------------------------
    def set_value(
        self, row: int, column: int, value: Optional[float]
    ) -> None:
        """Define o valor numérico de uma célula (ou limpa com None).

        O valor exato é guardado no item (``UserRole``) para que a
        exibição com 6 algarismos significativos não cause perda de
        precisão nem "frequências duplicadas" falsas ao reconstruir a
        medição a partir da tabela.
        """
        text = "" if value is None else _CELL_FORMAT.format(value)
        item = self.item(row, column)
        if item is None:
            item = QTableWidgetItem(text)
            self.setItem(row, column, item)
        else:
            item.setText(text)
        item.setData(self._ROLE_VALUE, value)
        item.setData(self._ROLE_TEXT, text)

    def get_value(self, row: int, column: int) -> Optional[float]:
        """Lê o valor numérico de uma célula (None se vazia/inválida).

        Retorna o float exato guardado no item quando o texto exibido
        não foi editado pelo usuário; caso contrário, interpreta o
        texto digitado.
        """
        item = self.item(row, column)
        if item is None:
            return None
        stored_value = item.data(self._ROLE_VALUE)
        stored_text = item.data(self._ROLE_TEXT)
        if stored_value is not None and item.text() == stored_text:
            return float(stored_value)
        return parse_number(item.text())

    def get_rows(self) -> list[list[Optional[float]]]:
        """Retorna todas as linhas não vazias da tabela."""
        rows: list[list[Optional[float]]] = []
        for row in range(self.rowCount()):
            values = [
                self.get_value(row, col)
                for col in range(self.columnCount())
            ]
            if any(v is not None for v in values):
                rows.append(values)
        return rows

    def set_rows(self, rows: Sequence[Sequence[Optional[float]]]) -> None:
        """Substitui o conteúdo da tabela pelas linhas fornecidas."""
        self.blockSignals(True)
        try:
            self.clearContents()
            self.setRowCount(max(len(rows) + 5, 20))
            for r, row in enumerate(rows):
                for c, value in enumerate(row[: self.columnCount()]):
                    self.set_value(r, c, value)
        finally:
            self.blockSignals(False)
        self.pasted.emit(0, max(len(rows) - 1, 0))

    def add_rows(self, count: int) -> None:
        """Acrescenta linhas vazias ao final da tabela."""
        self.setRowCount(self.rowCount() + count)

    def remove_selected_rows(self) -> None:
        """Remove as linhas com células selecionadas."""
        rows = sorted(
            {index.row() for index in self.selectedIndexes()},
            reverse=True,
        )
        for row in rows:
            self.removeRow(row)
        if self.rowCount() == 0:
            self.setRowCount(20)

    def clear_all(self) -> None:
        """Limpa todas as células, mantendo as linhas."""
        self.blockSignals(True)
        try:
            self.clearContents()
        finally:
            self.blockSignals(False)

    def clear_selected_cells(self) -> None:
        """Limpa o conteúdo das células selecionadas."""
        self.blockSignals(True)
        try:
            for index in self.selectedIndexes():
                item = self.item(index.row(), index.column())
                if item is not None:
                    item.setText("")
        finally:
            self.blockSignals(False)

    def copy_selection(self) -> None:
        """Copia a seleção para a área de transferência (TSV)."""
        indexes = self.selectedIndexes()
        if not indexes:
            return
        rows = sorted({i.row() for i in indexes})
        cols = sorted({i.column() for i in indexes})
        lines: list[str] = []
        for row in rows:
            cells: list[str] = []
            for col in cols:
                item = self.item(row, col)
                cells.append(item.text() if item is not None else "")
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))

    def paste_from_clipboard(self) -> None:
        """Cola dados tabulares detectando delimitadores e decimais."""
        text = QApplication.clipboard().text()
        if not text.strip():
            return
        parsed = util.parse_table_text(text)
        if not parsed:
            QMessageBox.warning(
                self,
                "Colar dados",
                "Nenhum dado numérico foi reconhecido na área de "
                "transferência.",
            )
            return
        start_row = max(self.currentRow(), 0)
        start_col = max(self.currentColumn(), 0)
        needed_rows = start_row + len(parsed)
        if needed_rows > self.rowCount():
            self.setRowCount(needed_rows)
        self.blockSignals(True)
        try:
            for r, row in enumerate(parsed):
                for c, value in enumerate(row):
                    target_col = start_col + c
                    if target_col >= self.columnCount():
                        break
                    if value is not None:
                        self.set_value(start_row + r, target_col, value)
        finally:
            self.blockSignals(False)
        logger.info(
            "Colagem: %d linha(s) a partir da célula (%d, %d).",
            len(parsed),
            start_row + 1,
            start_col + 1,
        )
        self.pasted.emit(start_row, start_row + len(parsed) - 1)


class DataTable(PasteableTable):
    """Tabela principal de dados com preenchimento automático.

    Cadeia de cálculo automático por linha:

    * ``Tensão`` e ``Corrente`` → ``|Z| = V / I``;
    * ``|Z|`` e ``Fase`` → ``Z'`` e ``-Z''``;
    * ``Z'`` e ``-Z''`` → ``|Z|`` e ``Fase``.

    A colagem reconhece cabeçalhos (inclusive de tensão/corrente) e
    mapeia as colunas automaticamente; sem cabeçalho, usa o formato
    posicional configurado em :meth:`set_paste_mapping`.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(COLUMN_LABELS, initial_rows=50, parent=parent)
        self._paste_mapping: Optional[list[int]] = None
        self.cellChanged.connect(self._on_cell_changed)
        self.pasted.connect(self._on_pasted)

    def set_paste_mapping(self, mapping: Optional[Sequence[int]]) -> None:
        """Define as colunas-alvo da colagem posicional sem cabeçalho.

        Aplicado apenas quando a colagem é ancorada na coluna 0; em
        outras colunas, a colagem segue a posição do cursor (como no
        Excel).

        Args:
            mapping: Índices de coluna de destino, na ordem das
                colunas coladas (ou ``None`` para posicional puro).
        """
        self._paste_mapping = list(mapping) if mapping is not None else None

    def paste_from_clipboard(self) -> None:
        """Cola dados detectando cabeçalho e delimitadores.

        Com cabeçalho reconhecido (Freq/Z'/-Z''/|Z|/Fase/Tensão/
        Corrente), as colunas são mapeadas automaticamente,
        independentemente da posição do cursor.  Sem cabeçalho, aplica
        o mapeamento posicional configurado (âncora na coluna 0) ou a
        posição do cursor.
        """
        text = QApplication.clipboard().text()
        if not text.strip():
            return
        parsed = util.parse_table_text(text)
        if not parsed:
            QMessageBox.warning(
                self,
                "Colar dados",
                "Nenhum dado numérico foi reconhecido na área de "
                "transferência.",
            )
            return
        start_row = max(self.currentRow(), 0)
        start_col = max(self.currentColumn(), 0)

        header_map = util.header_map_from_text(text)
        if header_map is not None:
            rows = util.arrange_rows_to_canonical(parsed, header_map)
            target_cols = list(range(len(COLUMN_LABELS)))
            origin = "cabeçalho reconhecido"
        elif start_col == 0 and self._paste_mapping is not None:
            rows = parsed
            target_cols = list(self._paste_mapping)
            origin = "formato posicional configurado"
        else:
            rows = parsed
            target_cols = list(range(start_col, self.columnCount()))
            origin = f"posicional a partir da coluna {start_col + 1}"

        needed_rows = start_row + len(rows)
        if needed_rows > self.rowCount():
            self.setRowCount(needed_rows)
        self.blockSignals(True)
        try:
            for r, row in enumerate(rows):
                for c, value in enumerate(row):
                    if c >= len(target_cols):
                        break
                    if value is not None:
                        self.set_value(
                            start_row + r, target_cols[c], value
                        )
        finally:
            self.blockSignals(False)
        logger.info(
            "Colagem: %d linha(s) na tabela de dados (%s).",
            len(rows),
            origin,
        )
        self.pasted.emit(start_row, start_row + len(rows) - 1)

    def _on_cell_changed(self, row: int, column: int) -> None:
        """Completa as colunas derivadas após edição manual."""
        self.blockSignals(True)
        try:
            self._complete_row(row, edited_column=column)
        finally:
            self.blockSignals(False)

    def _on_pasted(self, first_row: int, last_row: int) -> None:
        """Completa as colunas derivadas após uma colagem."""
        self.blockSignals(True)
        try:
            for row in range(first_row, last_row + 1):
                self._complete_row(row, edited_column=None)
        finally:
            self.blockSignals(False)

    def _complete_row(
        self, row: int, edited_column: Optional[int]
    ) -> None:
        """Preenche as colunas derivadas de uma linha.

        A direção do cálculo respeita estritamente a coluna editada
        (o valor recém-digitado nunca é sobrescrito por dados
        obsoletos):

        * ``Z'``/``-Z''`` editados → recalcula ``|Z|`` e fase;
        * ``|Z|``/fase editados → recalcula ``Z'`` e ``-Z''``
          (usando ``|Z| = V/I`` se ``|Z|`` estiver vazio);
        * ``Tensão``/``Corrente`` editadas → recalcula ``|Z| = V/I``
          e, havendo fase, também ``Z'`` e ``-Z''``.

        Args:
            row: Índice da linha.
            edited_column: Coluna editada (define a direção do
                cálculo) ou ``None`` (colagem/importação) para decidir
                pelos dados, preferindo o par cartesiano.
        """
        z_re = self.get_value(row, COL_ZREAL)
        minus_z_im = self.get_value(row, COL_MINUS_ZIMAG)
        z_mod = self.get_value(row, COL_ZMOD)
        phase = self.get_value(row, COL_PHASE)
        volt = self.get_value(row, COL_VOLT)
        curr = self.get_value(row, COL_CURR)

        cartesian = z_re is not None and minus_z_im is not None
        vi = volt is not None and curr is not None and curr != 0.0

        def _fill_polar() -> None:
            z_complex = complex(z_re, -minus_z_im)
            self.set_value(row, COL_ZMOD, abs(z_complex))
            self.set_value(
                row, COL_PHASE, float(np.degrees(np.angle(z_complex)))
            )

        def _fill_cartesian(
            mod_value: float, phase_value: float
        ) -> None:
            phase_rad = float(np.radians(phase_value))
            self.set_value(
                row, COL_ZREAL, mod_value * float(np.cos(phase_rad))
            )
            self.set_value(
                row,
                COL_MINUS_ZIMAG,
                -mod_value * float(np.sin(phase_rad)),
            )

        if edited_column in (COL_ZREAL, COL_MINUS_ZIMAG):
            if cartesian:
                _fill_polar()
        elif edited_column in (COL_VOLT, COL_CURR):
            if vi:
                z_mod_vi = abs(volt / curr)
                self.set_value(row, COL_ZMOD, z_mod_vi)
                if phase is not None:
                    _fill_cartesian(z_mod_vi, phase)
        elif edited_column in (COL_ZMOD, COL_PHASE):
            if z_mod is None and vi:
                z_mod = abs(volt / curr)
                self.set_value(row, COL_ZMOD, z_mod)
            if z_mod is not None and phase is not None:
                _fill_cartesian(z_mod, phase)
        else:
            # Colagem/importação: prioridade cartesiano → polar → V/I.
            if cartesian:
                _fill_polar()
                return
            if z_mod is None and vi:
                z_mod = abs(volt / curr)
                self.set_value(row, COL_ZMOD, z_mod)
            if z_mod is not None and phase is not None:
                _fill_cartesian(z_mod, phase)


# ---------------------------------------------------------------------------
# Painel de entrada de dados
# ---------------------------------------------------------------------------
class DataEntryPanel(QWidget):
    """Aba "Dados": tabela tipo Excel + botões de importação/medição."""

    #: Emitido ao criar uma medição a partir da tabela.
    measurementCreated = Signal(object)
    #: Emitido ao atualizar a medição selecionada com dados da tabela.
    measurementUpdated = Signal(object)
    #: Emitido ao importar curvas I-V de um CSV de sessão (lista).
    ivCurvesImported = Signal(object)

    #: Rótulo do item "sem correção" no seletor de correção.
    _NO_CORRECTION = "Sem correção"

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        corrections_provider: Optional[
            "Callable[[], dict[str, InstrumentCorrection]]"
        ] = None,
    ) -> None:
        super().__init__(parent)
        self._corrections_provider = corrections_provider
        self.table = DataTable(self)

        self.import_button = QPushButton("Importar…", self)
        self.import_button.setToolTip(
            "Importa dados de arquivos CSV, TXT, XLSX ou ODS."
        )
        self.import_button.clicked.connect(self._on_import_clicked)

        self.add_rows_button = QPushButton("Adicionar linhas", self)
        self.add_rows_button.clicked.connect(
            lambda: self.table.add_rows(20)
        )

        self.clear_button = QPushButton("Limpar tabela", self)
        self.clear_button.clicked.connect(self.table.clear_all)

        self.add_measurement_button = QPushButton(
            "Adicionar como medição", self
        )
        self.add_measurement_button.setToolTip(
            "Cria uma nova medição na lista lateral com os dados da "
            "tabela."
        )
        self.add_measurement_button.clicked.connect(
            self._on_add_measurement
        )

        self.update_measurement_button = QPushButton(
            "Atualizar medição selecionada", self
        )
        self.update_measurement_button.setToolTip(
            "Substitui os dados da medição selecionada na lista pelos "
            "dados atuais da tabela."
        )
        self.update_measurement_button.clicked.connect(
            self._on_update_measurement
        )

        hint = QLabel(
            "Digite os valores ou cole (Ctrl+V) diretamente do Excel, "
            "do Metrohm NOVA ou de arquivos TXT. Delimitadores "
            "(tabulação, vírgula, ponto e vírgula, espaços) e vírgula "
            "decimal são reconhecidos automaticamente. Preencha "
            "Frequência + (Z' e -Z''), Frequência + (|Z| e Fase) ou "
            "Frequência + (Tensão, Corrente e Fase) — |Z| = V/I e as "
            "demais colunas são calculadas. Colagens com cabeçalho "
            "têm as colunas reconhecidas automaticamente.",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9a9a9a;")

        self.paste_format_combo = QComboBox(self)
        self.paste_format_combo.setToolTip(
            "Ordem das colunas ao colar dados SEM linha de cabeçalho "
            "(com a célula ativa na primeira coluna). Colagens com "
            "cabeçalho são mapeadas automaticamente."
        )
        self.paste_format_combo.addItem(
            "Freq, Z', -Z'' (, |Z|, Fase)",
            [COL_FREQ, COL_ZREAL, COL_MINUS_ZIMAG, COL_ZMOD, COL_PHASE],
        )
        self.paste_format_combo.addItem(
            "Freq, |Z|, Fase",
            [COL_FREQ, COL_ZMOD, COL_PHASE],
        )
        self.paste_format_combo.addItem(
            "Freq, Tensão, Corrente, Fase",
            [COL_FREQ, COL_VOLT, COL_CURR, COL_PHASE],
        )
        self.paste_format_combo.currentIndexChanged.connect(
            self._on_paste_format_changed
        )
        self.table.set_paste_mapping(
            self.paste_format_combo.currentData()
        )

        self.correction_combo = QComboBox(self)
        self.correction_combo.setToolTip(
            "Correção do instrumento a aplicar ao criar a medição. "
            "Escolha \"Sem correção\" para medições que não precisam "
            "de correção; as demais correções vêm da biblioteca em "
            "Análise → Correção do Instrumento…"
        )
        self.correction_combo.setMinimumWidth(150)
        self.refresh_corrections()

        buttons = QHBoxLayout()
        buttons.addWidget(self.import_button)
        buttons.addWidget(self.add_rows_button)
        buttons.addWidget(self.clear_button)
        buttons.addWidget(QLabel("Colar sem cabeçalho como:", self))
        buttons.addWidget(self.paste_format_combo)
        buttons.addStretch(1)
        buttons.addWidget(QLabel("Correção:", self))
        buttons.addWidget(self.correction_combo)
        buttons.addWidget(self.add_measurement_button)
        buttons.addWidget(self.update_measurement_button)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(buttons)
        layout.addWidget(self.table, 1)

    def _on_paste_format_changed(self, _index: int) -> None:
        """Atualiza o mapeamento da colagem posicional."""
        self.table.set_paste_mapping(self.paste_format_combo.currentData())

    def refresh_corrections(self) -> None:
        """Repovoa o seletor de correção com a biblioteca atual.

        Preserva a seleção pelo nome, quando ainda existir.
        """
        previous = self.correction_combo.currentData()
        corrections = (
            self._corrections_provider()
            if self._corrections_provider is not None
            else {}
        )
        self.correction_combo.blockSignals(True)
        try:
            self.correction_combo.clear()
            self.correction_combo.addItem(self._NO_CORRECTION, None)
            for name in corrections:
                self.correction_combo.addItem(name, name)
            if previous is not None:
                index = self.correction_combo.findData(previous)
                if index >= 0:
                    self.correction_combo.setCurrentIndex(index)
        finally:
            self.correction_combo.blockSignals(False)

    def _selected_correction(self) -> Optional[InstrumentCorrection]:
        """Correção escolhida no seletor (ou ``None``)."""
        name = self.correction_combo.currentData()
        if name is None or self._corrections_provider is None:
            return None
        return self._corrections_provider().get(name)

    # ------------------------------------------------------------------
    def _on_import_clicked(self) -> None:
        """Abre o seletor de arquivos e importa os dados.

        Se o arquivo contiver várias medições identificadas por nome
        (coluna ``Medição``, gerada pela exportação CSV/Excel do
        AMOSTRAS FRA), oferece importá-las como medições separadas na
        lista lateral; caso contrário, carrega os dados na tabela.
        """
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar dados",
            "",
            "Arquivos de dados (*.csv *.txt *.dat *.xlsx *.xlsm *.ods);;"
            "Todos os arquivos (*)",
        )
        if not path:
            return

        multi: list[Measurement] = []
        try:
            multi = util.load_measurements_from_file(path)
        except (ValueError, OSError, ImportError) as exc:
            logger.warning(
                "Falha ao detectar múltiplas medições em '%s': %s",
                path,
                exc,
            )
        session_iv: list = []
        try:
            session_iv = util.load_session_iv_curves(path)
        except (ValueError, OSError, ImportError) as exc:
            logger.warning(
                "Falha ao detectar curvas I-V de sessão em '%s': %s",
                path,
                exc,
            )

        if len(multi) >= 2 or session_iv:
            parts: list[str] = []
            if multi:
                parts.append(f"{len(multi)} medição(ões) (FRA)")
            if session_iv:
                parts.append(f"{len(session_iv)} curva(s) I-V")
            names = ", ".join(
                [m.name for m in multi] + [c.name for c in session_iv]
            )
            answer = QMessageBox.question(
                self,
                "Importar dados",
                f"O arquivo contém {' e '.join(parts)}:\n{names}\n\n"
                "Importar como amostras separadas na lista lateral?\n"
                "(Escolha \"Não\" para carregar tudo na tabela.)",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Yes:
                for measurement in multi:
                    self.measurementCreated.emit(measurement)
                if session_iv:
                    self.ivCurvesImported.emit(session_iv)
                logger.info(
                    "Importadas %d medição(ões) e %d curva(s) I-V "
                    "separadas de '%s'.",
                    len(multi),
                    len(session_iv),
                    path,
                )
                return

        try:
            rows = util.load_table_from_file(path)
        except (ValueError, OSError, ImportError) as exc:
            logger.exception("Falha ao importar '%s'.", path)
            QMessageBox.critical(
                self,
                "Importar dados",
                f"Não foi possível importar o arquivo:\n{exc}",
            )
            return
        self.table.set_rows(rows)
        logger.info(
            "Importadas %d linha(s) de '%s'.", len(rows), path
        )

    def build_measurement(self, name: str) -> Measurement:
        """Constrói uma :class:`Measurement` com os dados da tabela.

        Raises:
            ValueError: Se os dados forem insuficientes ou inválidos.
        """
        rows = self.table.get_rows()
        if not rows:
            raise ValueError("A tabela está vazia.")
        return Measurement.from_components(
            name=name,
            frequency=[r[COL_FREQ] for r in rows],
            z_real=[r[COL_ZREAL] for r in rows],
            minus_z_imag=[r[COL_MINUS_ZIMAG] for r in rows],
            magnitude=[r[COL_ZMOD] for r in rows],
            phase_deg=[r[COL_PHASE] for r in rows],
            voltage=[r[COL_VOLT] for r in rows],
            current=[r[COL_CURR] for r in rows],
        )

    def load_measurement(self, measurement: Measurement) -> None:
        """Carrega uma medição na tabela (colunas de impedância)."""
        rows: list[list[Optional[float]]] = [
            [
                float(f),
                float(zr),
                float(mzi),
                float(zm),
                float(ph),
                None,
                None,
            ]
            for f, zr, mzi, zm, ph in zip(
                measurement.frequency,
                measurement.z_real,
                measurement.minus_z_imag,
                measurement.magnitude,
                measurement.phase_deg,
            )
        ]
        self.table.set_rows(rows)

    def _on_add_measurement(self) -> None:
        """Cria uma medição a partir da tabela (pede o nome).

        Aplica a correção do instrumento escolhida no seletor, se
        houver — assim a medição já entra corrigida na lista.
        """
        name, ok = QInputDialog.getText(
            self,
            "Nova medição",
            "Nome da medição (ex.: FRA0F, 3 pancadas):",
        )
        if not ok or not name.strip():
            return
        clean_name = name.strip()
        try:
            measurement = self.build_measurement(clean_name)
        except ValueError as exc:
            QMessageBox.warning(self, "Nova medição", str(exc))
            return
        correction = self._selected_correction()
        if correction is not None:
            try:
                measurement = correction.apply(
                    measurement, new_name=clean_name
                )
            except (ValueError, RuntimeError) as exc:
                QMessageBox.warning(
                    self,
                    "Correção do instrumento",
                    f"Não foi possível aplicar a correção "
                    f"'{correction.name}':\n{exc}",
                )
                return
        self.measurementCreated.emit(measurement)

    def _on_update_measurement(self) -> None:
        """Atualiza a medição selecionada com os dados da tabela.

        Aplica a correção do instrumento escolhida no seletor, se
        houver — assim a medição selecionada passa a ser a versão
        corrigida.
        """
        try:
            measurement = self.build_measurement("__temporario__")
        except ValueError as exc:
            QMessageBox.warning(self, "Atualizar medição", str(exc))
            return
        correction = self._selected_correction()
        if correction is not None:
            try:
                measurement = correction.apply(
                    measurement, new_name="__temporario__"
                )
            except (ValueError, RuntimeError) as exc:
                QMessageBox.warning(
                    self,
                    "Correção do instrumento",
                    f"Não foi possível aplicar a correção "
                    f"'{correction.name}':\n{exc}",
                )
                return
        self.measurementUpdated.emit(measurement)


# ---------------------------------------------------------------------------
# Aba de curvas I-V do módulo
# ---------------------------------------------------------------------------
class IVTable(PasteableTable):
    """Tabela de entrada de curva I-V (tensão, corrente, potência).

    A coluna de potência é calculada automaticamente
    (``P = V·I``) e recalculada a cada edição ou colagem.
    """

    _COLUMNS = ("Tensão (V)", "Corrente (A)", "Potência (W)")
    _COL_V = 0
    _COL_I = 1
    _COL_P = 2

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(self._COLUMNS, initial_rows=50, parent=parent)
        self.cellChanged.connect(self._on_cell_changed)
        self.pasted.connect(self._on_pasted)

    def _on_cell_changed(self, row: int, _column: int) -> None:
        self.blockSignals(True)
        try:
            self._complete_row(row)
        finally:
            self.blockSignals(False)

    def _on_pasted(self, first_row: int, last_row: int) -> None:
        self.blockSignals(True)
        try:
            for row in range(first_row, last_row + 1):
                self._complete_row(row)
        finally:
            self.blockSignals(False)

    def _complete_row(self, row: int) -> None:
        """Atualiza a potência da linha (``P = V·I``)."""
        volt = self.get_value(row, self._COL_V)
        curr = self.get_value(row, self._COL_I)
        if volt is not None and curr is not None:
            self.set_value(row, self._COL_P, volt * curr)
        else:
            self.set_value(row, self._COL_P, None)


class IVTab(QWidget):
    """Aba "Curva I-V": entrada e gráficos das curvas das amostras.

    As curvas exibidas seguem as **amostras marcadas na lista lateral
    "Medições"** — as amostras são compartilhadas entre o FRA (EIS) e
    a curva I-V.  Uma amostra que só tem FRA (sem curva I-V) não
    aparece no gráfico desta aba.
    """

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self._window = window

        # -- Entrada -----------------------------------------------------
        hint = QLabel(
            "Digite ou cole (Ctrl+V) pares de tensão e corrente da "
            "varredura I-V do módulo — a potência é calculada "
            "automaticamente. \"Adicionar como curva\" cria/associa a "
            "curva a uma amostra; \"Atualizar\" substitui a curva da "
            "amostra selecionada na lista lateral. As curvas ficam "
            "atreladas às amostras (mesma lista do FRA).",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9a9a9a;")

        self.table = IVTable(self)

        import_button = QPushButton("Importar…", self)
        import_button.clicked.connect(self._on_import)
        add_rows_button = QPushButton("Adicionar linhas", self)
        add_rows_button.clicked.connect(lambda: self.table.add_rows(20))
        clear_button = QPushButton("Limpar tabela", self)
        clear_button.clicked.connect(self.table.clear_all)
        load_button = QPushButton("Carregar curva na tabela", self)
        load_button.setToolTip(
            "Carrega na tabela a curva I-V da amostra selecionada na "
            "lista lateral \"Medições\"."
        )
        load_button.clicked.connect(self._on_load)
        add_curve_button = QPushButton("Adicionar como curva I-V", self)
        add_curve_button.setToolTip(
            "Cria a curva I-V com os dados da tabela e a associa a uma "
            "amostra (nova ou existente, pelo nome)."
        )
        add_curve_button.clicked.connect(self._on_add_curve)
        update_curve_button = QPushButton(
            "Atualizar curva da amostra selec.", self
        )
        update_curve_button.setToolTip(
            "Substitui a curva I-V da amostra selecionada na lista "
            "lateral pelos dados da tabela."
        )
        update_curve_button.clicked.connect(self._on_update_curve)
        associate_button = QPushButton("Associar curvas I-V…", self)
        associate_button.setToolTip(
            "Abre uma tabela para associar cada curva I-V à amostra "
            "(FRA) correspondente."
        )
        associate_button.clicked.connect(self._on_associate)
        fit_button = QPushButton("  Ajustar modelo de diodo…", self)
        fit_button.setIcon(
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_FileDialogDetailedView
            )
        )
        fit_button.setToolTip(
            "Estima os parâmetros do módulo (I_L, I₀, Rs, Rp, a) "
            "ajustando o modelo de diodo único à curva I-V."
        )
        fit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        fit_button.setMinimumHeight(36)
        # Botão de destaque (ação principal da aba): estilo "accent".
        fit_button.setStyleSheet(
            "QPushButton {"
            " background-color: #0e639c; color: #ffffff;"
            " font-weight: 600; border: 1px solid #1f8ad0;"
            " border-radius: 5px; padding: 8px 16px; text-align: center; }"
            "QPushButton:hover { background-color: #1177bb;"
            " border-color: #3aa0e0; }"
            "QPushButton:pressed { background-color: #0a4f7a; }"
        )
        fit_button.clicked.connect(self._on_fit_diode)
        export_button = QPushButton("Exportar Excel…", self)
        export_button.clicked.connect(self._on_export_excel)

        entry_buttons1 = QHBoxLayout()
        entry_buttons1.addWidget(import_button)
        entry_buttons1.addWidget(add_rows_button)
        entry_buttons1.addWidget(clear_button)
        entry_buttons1.addWidget(load_button)
        entry_buttons2 = QHBoxLayout()
        entry_buttons2.addWidget(add_curve_button)
        entry_buttons2.addWidget(update_curve_button)
        entry_buttons2.addWidget(associate_button)
        entry_buttons3 = QHBoxLayout()
        entry_buttons3.addWidget(export_button)
        # Linha própria em destaque para a ação principal.
        entry_buttons_fit = QHBoxLayout()
        entry_buttons_fit.addWidget(fit_button, 1)

        entry = QVBoxLayout()
        entry.addWidget(hint)
        entry.addWidget(self.table, 1)
        entry.addLayout(entry_buttons1)
        entry.addLayout(entry_buttons2)
        entry.addLayout(entry_buttons3)
        entry.addLayout(entry_buttons_fit)
        entry_widget = QWidget(self)
        entry_widget.setLayout(entry)
        entry_widget.setMaximumWidth(460)

        # -- Gráfico -------------------------------------------------------
        right_hint = QLabel(
            "As curvas exibidas seguem as amostras marcadas na lista "
            "lateral \"Medições\". Amostras sem curva I-V não aparecem. "
            "Cor, fundo e estilo vêm do dock \"Estilo dos gráficos\".",
            self,
        )
        right_hint.setWordWrap(True)
        right_hint.setStyleSheet("color: #9a9a9a;")

        self.power_checkbox = QCheckBox(
            "Mostrar P×V (eixo direito)", self
        )
        self.power_checkbox.setChecked(True)
        self.power_checkbox.toggled.connect(
            lambda _checked: self.refresh()
        )
        self.pmax_checkbox = QCheckBox("Marcar Pmáx", self)
        self.pmax_checkbox.setChecked(True)
        self.pmax_checkbox.toggled.connect(
            lambda _checked: self.refresh()
        )

        self.canvas = PlotCanvas(self)

        self.params_table = QTableWidget(0, 7, self)
        self.params_table.setHorizontalHeaderLabels(
            ["Amostra", "Isc (A)", "Voc (V)", "Pmáx (W)", "Vmp (V)",
             "Imp (A)", "FF"]
        )
        self.params_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.params_table.verticalHeader().setVisible(False)
        self.params_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.params_table.setMaximumHeight(170)

        options_row = QHBoxLayout()
        options_row.addStretch(1)
        options_row.addWidget(self.power_checkbox)
        options_row.addWidget(self.pmax_checkbox)

        right = QVBoxLayout()
        right.addWidget(right_hint)
        right.addLayout(options_row)
        right.addWidget(self.canvas, 1)
        right.addWidget(self.params_table)
        right_widget = QWidget(self)
        right_widget.setLayout(right)

        layout = QHBoxLayout(self)
        layout.addWidget(entry_widget)
        layout.addWidget(right_widget, 1)

    # -- Curvas da sessão -----------------------------------------------------
    def checked_curves(self) -> list[util.IVCurve]:
        """Curvas I-V das amostras marcadas na lista lateral."""
        return self._window.checked_iv_curves()

    # -- Ações de entrada -------------------------------------------------------
    def build_curve(self, name: str) -> util.IVCurve:
        """Constrói uma :class:`util.IVCurve` com os dados da tabela."""
        rows = [
            [row[IVTable._COL_V], row[IVTable._COL_I]]
            for row in self.table.get_rows()
        ]
        if not rows:
            raise ValueError("A tabela está vazia.")
        return util.IVCurve.from_rows(name, rows)

    def _on_add_curve(self) -> None:
        default = self._window.selected_sample_name(warn=False) or ""
        name, ok = QInputDialog.getText(
            self,
            "Nova curva I-V",
            "Nome da amostra (para associar a uma amostra existente, "
            "use o mesmo nome):",
            text=default,
        )
        if not ok or not name.strip():
            return
        try:
            curve = self.build_curve(name.strip())
        except ValueError as exc:
            QMessageBox.warning(self, "Nova curva I-V", str(exc))
            return
        self._window.add_iv_curve(curve)

    def _on_update_curve(self) -> None:
        name = self._window.selected_sample_name()
        if name is None:
            return
        try:
            curve = self.build_curve(name)
        except ValueError as exc:
            QMessageBox.warning(self, "Atualizar curva", str(exc))
            return
        self._window.iv_curves[name] = curve
        self._window.iv_fit_results.pop(name, None)
        self._window.update_sample_tooltip(name)
        self.refresh()
        self._window.show_status(
            f"Curva I-V da amostra '{name}' atualizada."
        )

    def _on_import(self) -> None:
        """Importa curva(s) I-V de um arquivo.

        Arquivos em formato de matriz (uma coluna de tensão e várias
        colunas de corrente, cada uma uma curva) são reconhecidos: o
        programa oferece adicionar todas as curvas separadamente à
        lista.  Arquivos simples de duas colunas são carregados na
        tabela para edição.
        """
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar curva I-V",
            "",
            "Arquivos de dados (*.csv *.txt *.dat *.xlsx *.xlsm *.ods);;"
            "Todos os arquivos (*)",
        )
        if not path:
            return

        curves: list[util.IVCurve] = []
        try:
            curves = util.load_iv_curves_from_file(path)
        except (ValueError, OSError, ImportError) as exc:
            logger.warning(
                "Falha ao detectar múltiplas curvas I-V em '%s': %s",
                path,
                exc,
            )

        if len(curves) >= 2:
            targets = self._window.sample_names()
            dialog = IVAssociationDialog(
                self,
                [c.name for c in curves],
                targets,
                include_new=True,
                include_skip=True,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            added = self._window.import_iv_curves_with_mapping(
                curves, dialog.mapping()
            )
            self._window.show_status(
                f"{added} curva(s) I-V importada(s)/associada(s) de "
                f"'{path}'."
            )
            return

        try:
            rows = util.load_iv_table_from_file(path)
        except (ValueError, OSError, ImportError) as exc:
            logger.exception("Falha ao importar curva I-V de '%s'.", path)
            QMessageBox.critical(
                self,
                "Importar curva I-V",
                f"Não foi possível importar o arquivo:\n{exc}",
            )
            return
        self.table.set_rows(rows)
        self._window.show_status(
            f"{len(rows)} linha(s) importada(s) para a tabela I-V."
        )

    def _on_load(self) -> None:
        """Carrega na tabela a curva I-V da amostra selecionada."""
        name = self._window.selected_sample_name()
        if name is None:
            return
        curve = self._window.iv_curves.get(name)
        if curve is None:
            QMessageBox.information(
                self,
                "Curva I-V",
                f"A amostra '{name}' não tem curva I-V. Cole os dados "
                "e use \"Adicionar como curva I-V\" para criar uma.",
            )
            return
        self.table.set_rows(
            [
                [float(v), float(i), float(v) * float(i)]
                for v, i in zip(curve.voltage, curve.current)
            ]
        )
        self._window.show_status(
            f"Curva I-V da amostra '{name}' carregada na tabela."
        )

    def _on_export_excel(self) -> None:
        curves = self.checked_curves()
        if not curves:
            QMessageBox.information(
                self,
                "Exportar curvas I-V",
                "Marque ao menos uma amostra (com curva I-V) na lista "
                "lateral.",
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar curvas I-V",
            "curvas_iv.xlsx",
            "Planilha do Excel (*.xlsx)",
        )
        if not path:
            return
        try:
            exportacao.export_iv_excel(curves, path)
        except (OSError, ValueError) as exc:
            logger.exception("Falha ao exportar curvas I-V.")
            QMessageBox.critical(
                self,
                "Exportar curvas I-V",
                f"Não foi possível exportar:\n{exc}",
            )
            return
        self._window.show_status(f"Curvas I-V exportadas: {path}")

    def _on_associate(self) -> None:
        """Reassocia as curvas I-V existentes às amostras (FRA)."""
        iv_names = [
            name
            for name in self._window.sample_names()
            if name in self._window.iv_curves
        ]
        if not iv_names:
            QMessageBox.information(
                self,
                "Associar curvas I-V",
                "Não há curvas I-V para associar. Importe ou crie "
                "curvas primeiro.",
            )
            return
        targets = self._window.sample_names()
        dialog = IVAssociationDialog(
            self,
            iv_names,
            targets,
            include_new=False,
            include_skip=False,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        moved = self._window.reassign_iv_curves(dialog.mapping())
        self._window.show_status(
            f"{moved} curva(s) I-V reassociada(s) às amostras."
        )

    def _on_fit_diode(self) -> None:
        """Abre o ajuste do modelo de diodo único das curvas I-V."""
        iv_names = [
            name
            for name in self._window.sample_names()
            if name in self._window.iv_curves
        ]
        if not iv_names:
            QMessageBox.information(
                self,
                "Ajustar modelo de diodo",
                "Não há curvas I-V para ajustar. Importe ou crie uma "
                "curva primeiro.",
            )
            return
        initial = self._window.selected_sample_name(warn=False)
        if initial not in iv_names:
            initial = iv_names[0]
        dialog = DiodeFitDialog(self, self._window, initial)
        dialog.exec()

    # -- Gráfico e parâmetros ---------------------------------------------------
    def refresh(self) -> None:
        """Redesenha as curvas marcadas e atualiza os parâmetros."""
        curves = self.checked_curves()
        style = self._window.plot_style()
        annotate = self.pmax_checkbox.isChecked()

        self.canvas.clear()
        if curves:
            ax = self.canvas.figure.add_subplot(111)
            color_map: dict[str, str] = {}
            for curve in curves:
                line, = ax.plot(
                    curve.voltage,
                    curve.current,
                    label=curve.name,
                    **style.line_kwargs_for(curve.name),
                )
                color_map[curve.name] = line.get_color()
                if annotate:
                    ax.plot(
                        [curve.v_mp], [curve.i_mp],
                        marker="x", markersize=9,
                        markeredgewidth=2.0, linestyle="none",
                        color=line.get_color(),
                    )
            ax.set_xlabel("Tensão (V)")
            ax.set_ylabel("Corrente (A)")
            ax.set_title("Curva I-V do módulo")
            ax.grid(style.show_grid, which="both")
            ax.legend(loc="best", fontsize=8)
            apply_background(ax, style)

            if self.power_checkbox.isChecked():
                ax2 = ax.twinx()
                for curve in curves:
                    ax2.plot(
                        curve.voltage,
                        curve.power,
                        linestyle="--",
                        linewidth=max(style.line_width * 0.9, 0.6),
                        color=color_map[curve.name],
                        alpha=0.75,
                    )
                    if annotate:
                        ax2.plot(
                            [curve.v_mp], [curve.p_max],
                            marker="*", markersize=10,
                            linestyle="none",
                            color=color_map[curve.name],
                        )
                ax2.set_ylabel("Potência (W)  (tracejado)")
                ax2.grid(False)
        self.canvas.draw()

        self.params_table.setRowCount(len(curves))
        for row, curve in enumerate(curves):
            metrics = curve.metrics()
            values = [
                curve.name,
                f"{metrics['isc']:.4g}",
                f"{metrics['voc']:.4g}",
                f"{metrics['p_max']:.4g}",
                f"{metrics['v_mp']:.4g}",
                f"{metrics['i_mp']:.4g}",
                f"{metrics['fill_factor']:.4g}",
            ]
            for column, text in enumerate(values):
                self.params_table.setItem(
                    row, column, QTableWidgetItem(text)
                )


# ---------------------------------------------------------------------------
# Associação de curvas I-V às amostras
# ---------------------------------------------------------------------------
class IVAssociationDialog(QDialog):
    """Diálogo para associar curvas I-V às amostras (FRA).

    Exibe uma tabela com cada curva I-V e um seletor da amostra à qual
    ela pertence.  Usado ao importar várias curvas (para atrelá-las aos
    FRAs existentes) e para reassociar depois.
    """

    #: Valor especial: manter/criar a curva como amostra nova.
    NEW = "__new__"
    #: Valor especial: não importar/ignorar a curva.
    SKIP = "__skip__"

    def __init__(
        self,
        parent: Optional[QWidget],
        curve_names: Sequence[str],
        targets: Sequence[str],
        include_new: bool = True,
        include_skip: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Associar curvas I-V às amostras")
        self.resize(560, 460)
        self._curve_names = list(curve_names)
        self._targets = list(targets)
        self._include_new = include_new
        self._include_skip = include_skip

        hint = QLabel(
            "Para cada curva I-V, escolha a amostra à qual ela pertence "
            "(por exemplo, a amostra que já tem o FRA). \"Nova amostra\" "
            "mantém a curva com o próprio nome. Use \"Associar por nome\" "
            "para casar automaticamente curvas e amostras de mesmo nome.",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9a9a9a;")

        self.table = QTableWidget(
            len(self._curve_names), 2, self
        )
        self.table.setHorizontalHeaderLabels(
            ["Curva I-V", "Associar à amostra"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.verticalHeader().setVisible(False)
        self._combos: list[QComboBox] = []
        for row, name in enumerate(self._curve_names):
            name_item = QTableWidgetItem(name)
            name_item.setFlags(
                name_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )
            self.table.setItem(row, 0, name_item)
            combo = QComboBox(self)
            if include_new:
                combo.addItem(f"Nova amostra ({name})", self.NEW)
            for target in self._targets:
                combo.addItem(f"Amostra: {target}", target)
            if include_skip:
                combo.addItem("Não importar", self.SKIP)
            self.table.setCellWidget(row, 1, combo)
            self._combos.append(combo)

        auto_button = QPushButton("Associar por nome", self)
        auto_button.clicked.connect(self._auto_match)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Aplicar"
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        top = QHBoxLayout()
        top.addWidget(auto_button)
        top.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addWidget(button_box)

        self._auto_match()

    def _auto_match(self) -> None:
        """Seleciona a amostra de mesmo nome (normalizado) por linha."""
        normalized = {
            self._normalize(t): t for t in self._targets
        }
        for row, name in enumerate(self._curve_names):
            combo = self._combos[row]
            target = normalized.get(self._normalize(name))
            if target is not None:
                index = combo.findData(target)
                if index >= 0:
                    combo.setCurrentIndex(index)

    @staticmethod
    def _normalize(text: str) -> str:
        return "".join(text.lower().split())

    def mapping(self) -> dict[str, str]:
        """Mapeamento ``{nome da curva: alvo}`` escolhido pelo usuário.

        O alvo é o nome de uma amostra, :attr:`NEW` ou :attr:`SKIP`.
        """
        return {
            name: self._combos[row].currentData()
            for row, name in enumerate(self._curve_names)
        }


# ---------------------------------------------------------------------------
# Ajuste do modelo de diodo único (curva I-V)
# ---------------------------------------------------------------------------
class DiodeFitDialog(QDialog):
    """Ajuste do modelo de diodo único de uma curva I-V.

    Estima os cinco parâmetros do módulo fotovoltaico real
    (``I_L, I_0, R_s, R_p, a``) ajustando a equação do diodo único à
    curva I-V medida, à semelhança do ajuste de circuito equivalente do
    FRA.  Exibe os parâmetros com incertezas, as métricas de qualidade
    (RMSE, R², fator de idealidade) e a sobreposição do modelo sobre os
    dados experimentais.
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        window: "MainWindow",
        initial_name: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self._window = window
        self.setWindowTitle("Ajuste do modelo de diodo único — Curva I-V")
        self.resize(940, 620)
        self._last_result: Optional[iv_model.IVFitResult] = None

        hint = QLabel(
            "Ajusta o modelo do módulo fotovoltaico real (diodo único, "
            "cinco parâmetros) à curva I-V. A convenção de sinal (curva "
            "escura ou iluminada) é detectada automaticamente.",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9a9a9a;")

        equation = QLabel(self)
        equation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        equation.setPixmap(
            mathtext_to_pixmap(
                r"$I = I_\mathrm{L} - I_0\left[\exp\!\left("
                r"\frac{V + I\,R_\mathrm{s}}{a}\right) - 1\right]"
                r" - \frac{V + I\,R_\mathrm{s}}{R_\mathrm{p}}$",
                fontsize=17,
                color="#e8e8e8",
            )
        )
        equation.setScaledContents(False)
        equation.setStyleSheet(
            "QLabel { background: rgba(255, 255, 255, 0.06);"
            " border: 1px solid #5a6472; border-radius: 6px;"
            " padding: 10px; margin: 2px 0; }"
        )

        self.curve_combo = QComboBox(self)
        for name in self._window.sample_names():
            if name in self._window.iv_curves:
                self.curve_combo.addItem(name, name)
        if initial_name is not None:
            index = self.curve_combo.findData(initial_name)
            if index >= 0:
                self.curve_combo.setCurrentIndex(index)
        # Trocar a amostra atualiza o gráfico automaticamente (reaproveita
        # o ajuste já calculado; ajusta na hora se ainda não houver um).
        self.curve_combo.currentIndexChanged.connect(
            lambda _index: self._on_curve_changed()
        )

        self.cells_spin = QSpinBox(self)
        self.cells_spin.setRange(1, 1000)
        self.cells_spin.setValue(36)
        self.cells_spin.setToolTip(
            "Número de células em série (Ns) do módulo. Apenas "
            "informativo: serve só para derivar o fator de idealidade "
            "n a partir de a — não afeta o ajuste."
        )
        self.temp_spin = QDoubleSpinBox(self)
        self.temp_spin.setRange(-40.0, 150.0)
        self.temp_spin.setValue(25.0)
        self.temp_spin.setSuffix(" °C")
        self.temp_spin.setDecimals(1)
        self.cells_spin.valueChanged.connect(self._update_ideality)
        self.temp_spin.valueChanged.connect(self._update_ideality)

        form = QFormLayout()
        form.addRow("Amostra (curva I-V):", self.curve_combo)
        form.addRow("Células em série (Ns):", self.cells_spin)
        form.addRow("Temperatura da célula:", self.temp_spin)

        self.fit_button = QPushButton("Ajustar", self)
        self.fit_button.clicked.connect(self._run_fit)
        self.fit_all_button = QPushButton("Ajustar todas…", self)
        self.fit_all_button.setToolTip(
            "Ajusta todas as curvas I-V e mostra a comparação dos "
            "parâmetros entre as amostras."
        )
        self.fit_all_button.clicked.connect(self._run_fit_all)
        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.fit_button)
        buttons_row.addWidget(self.fit_all_button)

        self.params_table = QTableWidget(0, 3, self)
        self.params_table.setHorizontalHeaderLabels(
            ["Parâmetro", "Valor", "Incerteza (1σ)"]
        )
        self.params_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.params_table.verticalHeader().setVisible(False)
        self.params_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        self.stats_label = QLabel("—", self)
        self.stats_label.setWordWrap(True)

        note = QLabel(
            "Nota: a partir de uma única curva, Rs, Rp e a são "
            "correlacionados — o modelo reproduz a curva (R² alto), mas "
            "os valores individuais têm incerteza. I_L (≈ Isc) e o "
            "formato são os mais confiáveis.",
            self,
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #8a8a8a; font-size: 11px;")

        left = QVBoxLayout()
        left.addWidget(hint)
        left.addWidget(equation)
        left.addLayout(form)
        left.addLayout(buttons_row)
        left.addWidget(self.params_table, 1)
        stats_box = QGroupBox("Qualidade do ajuste", self)
        stats_layout = QVBoxLayout(stats_box)
        stats_layout.addWidget(self.stats_label)
        left.addWidget(stats_box)
        left.addWidget(note)
        left_widget = QWidget(self)
        left_widget.setLayout(left)
        left_widget.setMaximumWidth(420)

        self.canvas = PlotCanvas(self)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close, self
        )
        button_box.rejected.connect(self.reject)
        button_box.button(
            QDialogButtonBox.StandardButton.Close
        ).clicked.connect(self.reject)

        content = QHBoxLayout()
        content.addWidget(left_widget)
        content.addWidget(self.canvas, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(content, 1)
        layout.addWidget(button_box)

        if self.curve_combo.count() > 0:
            self._on_curve_changed()

    def _selected_curve(self) -> Optional[util.IVCurve]:
        name = self.curve_combo.currentData()
        if name is None:
            return None
        return self._window.iv_curves.get(name)

    def _on_curve_changed(self) -> None:
        """Reage à troca de amostra no seletor.

        Mostra imediatamente o ajuste já calculado da amostra
        selecionada (o ajuste é determinístico e o cache é invalidado
        quando os dados mudam); se ainda não houver um ajuste, calcula
        na hora.  Assim, trocar de amostra atualiza o gráfico sem exigir
        um novo clique em "Ajustar".
        """
        name = self.curve_combo.currentData()
        if name is None:
            return
        cached = self._window.iv_fit_results.get(name)
        if cached is not None:
            self._display_result(cached)
            self._window.show_status(
                f"Ajuste de diodo de '{name}' "
                f"(R² = {cached.r_squared:.6f})."
            )
        else:
            self._run_fit()

    def _run_fit(self) -> None:
        curve = self._selected_curve()
        if curve is None:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = iv_model.fit_single_diode(curve)
        except (ValueError, RuntimeError) as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Ajuste do modelo de diodo", str(exc))
            return
        except Exception as exc:  # pragma: no cover - proteção geral
            QApplication.restoreOverrideCursor()
            logger.exception("Erro inesperado no ajuste de diodo.")
            QMessageBox.critical(
                self,
                "Ajuste do modelo de diodo",
                f"Erro inesperado no ajuste:\n{exc}",
            )
            return
        QApplication.restoreOverrideCursor()

        self._window.iv_fit_results[result.curve_name] = result
        self._display_result(result)
        self._window.show_status(
            f"Ajuste de diodo de '{result.curve_name}' concluído "
            f"(R² = {result.r_squared:.6f})."
        )

    def _display_result(self, result: "iv_model.IVFitResult") -> None:
        """Renderiza um ajuste: gráfico, tabela de parâmetros e métricas."""
        self._last_result = result
        self.canvas.clear()
        plot_diode_fit(
            self.canvas.figure, result, self._window.plot_style()
        )
        self.canvas.draw()

        self.params_table.setRowCount(0)
        for param_name, value_text, error_text in result.summary_rows():
            row = self.params_table.rowCount()
            self.params_table.insertRow(row)
            self.params_table.setItem(
                row, 0, QTableWidgetItem(param_name)
            )
            self.params_table.setItem(row, 1, QTableWidgetItem(value_text))
            self.params_table.setItem(row, 2, QTableWidgetItem(error_text))

        self._update_ideality()

    def _update_ideality(self) -> None:
        """Atualiza o texto de métricas com o fator de idealidade."""
        result = self._last_result
        if result is None:
            self.stats_label.setText("—")
            return
        n = result.ideality_factor(
            n_cells=self.cells_spin.value(),
            temperature_c=self.temp_spin.value(),
        )
        tipo = "escura (dark I-V)" if result.dark else "iluminada"
        self.stats_label.setText(
            f"Curva: {tipo}\n"
            f"RMSE = {result.rmse:.4g} A\n"
            f"R² = {result.r_squared:.6f}\n"
            f"Fator de idealidade n = {n:.3g}  "
            f"(Ns={self.cells_spin.value()}, "
            f"T={self.temp_spin.value():.0f} °C)"
        )

    def _run_fit_all(self) -> None:
        """Ajusta todas as curvas I-V e mostra a comparação."""
        names = [
            self.curve_combo.itemData(i)
            for i in range(self.curve_combo.count())
        ]
        results: list[iv_model.IVFitResult] = []
        failures: list[str] = []
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        for name in names:
            curve = self._window.iv_curves.get(name)
            if curve is None:
                continue
            try:
                result = iv_model.fit_single_diode(curve)
            except (ValueError, RuntimeError) as exc:
                failures.append(f"{name}: {exc}")
                continue
            results.append(result)
            self._window.iv_fit_results[result.curve_name] = result
        QApplication.restoreOverrideCursor()

        if not results:
            QMessageBox.warning(
                self,
                "Ajustar todas",
                "Nenhuma curva pôde ser ajustada.\n"
                + "\n".join(failures),
            )
            return
        DiodeFitComparisonDialog(self, results, failures).exec()
        self._window.show_status(
            f"{len(results)} curva(s) I-V ajustada(s) pelo modelo de "
            "diodo."
        )


class DiodeFitComparisonDialog(QDialog):
    """Tabela comparativa dos parâmetros de diodo entre amostras."""

    def __init__(
        self,
        parent: Optional[QWidget],
        results: Sequence["iv_model.IVFitResult"],
        failures: Sequence[str] = (),
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Comparação — modelo de diodo entre amostras")
        self.resize(760, 420)

        headers = [
            "Amostra", "I_L (A)", "I₀ (A)", "Rs (Ω)", "Rp (Ω)",
            "a (V)", "R²", "Tipo",
        ]
        table = QTableWidget(len(results), len(headers), self)
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        for row, res in enumerate(results):
            p = res.param_values
            cells = [
                res.curve_name,
                f"{p[0]:.4g}", f"{p[1]:.3g}", f"{p[2]:.4g}",
                f"{p[3]:.4g}", f"{p[4]:.4g}", f"{res.r_squared:.5f}",
                "escura" if res.dark else "iluminada",
            ]
            for col, text in enumerate(cells):
                table.setItem(row, col, QTableWidgetItem(text))

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(f"{len(results)} amostra(s) ajustada(s).", self)
        )
        layout.addWidget(table, 1)
        if failures:
            warn = QLabel(
                "Não ajustadas:\n" + "\n".join(failures), self
            )
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #d08770;")
            layout.addWidget(warn)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close, self
        )
        button_box.rejected.connect(self.reject)
        button_box.button(
            QDialogButtonBox.StandardButton.Close
        ).clicked.connect(self.reject)
        layout.addWidget(button_box)


# ---------------------------------------------------------------------------
# Janela de Correção do Instrumento
# ---------------------------------------------------------------------------
class CorrectionDialog(QDialog):
    """Janela "Correção do Instrumento" (biblioteca de correções).

    Gerencia várias correções nomeadas (uma por instrumento/resistor
    padrão).  Para cada correção, permite inserir (digitar, colar ou
    importar) a frequência, a magnitude e a fase do resistor padrão,
    calcula a impedância complexa e a função de transferência
    ``H(f)`` e exibe a pré-visualização de ``|H|`` e da fase de ``H``.

    Ao fechar com "Salvar", a biblioteca atualizada fica disponível em
    :attr:`corrections` (dicionário ``{nome: InstrumentCorrection}``).
    """

    _NEW_ENTRY = "(Nova correção)"

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        corrections: Optional[
            "dict[str, InstrumentCorrection]"
        ] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Correção do Instrumento")
        self.resize(940, 660)
        #: Biblioteca de correções (cópia de trabalho).
        self.corrections: dict[str, InstrumentCorrection] = dict(
            corrections or {}
        )

        # -- Seleção da correção -----------------------------------------
        self.select_combo = QComboBox(self)
        self.select_combo.currentIndexChanged.connect(
            self._on_select_changed
        )
        self.remove_button = QPushButton("Remover correção", self)
        self.remove_button.clicked.connect(self._on_remove)

        self.name_edit = QLineEdit(self)
        self.name_edit.setPlaceholderText(
            "Ex.: Instrumento A (resistor 100 Ω)"
        )
        self.name_edit.setToolTip(
            "Nome da correção — identifica o instrumento/resistor."
        )

        self.table = PasteableTable(
            ("Frequência (Hz)", "Magnitude (Ω)", "Fase (°)"),
            initial_rows=40,
            parent=self,
        )

        self.r_nominal_edit = QLineEdit(self)
        self.r_nominal_edit.setPlaceholderText("Ex.: 100")
        self.r_nominal_edit.setToolTip(
            "Valor nominal do resistor padrão, em ohms."
        )

        self.import_button = QPushButton("Importar…", self)
        self.import_button.clicked.connect(self._on_import)

        self.export_button = QPushButton("Exportar…", self)
        self.export_button.setToolTip(
            "Salva a tabela da correção (frequência, magnitude, fase e "
            "H(f) calculada) em CSV ou Excel."
        )
        self.export_button.clicked.connect(self._on_export)

        self.compute_button = QPushButton("Calcular H(f)", self)
        self.compute_button.clicked.connect(self._on_compute)

        self.save_button = QPushButton("Salvar correção na lista", self)
        self.save_button.setToolTip(
            "Guarda a correção atual na biblioteca sem fechar a janela."
        )
        self.save_button.clicked.connect(self._on_save_current)

        self.status_label = QLabel(
            "Selecione \"(Nova correção)\", dê um nome, insira os dados "
            "do resistor padrão e clique em \"Calcular H(f)\".",
            self,
        )
        self.status_label.setWordWrap(True)

        self.canvas = PlotCanvas(self)

        select_row = QHBoxLayout()
        select_row.addWidget(QLabel("Correção:", self))
        select_row.addWidget(self.select_combo, 1)
        select_row.addWidget(self.remove_button)

        form = QFormLayout()
        form.addRow("Nome:", self.name_edit)
        form.addRow("Resistor padrão (Ω):", self.r_nominal_edit)

        left = QVBoxLayout()
        left.addLayout(select_row)
        left.addLayout(form)
        left.addWidget(self.table, 1)
        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.import_button)
        buttons_row.addWidget(self.export_button)
        buttons_row.addWidget(self.compute_button)
        buttons_row.addWidget(self.save_button)
        buttons_row.addStretch(1)
        left.addLayout(buttons_row)

        left_widget = QWidget(self)
        left_widget.setLayout(left)

        content = QHBoxLayout()
        content.addWidget(left_widget, 1)
        content.addWidget(self.canvas, 1)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.button_box.button(
            QDialogButtonBox.StandardButton.Ok
        ).setText("Salvar e fechar")
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(content, 1)
        layout.addWidget(self.status_label)
        layout.addWidget(self.button_box)

        self._reload_combo(select_first_existing=True)

    # -- Biblioteca ----------------------------------------------------------
    def _reload_combo(self, select_first_existing: bool = False) -> None:
        """Repovoa o combo com a biblioteca atual."""
        self.select_combo.blockSignals(True)
        try:
            self.select_combo.clear()
            self.select_combo.addItem(self._NEW_ENTRY)
            for name in self.corrections:
                self.select_combo.addItem(name)
        finally:
            self.select_combo.blockSignals(False)
        if select_first_existing and self.corrections:
            self.select_combo.setCurrentIndex(1)
            self._on_select_changed(1)
        else:
            self.select_combo.setCurrentIndex(0)
            self._on_select_changed(0)

    def _on_select_changed(self, _index: int) -> None:
        """Carrega a correção escolhida (ou limpa para uma nova)."""
        name = self.select_combo.currentText()
        if name == self._NEW_ENTRY or name not in self.corrections:
            self.table.clear_all()
            self.r_nominal_edit.clear()
            self.name_edit.setText(
                unique_name("Correção", list(self.corrections))
            )
            self.canvas.clear()
            self.canvas.draw()
            self.remove_button.setEnabled(False)
            return
        self.remove_button.setEnabled(True)
        self._load_existing(self.corrections[name])

    def _on_remove(self) -> None:
        """Remove a correção selecionada da biblioteca."""
        name = self.select_combo.currentText()
        if name == self._NEW_ENTRY or name not in self.corrections:
            return
        answer = QMessageBox.question(
            self,
            "Remover correção",
            f"Remover a correção '{name}' da biblioteca?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.corrections.pop(name, None)
        self._reload_combo()

    def _load_existing(self, correction: InstrumentCorrection) -> None:
        """Preenche a janela com uma correção existente."""
        rows: list[list[Optional[float]]] = [
            [float(f), float(m), float(p)]
            for f, m, p in zip(
                correction.frequency,
                correction.magnitude,
                correction.phase_deg,
            )
        ]
        self.table.set_rows(rows)
        self.r_nominal_edit.setText(
            _CELL_FORMAT.format(correction.r_nominal)
        )
        self.name_edit.setText(correction.name)
        self._plot(correction)

    def _on_import(self) -> None:
        """Importa os dados do resistor padrão de um arquivo."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar dados do resistor padrão",
            "",
            "Arquivos de dados (*.csv *.txt *.dat *.xlsx *.xlsm *.ods);;"
            "Todos os arquivos (*)",
        )
        if not path:
            return
        try:
            canonical, had_header = util.load_table_from_file_ex(path)
        except (ValueError, OSError, ImportError) as exc:
            logger.exception("Falha ao importar correção de '%s'.", path)
            QMessageBox.critical(
                self,
                "Importar dados",
                f"Não foi possível importar o arquivo:\n{exc}",
            )
            return
        rows: list[list[Optional[float]]] = []
        for row in canonical:
            freq = row[COL_FREQ]
            magnitude = row[COL_ZMOD]
            phase = row[COL_PHASE]
            z_re = row[COL_ZREAL]
            minus_z_im = row[COL_MINUS_ZIMAG]
            if magnitude is None or phase is None:
                if had_header:
                    # Cabeçalho cartesiano reconhecido (ex.: Z'/-Z''):
                    # converter para módulo e fase em graus.
                    if z_re is not None and minus_z_im is not None:
                        z_complex = complex(z_re, -minus_z_im)
                        magnitude = abs(z_complex)
                        phase = float(np.degrees(np.angle(z_complex)))
                else:
                    # Sem cabeçalho: ordem posicional
                    # (frequência, magnitude, fase).
                    magnitude = z_re if magnitude is None else magnitude
                    phase = minus_z_im if phase is None else phase
            rows.append([freq, magnitude, phase])
        self.table.set_rows(rows)

    def _on_export(self) -> None:
        """Exporta a tabela da correção atual para CSV ou Excel."""
        try:
            correction = self._build_correction()
        except ValueError as exc:
            QMessageBox.warning(self, "Exportar correção", str(exc))
            return
        safe_name = re.sub(r"[^\w\-. ]", "_", correction.name).strip()
        default = f"correcao_{safe_name or 'instrumento'}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar tabela de correção",
            default,
            "Arquivo CSV (*.csv);;Planilha do Excel (*.xlsx)",
        )
        if not path:
            return
        try:
            exportacao.export_correction(correction, path)
        except (OSError, ValueError) as exc:
            logger.exception("Falha ao exportar correção.")
            QMessageBox.critical(
                self,
                "Exportar correção",
                f"Não foi possível exportar:\n{exc}",
            )
            return
        self.status_label.setText(f"Correção exportada: {path}")

    def _build_correction(self) -> InstrumentCorrection:
        """Valida os campos e constrói a correção.

        Raises:
            ValueError: Se os dados forem insuficientes/inválidos.
        """
        name = self.name_edit.text().strip()
        if not name:
            raise ValueError("Informe um nome para a correção.")
        r_nominal = parse_number(self.r_nominal_edit.text() or "")
        if r_nominal is None or r_nominal <= 0.0:
            raise ValueError(
                "Informe o valor nominal do resistor padrão (em ohms, "
                "maior que zero)."
            )
        return InstrumentCorrection.from_rows(
            self.table.get_rows(), r_nominal, name=name
        )

    def _store_current(self) -> Optional[InstrumentCorrection]:
        """Valida e guarda a correção atual na biblioteca de trabalho.

        Returns:
            A correção armazenada, ou ``None`` se houver erro (já
            avisado ao usuário).
        """
        try:
            correction = self._build_correction()
        except ValueError as exc:
            QMessageBox.warning(self, "Correção do Instrumento", str(exc))
            return None
        self.corrections[correction.name] = correction
        logger.info(
            "Correção '%s' salva (R nominal = %s).",
            correction.name,
            format_engineering(correction.r_nominal, "Ω"),
        )
        return correction

    def _on_save_current(self) -> None:
        """Salva a correção atual na biblioteca sem fechar a janela."""
        correction = self._store_current()
        if correction is None:
            return
        self._plot(correction)
        current = correction.name
        self._reload_combo()
        index = self.select_combo.findText(current)
        if index >= 0:
            self.select_combo.setCurrentIndex(index)
        self.status_label.setText(
            f"Correção '{current}' salva na biblioteca "
            f"({len(self.corrections)} no total)."
        )

    def _on_compute(self) -> None:
        """Calcula H(f) e atualiza a pré-visualização."""
        try:
            correction = self._build_correction()
        except ValueError as exc:
            QMessageBox.warning(self, "Correção do Instrumento", str(exc))
            return
        self._plot(correction)
        h = correction.h
        self.status_label.setText(
            f"H(f) calculada com {correction.n_points} pontos. "
            f"|H| entre {np.min(np.abs(h)):.6g} e "
            f"{np.max(np.abs(h)):.6g}; fase entre "
            f"{np.min(np.degrees(np.angle(h))):.4g}° e "
            f"{np.max(np.degrees(np.angle(h))):.4g}°."
        )

    def _plot(self, correction: InstrumentCorrection) -> None:
        """Plota |H| e fase de H na pré-visualização."""
        self.canvas.clear()
        h = correction.h
        ax_mag, ax_ph = self.canvas.figure.subplots(2, 1, sharex=True)
        ax_mag.plot(
            correction.frequency, np.abs(h), marker="o", markersize=3.5,
        )
        ax_mag.axhline(1.0, color="#888888", linewidth=0.8)
        ax_mag.set_xscale("log")
        ax_mag.set_ylabel("|H| (adim.)")
        ax_mag.set_title("Função de transferência do instrumento H(f)")
        ax_mag.grid(True, which="both")
        ax_ph.plot(
            correction.frequency,
            np.degrees(np.angle(h)),
            marker="o",
            markersize=3.5,
        )
        ax_ph.axhline(0.0, color="#888888", linewidth=0.8)
        ax_ph.set_xscale("log")
        ax_ph.set_xlabel("Frequência (Hz)")
        ax_ph.set_ylabel("Fase de H (°)")
        ax_ph.grid(True, which="both")
        self.canvas.draw()

    def _on_accept(self) -> None:
        """Salva a correção atual (se preenchida) e fecha.

        Se a janela estiver em branco mas já houver correções na
        biblioteca, fecha mantendo-as (permite apenas remover/editar).
        """
        has_data = bool(self.table.get_rows()) or bool(
            self.r_nominal_edit.text().strip()
        )
        if has_data:
            if self._store_current() is None:
                return
        elif not self.corrections:
            QMessageBox.warning(
                self,
                "Correção do Instrumento",
                "Insira os dados de ao menos uma correção.",
            )
            return
        self.accept()


# ---------------------------------------------------------------------------
# Diálogo de observações do relatório
# ---------------------------------------------------------------------------
class ReportDialog(QDialog):
    """Diálogo para digitar as observações do relatório PDF."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Relatório PDF — Observações")
        self.resize(560, 320)

        label = QLabel(
            "Digite as observações a incluir no relatório (opcional):",
            self,
        )
        self.text_edit = QPlainTextEdit(self)
        self.text_edit.setPlaceholderText(
            "Ex.: módulo fotovoltaico monocristalino de 150 W, ensaio "
            "após 5 pancadas, temperatura ambiente de 25 °C…"
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Gerar relatório"
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(self.text_edit, 1)
        layout.addWidget(buttons)

    def observations(self) -> str:
        """Texto de observações digitado pelo usuário."""
        return self.text_edit.toPlainText()


# ---------------------------------------------------------------------------
# Conexão serial (dados do sistema embarcado)
# ---------------------------------------------------------------------------
class SerialDialog(QDialog):
    """Janela "Conexão Serial".

    Recebe pontos de medição de um sistema embarcado por porta serial
    (padrão 115200 baud) e permite criar uma medição ou enviar os
    pontos à tabela de dados.  Cada linha recebida é interpretada
    conforme o formato escolhido (frequência, tensão, corrente, fase,
    etc.).
    """

    #: Emitido ao criar uma medição a partir dos pontos recebidos.
    measurementCreated = Signal(object)
    #: Emitido ao enviar as linhas recebidas para a tabela de dados.
    rowsToTable = Signal(object)

    #: Formatos de linha aceitos: (rótulo, mapeamento de colunas).
    _FORMATS: tuple[tuple[str, tuple[int, ...]], ...] = (
        ("Frequência, Tensão, Corrente, Fase",
         (COL_FREQ, COL_VOLT, COL_CURR, COL_PHASE)),
        ("Frequência, Z', -Z''",
         (COL_FREQ, COL_ZREAL, COL_MINUS_ZIMAG)),
        ("Frequência, |Z|, Fase",
         (COL_FREQ, COL_ZMOD, COL_PHASE)),
    )
    _MAX_LOG_LINES: int = 500

    #: Faixas de excitação do AD5933: (rótulo, Vpp em mV p/ firmware).
    _AD5933_RANGES: tuple[tuple[str, int], ...] = (
        ("2 Vpp (offset 1,48 V)", 2000),
        ("1 Vpp (offset 0,76 V)", 1000),
        ("0,4 Vpp (offset 0,31 V)", 400),
        ("0,2 Vpp (offset 0,17 V)", 200),
    )

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        mode: str = "generico",
    ) -> None:
        super().__init__(parent)
        #: Tipo de dispositivo: "generico" (COM comum) ou "ad5933".
        self.mode = mode
        if mode == "ad5933":
            self.setWindowTitle("Conexão Serial — AD5933 (via ESP32)")
        else:
            self.setWindowTitle("Conexão Serial — dispositivo genérico")
        self.resize(920, 700)
        self.setWindowFlag(Qt.WindowType.Window, True)

        self._acq = serial_io.SerialAcquisition(self)
        self._acq.rowReceived.connect(self._on_row_received)
        self._acq.rawLineReceived.connect(self._on_raw_line)
        self._acq.opened.connect(self._on_opened)
        self._acq.closed.connect(self._on_closed)
        self._acq.errorOccurred.connect(self._on_error)

        #: Linhas canônicas acumuladas (7 colunas).
        self._rows: list[list[Optional[float]]] = []

        # -- Conexão ------------------------------------------------------
        self.port_combo = QComboBox(self)
        self.port_combo.setMinimumWidth(220)
        self.refresh_button = QPushButton("Atualizar portas", self)
        self.refresh_button.clicked.connect(self.refresh_ports)

        self.baud_combo = QComboBox(self)
        self.baud_combo.setEditable(True)
        for baud in serial_io.COMMON_BAUD_RATES:
            self.baud_combo.addItem(str(baud), baud)
        self.baud_combo.setCurrentText(
            str(serial_io.DEFAULT_BAUD_RATE)
        )

        self.format_combo = QComboBox(self)
        self.format_combo.setToolTip(
            "Ordem das colunas no formato posicional. Linhas rotuladas "
            "(f=, V=, I=, pha=…) são reconhecidas automaticamente, "
            "independentemente deste seletor."
        )
        for label, mapping in self._FORMATS:
            self.format_combo.addItem(label, mapping)
        self.format_combo.currentIndexChanged.connect(
            self._on_format_changed
        )

        self.connect_button = QPushButton("Conectar", self)
        self.connect_button.setCheckable(True)
        self.connect_button.clicked.connect(self._toggle_connection)

        # -- Prévia e log -------------------------------------------------
        self.preview_table = QTableWidget(0, len(COLUMN_LABELS), self)
        self.preview_table.setHorizontalHeaderLabels(list(COLUMN_LABELS))
        self.preview_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.preview_table.verticalHeader().setVisible(True)
        self.preview_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        self.log_edit = QPlainTextEdit(self)
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(150)
        self.log_edit.setPlaceholderText(
            "Linhas brutas recebidas pela porta serial aparecerão aqui."
        )

        self.status_label = QLabel("Desconectado.", self)
        self.status_label.setWordWrap(True)

        self.create_button = QPushButton("Criar medição", self)
        self.create_button.clicked.connect(self._on_create_measurement)
        self.to_table_button = QPushButton(
            "Enviar para a tabela de dados", self
        )
        self.to_table_button.clicked.connect(self._on_send_to_table)
        self.clear_button = QPushButton("Limpar pontos", self)
        self.clear_button.clicked.connect(self._on_clear)

        if self.mode == "ad5933":
            hint = QLabel(
                "Configure a varredura abaixo e clique em \"Enviar "
                "configuração\" com a porta conectada; depois use "
                "\"Iniciar varredura\". O firmware do ESP32 responde no "
                "formato rotulado f= z'= z''= (uma linha por ponto).",
                self,
            )
        else:
            hint = QLabel(
                "Envie do embarcado uma linha por ponto (uma frequência "
                "por linha), terminada por \"\\n\". Dois formatos são "
                "aceitos:\n"
                "• Posicional (use o seletor abaixo): "
                "10000,10.2,0.00012,-80.2\n"
                "• Rotulado (ordem livre): f=10000 V=10,2 I=0,00012 "
                "pha=-80,2\n"
                "Separadores vírgula/;/tab/espaço e vírgula decimal são "
                "reconhecidos; um marcador inicial (#, $, >) é ignorado.",
                self,
            )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9a9a9a;")

        # -- Configuração da comunicação (modo genérico) -------------------
        self.serial_group: Optional[QGroupBox] = None
        if self.mode == "generico":
            self.serial_group = QGroupBox(
                "Configuração da comunicação", self
            )
            self.databits_combo = QComboBox(self)
            for bits, value in (
                ("8", QSerialPort.DataBits.Data8),
                ("7", QSerialPort.DataBits.Data7),
                ("6", QSerialPort.DataBits.Data6),
                ("5", QSerialPort.DataBits.Data5),
            ):
                self.databits_combo.addItem(bits, value)
            self.parity_combo = QComboBox(self)
            for label, value in (
                ("Nenhuma", QSerialPort.Parity.NoParity),
                ("Par", QSerialPort.Parity.EvenParity),
                ("Ímpar", QSerialPort.Parity.OddParity),
            ):
                self.parity_combo.addItem(label, value)
            self.stopbits_combo = QComboBox(self)
            for label, value in (
                ("1", QSerialPort.StopBits.OneStop),
                ("1,5", QSerialPort.StopBits.OneAndHalfStop),
                ("2", QSerialPort.StopBits.TwoStop),
            ):
                self.stopbits_combo.addItem(label, value)
            self.flow_combo = QComboBox(self)
            for label, value in (
                ("Nenhum", QSerialPort.FlowControl.NoFlowControl),
                ("RTS/CTS (hardware)",
                 QSerialPort.FlowControl.HardwareControl),
                ("XON/XOFF (software)",
                 QSerialPort.FlowControl.SoftwareControl),
            ):
                self.flow_combo.addItem(label, value)

            serial_grid = QGridLayout(self.serial_group)
            serial_grid.addWidget(QLabel("Bits de dados:", self), 0, 0)
            serial_grid.addWidget(self.databits_combo, 0, 1)
            serial_grid.addWidget(QLabel("Paridade:", self), 0, 2)
            serial_grid.addWidget(self.parity_combo, 0, 3)
            serial_grid.addWidget(QLabel("Bits de parada:", self), 0, 4)
            serial_grid.addWidget(self.stopbits_combo, 0, 5)
            serial_grid.addWidget(
                QLabel("Controle de fluxo:", self), 1, 0
            )
            serial_grid.addWidget(self.flow_combo, 1, 1)
            note = QLabel(
                "Padrão 8N1 sem controle de fluxo — o usado por "
                "Arduino/ESP32 e pela maioria dos conversores USB-serial.",
                self,
            )
            note.setStyleSheet("color: #9a9a9a;")
            note.setWordWrap(True)
            serial_grid.addWidget(note, 1, 2, 1, 4)

        # -- Configuração da varredura (modo AD5933) -----------------------
        self.ad5933_group: Optional[QGroupBox] = None
        if self.mode == "ad5933":
            self.ad5933_group = QGroupBox(
                "Configuração da varredura (AD5933)", self
            )
            self.ad_fstart = QDoubleSpinBox(self)
            self.ad_fstart.setRange(1.0, 200000.0)
            self.ad_fstart.setDecimals(1)
            self.ad_fstart.setValue(1000.0)
            self.ad_fstart.setSuffix(" Hz")
            self.ad_fstop = QDoubleSpinBox(self)
            self.ad_fstop.setRange(1.0, 200000.0)
            self.ad_fstop.setDecimals(1)
            self.ad_fstop.setValue(100000.0)
            self.ad_fstop.setSuffix(" Hz")
            self.ad_npts = QSpinBox(self)
            self.ad_npts.setRange(2, 512)
            self.ad_npts.setValue(100)
            self.ad_range_combo = QComboBox(self)
            for label, millivolt in self._AD5933_RANGES:
                self.ad_range_combo.addItem(label, millivolt)
            self.ad_range_combo.setCurrentIndex(1)  # 1 Vpp
            self.ad_pga_combo = QComboBox(self)
            self.ad_pga_combo.addItem("x1", 1)
            self.ad_pga_combo.addItem("x5", 5)
            self.ad_settle = QSpinBox(self)
            self.ad_settle.setRange(1, 511)
            self.ad_settle.setValue(100)
            self.ad_settle.setToolTip(
                "Ciclos de acomodação do DUT antes de cada DFT."
            )

            self.ad_config_button = QPushButton(
                "Enviar configuração", self
            )
            self.ad_config_button.clicked.connect(self._send_ad5933_config)
            self.ad_sweep_button = QPushButton(
                "Iniciar varredura", self
            )
            self.ad_sweep_button.clicked.connect(self._start_ad5933_sweep)
            self.ad_temp_button = QPushButton("Ler temperatura", self)
            self.ad_temp_button.clicked.connect(self._read_ad5933_temp)

            grid = QGridLayout(self.ad5933_group)
            grid.addWidget(QLabel("Freq. inicial:", self), 0, 0)
            grid.addWidget(self.ad_fstart, 0, 1)
            grid.addWidget(QLabel("Freq. final:", self), 0, 2)
            grid.addWidget(self.ad_fstop, 0, 3)
            grid.addWidget(QLabel("Nº de pontos:", self), 0, 4)
            grid.addWidget(self.ad_npts, 0, 5)
            grid.addWidget(QLabel("Excitação:", self), 1, 0)
            grid.addWidget(self.ad_range_combo, 1, 1)
            grid.addWidget(QLabel("Ganho PGA:", self), 1, 2)
            grid.addWidget(self.ad_pga_combo, 1, 3)
            grid.addWidget(QLabel("Acomodação:", self), 1, 4)
            grid.addWidget(self.ad_settle, 1, 5)
            grid.addWidget(self.ad_config_button, 2, 1)
            grid.addWidget(self.ad_sweep_button, 2, 3)
            grid.addWidget(self.ad_temp_button, 2, 5)

        # -- Layout -------------------------------------------------------
        conn_row = QHBoxLayout()
        conn_row.addWidget(QLabel("Porta:", self))
        conn_row.addWidget(self.port_combo, 1)
        conn_row.addWidget(self.refresh_button)
        conn_row.addWidget(QLabel("Baud:", self))
        conn_row.addWidget(self.baud_combo)
        conn_row.addWidget(self.connect_button)

        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("Formato dos dados:", self))
        format_row.addWidget(self.format_combo, 1)

        actions_row = QHBoxLayout()
        actions_row.addWidget(self.create_button)
        actions_row.addWidget(self.to_table_button)
        actions_row.addWidget(self.clear_button)
        actions_row.addStretch(1)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close, self
        )
        button_box.rejected.connect(self.close)
        close_button = button_box.button(
            QDialogButtonBox.StandardButton.Close
        )
        close_button.setText("Fechar")
        close_button.clicked.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(conn_row)
        if self.mode == "ad5933":
            # Formato fixo (rotulado f= z'= z''=); o seletor não se aplica.
            self.format_combo.setCurrentIndex(1)  # Freq, Z', -Z''
            self.format_combo.setVisible(False)
            format_row.itemAt(0).widget().setVisible(False)
            layout.addLayout(format_row)
            layout.addWidget(self.ad5933_group)
        else:
            layout.addWidget(self.serial_group)
            layout.addLayout(format_row)
        layout.addWidget(QLabel("Pontos recebidos:", self))
        layout.addWidget(self.preview_table, 1)
        layout.addWidget(QLabel("Log da porta serial:", self))
        layout.addWidget(self.log_edit)
        layout.addLayout(actions_row)
        layout.addWidget(self.status_label)
        layout.addWidget(button_box)

        self._acq.set_mapping(self.format_combo.currentData())
        self.refresh_ports()

    def _on_format_changed(self, _index: int) -> None:
        """Atualiza o mapeamento posicional do parser."""
        self._acq.set_mapping(self.format_combo.currentData())

    # -- Comandos ao AD5933 (via firmware do ESP32) ---------------------------
    def _require_connection(self) -> bool:
        """Garante que a porta esteja aberta antes de enviar comandos."""
        if not self._acq.is_open:
            QMessageBox.information(
                self,
                "Conexão Serial",
                "Conecte-se à porta serial antes de enviar comandos "
                "ao AD5933.",
            )
            return False
        return True

    def _send_ad5933_config(self) -> None:
        """Envia a configuração de varredura ao firmware (comando C)."""
        if not self._require_connection():
            return
        f0 = float(self.ad_fstart.value())
        f1 = float(self.ad_fstop.value())
        if f1 <= f0:
            QMessageBox.warning(
                self,
                "Configuração AD5933",
                "A frequência final deve ser maior que a inicial.",
            )
            return
        n = int(self.ad_npts.value())
        df = (f1 - f0) / (n - 1)
        command = (
            f"C f0={f0:.3f} df={df:.6f} n={n} "
            f"vpp={self.ad_range_combo.currentData()} "
            f"pga={self.ad_pga_combo.currentData()} "
            f"st={self.ad_settle.value()}"
        )
        self._acq.send_text(command)
        self.status_label.setText(
            f"Configuração enviada: {f0:.1f}–{f1:.1f} Hz, {n} pontos, "
            f"{self.ad_range_combo.currentText()}, "
            f"PGA {self.ad_pga_combo.currentText()}."
        )

    def _start_ad5933_sweep(self) -> None:
        """Dispara a varredura no firmware (comando S)."""
        if not self._require_connection():
            return
        self._acq.send_text("S")
        self.status_label.setText(
            "Varredura iniciada — aguardando pontos do AD5933…"
        )

    def _read_ad5933_temp(self) -> None:
        """Solicita a temperatura interna do AD5933 (comando T)."""
        if not self._require_connection():
            return
        self._acq.send_text("T")
        self.status_label.setText(
            "Temperatura solicitada — veja o log da porta serial."
        )

    # -- Conexão ------------------------------------------------------------
    def refresh_ports(self) -> None:
        """Atualiza a lista de portas seriais disponíveis."""
        current = self.port_combo.currentData()
        self.port_combo.clear()
        ports = serial_io.list_serial_ports()
        if not ports:
            self.port_combo.addItem("(nenhuma porta encontrada)", None)
            self.connect_button.setEnabled(False)
        else:
            self.connect_button.setEnabled(True)
            for name, description in ports:
                label = f"{name} — {description}" if description else name
                self.port_combo.addItem(label, name)
            index = self.port_combo.findData(current)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)

    def _selected_baud(self) -> int:
        """Baud escolhido (aceita valor digitado)."""
        value = parse_number(self.baud_combo.currentText())
        if value is None or value <= 0:
            return serial_io.DEFAULT_BAUD_RATE
        return int(value)

    def _toggle_connection(self, checked: bool) -> None:
        """Conecta ou desconecta conforme o estado do botão."""
        if checked:
            port = self.port_combo.currentData()
            if not port:
                self.connect_button.setChecked(False)
                QMessageBox.information(
                    self,
                    "Conexão Serial",
                    "Nenhuma porta serial disponível. Conecte o "
                    "dispositivo e clique em \"Atualizar portas\".",
                )
                return
            try:
                if self.serial_group is not None:
                    self._acq.open(
                        port,
                        self._selected_baud(),
                        data_bits=self.databits_combo.currentData(),
                        parity=self.parity_combo.currentData(),
                        stop_bits=self.stopbits_combo.currentData(),
                        flow_control=self.flow_combo.currentData(),
                    )
                else:
                    self._acq.open(port, self._selected_baud())
            except RuntimeError as exc:
                self.connect_button.setChecked(False)
                QMessageBox.critical(
                    self, "Conexão Serial", str(exc)
                )
        else:
            self._acq.close()

    def _on_opened(self) -> None:
        self.connect_button.setChecked(True)
        self.connect_button.setText("Desconectar")
        self.port_combo.setEnabled(False)
        self.baud_combo.setEnabled(False)
        self.refresh_button.setEnabled(False)
        if self.serial_group is not None:
            self.serial_group.setEnabled(False)
        self.status_label.setText(
            f"Conectado a {self._acq.port_name} "
            f"({self._selected_baud()} baud). Aguardando dados…"
        )

    def _on_closed(self) -> None:
        self.connect_button.setChecked(False)
        self.connect_button.setText("Conectar")
        self.port_combo.setEnabled(True)
        self.baud_combo.setEnabled(True)
        self.refresh_button.setEnabled(True)
        if self.serial_group is not None:
            self.serial_group.setEnabled(True)
        self.status_label.setText(
            f"Desconectado. {len(self._rows)} ponto(s) recebido(s)."
        )

    def _on_error(self, message: str) -> None:
        self.status_label.setText(f"Erro na porta serial: {message}")

    # -- Recepção -----------------------------------------------------------
    def _on_raw_line(self, line: str) -> None:
        """Adiciona uma linha bruta ao log (com limite de tamanho)."""
        self.log_edit.appendPlainText(line)
        document = self.log_edit.document()
        if document.blockCount() > self._MAX_LOG_LINES:
            cursor = self.log_edit.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.select(cursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

    def _on_row_received(
        self, canonical: list[Optional[float]]
    ) -> None:
        """Registra uma linha canônica recebida (já mapeada)."""
        self._rows.append(list(canonical))
        self._append_preview_row(canonical)
        self.status_label.setText(
            f"Conectado a {self._acq.port_name}. "
            f"{len(self._rows)} ponto(s) recebido(s)."
        )

    def _append_preview_row(
        self, canonical: list[Optional[float]]
    ) -> None:
        """Acrescenta uma linha à tabela de prévia."""
        row = self.preview_table.rowCount()
        self.preview_table.insertRow(row)
        for column, value in enumerate(canonical):
            text = "" if value is None else _CELL_FORMAT.format(value)
            self.preview_table.setItem(
                row, column, QTableWidgetItem(text)
            )
        self.preview_table.scrollToBottom()

    # -- Ações --------------------------------------------------------------
    def _on_clear(self) -> None:
        """Descarta os pontos recebidos e o log."""
        self._rows.clear()
        self.preview_table.setRowCount(0)
        self.log_edit.clear()
        self.status_label.setText("Pontos limpos.")

    def _on_send_to_table(self) -> None:
        """Envia os pontos recebidos para a tabela de dados."""
        if not self._rows:
            QMessageBox.information(
                self,
                "Conexão Serial",
                "Nenhum ponto recebido ainda.",
            )
            return
        self.rowsToTable.emit([row[:] for row in self._rows])
        self.status_label.setText(
            f"{len(self._rows)} ponto(s) enviado(s) para a tabela de "
            "dados."
        )

    def _on_create_measurement(self) -> None:
        """Cria uma medição a partir dos pontos recebidos."""
        if not self._rows:
            QMessageBox.information(
                self,
                "Conexão Serial",
                "Nenhum ponto recebido ainda.",
            )
            return
        name, ok = QInputDialog.getText(
            self,
            "Nova medição",
            "Nome da medição (ex.: FRA0F):",
        )
        if not ok or not name.strip():
            return
        try:
            measurement = Measurement.from_components(
                name=name.strip(),
                frequency=[r[COL_FREQ] for r in self._rows],
                z_real=[r[COL_ZREAL] for r in self._rows],
                minus_z_imag=[r[COL_MINUS_ZIMAG] for r in self._rows],
                magnitude=[r[COL_ZMOD] for r in self._rows],
                phase_deg=[r[COL_PHASE] for r in self._rows],
                voltage=[r[COL_VOLT] for r in self._rows],
                current=[r[COL_CURR] for r in self._rows],
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Nova medição", str(exc))
            return
        self.measurementCreated.emit(measurement)
        self.status_label.setText(
            f"Medição '{measurement.name}' criada "
            f"({measurement.n_points} pontos)."
        )

    def closeEvent(self, event) -> None:  # noqa: N802 (API Qt)
        """Fecha a porta serial ao fechar a janela."""
        self._acq.close()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Editor de circuito equivalente (estilo NOVA 2 / ZView)
# ---------------------------------------------------------------------------
def circuit_value_lines(
    spec: "circuitos.CircuitSpec",
    values: Sequence[float],
) -> dict[str, list[str]]:
    """Monta as linhas de valores exibidas sob cada elemento.

    Args:
        spec: Especificação do circuito.
        values: Valores dos parâmetros (estimativas ou ajustados).

    Returns:
        Dicionário ``{rótulo do elemento: ["Q = 1e-06 S·sⁿ", ...]}``.
    """
    lines: dict[str, list[str]] = {
        label: [] for label in spec.element_labels
    }
    cursors: dict[int, int] = {}
    for unit, value, elem_index in zip(
        spec.param_units, values, spec.param_element
    ):
        label = spec.element_labels[elem_index]
        info = circuitos.ELEMENTS[spec.element_codes[elem_index]]
        k = cursors.get(elem_index, 0)
        cursors[elem_index] = k + 1
        param_label = info.param_labels[k]
        lines[label].append(f"{param_label} = {value:.4g} {unit}".rstrip())
    return lines


class CircuitDiagramWidget(QWidget):
    """Desenho esquemático de um circuito equivalente.

    Renderiza a árvore série/paralelo com símbolos clássicos (resistor
    em zigue-zague, capacitor de placas, indutor em arcos e caixas
    rotuladas para os demais elementos), com os rótulos e valores sob
    cada elemento — no estilo do Metrohm NOVA/ZView.
    """

    _SYM_W = 54
    _SYM_H = 28
    _ELEM_W = 100
    _WIRE = 14
    _BUS = 16
    _BRANCH_GAP = 12
    _LINE_H = 13
    _MARGIN = 16
    _TERMINAL = 14

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tree: Optional[circuitos.CircuitNode] = None
        self._elem_lines: list[list[str]] = []
        self._size_cache: dict[int, tuple[int, int, int]] = {}
        self._total: tuple[int, int, int] = (0, 0, 0)
        self._paint_cursor = 0
        self.setMinimumHeight(130)

    # -- API ------------------------------------------------------------
    def set_circuit(
        self,
        tree: Optional["circuitos.CircuitNode"],
        value_lines: Optional[dict[str, list[str]]] = None,
    ) -> None:
        """Define o circuito a desenhar (ou ``None`` para limpar).

        Args:
            tree: Árvore do circuito.
            value_lines: Linhas extras sob cada elemento, por rótulo.
        """
        self._tree = tree
        self._elem_lines = []
        self._size_cache = {}
        if tree is not None:
            labels = self._assign_labels(tree)
            extras = value_lines or {}
            self._elem_lines = [
                [label] + list(extras.get(label, []))
                for label in labels
            ]
            self._measure_cursor = 0
            self._total = self._compute_sizes(tree)
        else:
            self._total = (0, 0, 0)
        self.updateGeometry()
        self.update()

    @staticmethod
    def _assign_labels(tree: "circuitos.CircuitNode") -> list[str]:
        """Rótulos dos elementos na ordem de percurso (R1, C1, ...)."""
        counters: dict[str, int] = {}
        labels: list[str] = []

        def walk(node: "circuitos.CircuitNode") -> None:
            if node.kind == "element":
                code = node.element_code or "?"
                counters[code] = counters.get(code, 0) + 1
                labels.append(f"{code}{counters[code]}")
            else:
                for child in node.children:
                    walk(child)

        walk(tree)
        return labels

    # -- Layout ----------------------------------------------------------
    def _compute_sizes(
        self, node: "circuitos.CircuitNode"
    ) -> tuple[int, int, int]:
        """Calcula (largura, altura, y do eixo central) do nó."""
        if node.kind == "element":
            index = self._measure_cursor
            self._measure_cursor += 1
            n_lines = (
                len(self._elem_lines[index])
                if index < len(self._elem_lines)
                else 1
            )
            height = self._SYM_H + n_lines * self._LINE_H + 6
            size = (self._ELEM_W, height, self._SYM_H // 2)
        elif node.kind == "series":
            sizes = [self._compute_sizes(c) for c in node.children]
            width = sum(s[0] for s in sizes) + self._WIRE * max(
                len(sizes) - 1, 0
            )
            above = max((s[2] for s in sizes), default=20)
            below = max((s[1] - s[2] for s in sizes), default=20)
            size = (width, above + below, above)
        else:  # parallel
            sizes = [self._compute_sizes(c) for c in node.children]
            width = max((s[0] for s in sizes), default=40) + 2 * self._BUS
            height = sum(s[1] for s in sizes) + self._BRANCH_GAP * max(
                len(sizes) - 1, 0
            )
            first_center = sizes[0][2] if sizes else 0
            last_center = (
                height - (sizes[-1][1] - sizes[-1][2]) if sizes else 0
            )
            size = (width, height, (first_center + last_center) // 2)
        self._size_cache[id(node)] = size
        return size

    def sizeHint(self) -> QSize:  # noqa: N802 (API Qt)
        """Tamanho preferido conforme o circuito atual."""
        if self._tree is None:
            return QSize(320, 130)
        w, h, _ = self._total
        return QSize(
            w + 2 * (self._MARGIN + self._TERMINAL),
            max(h + 2 * self._MARGIN, 130),
        )

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (API Qt)
        """Tamanho mínimo (igual ao preferido)."""
        return self.sizeHint()

    # -- Desenho ----------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802 (API Qt)
        """Desenha o circuito."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text_color = self.palette().color(QPalette.ColorRole.Text)
        if self._tree is None:
            painter.setPen(QColor("#8a8a8a"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Monte o circuito adicionando elementos e grupos.",
            )
            return
        pen = QPen(text_color, 1.6)
        painter.setPen(pen)
        font = painter.font()
        font.setPointSizeF(8.5)
        painter.setFont(font)

        w, h, cy = self._total
        extra_w = max(
            self.width() - (w + 2 * (self._MARGIN + self._TERMINAL)), 0
        )
        extra_h = max(self.height() - (h + 2 * self._MARGIN), 0)
        x = self._MARGIN + extra_w // 2
        y = self._MARGIN + extra_h // 2 + cy

        painter.setBrush(text_color)
        painter.drawEllipse(QPointF(x, y), 3.0, 3.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(x, y), QPointF(x + self._TERMINAL, y))
        self._paint_cursor = 0
        self._draw_node(painter, self._tree, x + self._TERMINAL, y, w)
        end_x = x + self._TERMINAL + w
        painter.drawLine(
            QPointF(end_x, y), QPointF(end_x + self._TERMINAL, y)
        )
        painter.setBrush(text_color)
        painter.drawEllipse(
            QPointF(end_x + self._TERMINAL, y), 3.0, 3.0
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_node(
        self,
        painter: QPainter,
        node: "circuitos.CircuitNode",
        x: float,
        y_center: float,
        width: float,
    ) -> None:
        """Desenha um nó (elemento ou grupo) na largura indicada."""
        if node.kind == "element":
            self._draw_element(painter, node, x, y_center, width)
            return
        if node.kind == "series":
            children = node.children
            sizes = [self._size_cache[id(c)] for c in children]
            natural = sum(s[0] for s in sizes) + self._WIRE * max(
                len(children) - 1, 0
            )
            extra = max(width - natural, 0)
            share = extra // max(len(children), 1)
            remainder = extra - share * len(children)
            cursor = x
            for i, child in enumerate(children):
                child_w = sizes[i][0] + share
                if i == len(children) - 1:
                    child_w += remainder
                self._draw_node(painter, child, cursor, y_center, child_w)
                cursor += child_w
                if i < len(children) - 1:
                    painter.drawLine(
                        QPointF(cursor, y_center),
                        QPointF(cursor + self._WIRE, y_center),
                    )
                    cursor += self._WIRE
            return
        # parallel
        children = node.children
        sizes = [self._size_cache[id(c)] for c in children]
        _, node_h, node_cy = self._size_cache[id(node)]
        top = y_center - node_cy
        centers: list[float] = []
        acc = top
        inner_w = width - 2 * self._BUS
        for child, (cw, ch, ccy) in zip(children, sizes):
            branch_center = acc + ccy
            centers.append(branch_center)
            painter.drawLine(
                QPointF(x, branch_center),
                QPointF(x + self._BUS, branch_center),
            )
            self._draw_node(
                painter, child, x + self._BUS, branch_center, inner_w
            )
            painter.drawLine(
                QPointF(x + width - self._BUS, branch_center),
                QPointF(x + width, branch_center),
            )
            acc += ch + self._BRANCH_GAP
        painter.drawLine(
            QPointF(x, centers[0]), QPointF(x, centers[-1])
        )
        painter.drawLine(
            QPointF(x + width, centers[0]),
            QPointF(x + width, centers[-1]),
        )
        painter.setBrush(painter.pen().color())
        for center in centers:
            painter.drawEllipse(QPointF(x, center), 2.4, 2.4)
            painter.drawEllipse(QPointF(x + width, center), 2.4, 2.4)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_element(
        self,
        painter: QPainter,
        node: "circuitos.CircuitNode",
        x: float,
        y: float,
        width: float,
    ) -> None:
        """Desenha um elemento com fios, símbolo e rótulos."""
        lines = (
            self._elem_lines[self._paint_cursor]
            if self._paint_cursor < len(self._elem_lines)
            else ["?"]
        )
        self._paint_cursor += 1
        lead = (width - self._SYM_W) / 2.0
        sx = x + lead
        painter.drawLine(QPointF(x, y), QPointF(sx, y))
        self._draw_symbol(painter, node.element_code or "?", sx, y)
        painter.drawLine(
            QPointF(sx + self._SYM_W, y), QPointF(x + width, y)
        )
        center_x = x + width / 2.0
        base_y = y + self._SYM_H / 2.0 + 11
        text_color = self.palette().color(QPalette.ColorRole.Text)
        for i, line in enumerate(lines):
            painter.setPen(
                QPen(text_color if i == 0 else QColor("#4fc3f7"))
            )
            rect_w = 180.0
            painter.drawText(
                QRectF(
                    center_x - rect_w / 2.0,
                    base_y + i * self._LINE_H - 10,
                    rect_w,
                    14.0,
                ),
                Qt.AlignmentFlag.AlignHCenter,
                line,
            )
        painter.setPen(QPen(text_color, 1.6))

    def _draw_symbol(
        self, painter: QPainter, code: str, sx: float, y: float
    ) -> None:
        """Desenha o símbolo do elemento entre ``sx`` e ``sx+_SYM_W``."""
        w = float(self._SYM_W)
        if code == "R":
            points = [QPointF(sx, y), QPointF(sx + 6, y)]
            segments = 6
            amplitude = 8.0
            seg_w = (w - 12.0) / segments
            for i in range(segments):
                px = sx + 6 + seg_w * (i + 0.5)
                py = y + (amplitude if i % 2 else -amplitude)
                points.append(QPointF(px, py))
            points.append(QPointF(sx + w - 6, y))
            points.append(QPointF(sx + w, y))
            painter.drawPolyline(points)
        elif code == "C":
            cx = sx + w / 2.0
            painter.drawLine(QPointF(sx, y), QPointF(cx - 5, y))
            painter.drawLine(QPointF(cx + 5, y), QPointF(sx + w, y))
            painter.drawLine(
                QPointF(cx - 5, y - 11), QPointF(cx - 5, y + 11)
            )
            painter.drawLine(
                QPointF(cx + 5, y - 11), QPointF(cx + 5, y + 11)
            )
        elif code == "L":
            painter.drawLine(QPointF(sx, y), QPointF(sx + 8, y))
            painter.drawLine(QPointF(sx + w - 8, y), QPointF(sx + w, y))
            coil_w = (w - 16.0) / 3.0
            for i in range(3):
                rect = QRectF(
                    sx + 8 + i * coil_w, y - coil_w / 2.0, coil_w, coil_w
                )
                painter.drawArc(rect, 0, 180 * 16)
        else:
            box = QRectF(
                sx + 1,
                y - self._SYM_H / 2.0 + 2,
                w - 2,
                self._SYM_H - 4.0,
            )
            painter.drawRoundedRect(box, 3.0, 3.0)
            painter.drawText(
                box, Qt.AlignmentFlag.AlignCenter, code
            )


class CircuitBuilderDialog(QDialog):
    """Editor de circuito equivalente (estilo NOVA 2).

    Permite montar livremente o circuito com os elementos do
    ``impedance.py`` (R, C, L, CPE, W, Wo/"O", Ws/"T", Gerischer,
    Zarc, TLMQ, ...), organizados em grupos em série e em paralelo.
    Exibe o desenho esquemático, a string do circuito e a tabela de
    estimativas iniciais editáveis.
    """

    _ROLE_KIND = Qt.ItemDataRole.UserRole
    _ROLE_CODE = Qt.ItemDataRole.UserRole + 1

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        measurement: Optional[Measurement] = None,
        spec: Optional["circuitos.CircuitSpec"] = None,
        guesses: Optional[Sequence[float]] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Editor de circuito equivalente")
        self.resize(1040, 620)
        self._measurement = measurement
        self.spec: Optional[circuitos.CircuitSpec] = None
        self._guess_cache: dict[str, float] = {}
        self._updating_table = False

        # -- Estrutura (árvore) -----------------------------------------
        self.tree_widget = QTreeWidget(self)
        self.tree_widget.setHeaderLabel("Estrutura do circuito")
        self._root_item = QTreeWidgetItem(["Série (raiz)"])
        self._root_item.setData(0, self._ROLE_KIND, "series")
        self.tree_widget.addTopLevelItem(self._root_item)
        self.tree_widget.expandAll()

        self.element_combo = QComboBox(self)
        for code, info in circuitos.ELEMENTS.items():
            self.element_combo.addItem(
                f"{code} — {info.display_name}", code
            )

        add_element_button = QPushButton("Adicionar elemento", self)
        add_element_button.clicked.connect(self._add_element)
        add_parallel_button = QPushButton("Grupo paralelo", self)
        add_parallel_button.clicked.connect(
            lambda: self._add_group("parallel")
        )
        add_series_button = QPushButton("Grupo série", self)
        add_series_button.clicked.connect(
            lambda: self._add_group("series")
        )
        remove_button = QPushButton("Remover", self)
        remove_button.clicked.connect(self._remove_selected)
        up_button = QPushButton("▲ Subir", self)
        up_button.clicked.connect(lambda: self._move_selected(-1))
        down_button = QPushButton("▼ Descer", self)
        down_button.clicked.connect(lambda: self._move_selected(1))

        self.template_combo = QComboBox(self)
        for key, model in circuitos.MODELS.items():
            self.template_combo.addItem(model.display_name, key)
        load_template_button = QPushButton("Carregar modelo", self)
        load_template_button.clicked.connect(self._load_template)

        # -- Diagrama + parâmetros ----------------------------------------
        self.diagram = CircuitDiagramWidget(self)
        diagram_scroll = QScrollArea(self)
        diagram_scroll.setWidget(self.diagram)
        diagram_scroll.setWidgetResizable(True)
        diagram_scroll.setMinimumHeight(210)

        self.string_label = QLabel("—", self)
        self.string_label.setStyleSheet(
            "font-family: Consolas, monospace; color: #4fc3f7;"
        )

        self.guess_table = QTableWidget(0, 3, self)
        self.guess_table.setHorizontalHeaderLabels(
            ["Parâmetro", "Unidade", "Valor inicial"]
        )
        self.guess_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.guess_table.verticalHeader().setVisible(False)
        self.guess_table.cellChanged.connect(self._on_guess_edited)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #e0a030;")

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Usar circuito"
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)

        # -- Layout ----------------------------------------------------------
        template_row = QHBoxLayout()
        template_row.addWidget(QLabel("Modelo pronto:", self))
        template_row.addWidget(self.template_combo, 1)
        template_row.addWidget(load_template_button)

        palette_row = QHBoxLayout()
        palette_row.addWidget(self.element_combo, 1)
        palette_row.addWidget(add_element_button)

        group_row = QHBoxLayout()
        group_row.addWidget(add_parallel_button)
        group_row.addWidget(add_series_button)
        group_row.addWidget(remove_button)

        move_row = QHBoxLayout()
        move_row.addWidget(up_button)
        move_row.addWidget(down_button)
        move_row.addStretch(1)

        left = QVBoxLayout()
        left.addLayout(template_row)
        left.addWidget(self.tree_widget, 1)
        left.addLayout(palette_row)
        left.addLayout(group_row)
        left.addLayout(move_row)
        left_widget = QWidget(self)
        left_widget.setLayout(left)
        left_widget.setMaximumWidth(420)

        right = QVBoxLayout()
        right.addWidget(diagram_scroll, 2)
        string_row = QHBoxLayout()
        string_row.addWidget(QLabel("Circuito:", self))
        string_row.addWidget(self.string_label, 1)
        right.addLayout(string_row)
        right.addWidget(self.guess_table, 1)
        right_widget = QWidget(self)
        right_widget.setLayout(right)

        content = QHBoxLayout()
        content.addWidget(left_widget)
        content.addWidget(right_widget, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(content, 1)
        layout.addWidget(self.status_label)
        layout.addWidget(button_box)

        # -- Estado inicial ------------------------------------------------
        if spec is not None:
            self._populate_from_tree(self._root_item, spec.tree)
            if guesses is not None:
                self._guess_cache = {
                    name: float(value)
                    for name, value in zip(spec.param_names, guesses)
                }
        else:
            self._populate_from_tree(
                self._root_item, circuitos.preset_tree("randles")
            )
        self.tree_widget.expandAll()
        self._rebuild()

    # -- Construção/leitura da árvore -------------------------------------
    def _make_element_item(self, code: str) -> QTreeWidgetItem:
        info = circuitos.ELEMENTS[code]
        item = QTreeWidgetItem([f"{code} — {info.display_name}"])
        item.setData(0, self._ROLE_KIND, "element")
        item.setData(0, self._ROLE_CODE, code)
        return item

    def _make_group_item(self, kind: str) -> QTreeWidgetItem:
        label = "Paralelo" if kind == "parallel" else "Série"
        item = QTreeWidgetItem([label])
        item.setData(0, self._ROLE_KIND, kind)
        return item

    def _populate_from_tree(
        self, item: QTreeWidgetItem, node: "circuitos.CircuitNode"
    ) -> None:
        """Preenche um item de grupo com os filhos de um nó."""
        item.takeChildren()
        for child in node.children:
            if child.kind == "element":
                item.addChild(
                    self._make_element_item(child.element_code or "R")
                )
            else:
                group_item = self._make_group_item(child.kind)
                item.addChild(group_item)
                self._populate_from_tree(group_item, child)

    def _tree_from_item(
        self, item: QTreeWidgetItem
    ) -> "circuitos.CircuitNode":
        """Reconstrói a árvore de circuito a partir dos itens."""
        kind = item.data(0, self._ROLE_KIND)
        if kind == "element":
            return circuitos.CircuitNode(
                kind="element",
                element_code=item.data(0, self._ROLE_CODE),
            )
        children = [
            self._tree_from_item(item.child(i))
            for i in range(item.childCount())
        ]
        return circuitos.CircuitNode(kind=kind, children=children)

    def _selected_group_item(self) -> QTreeWidgetItem:
        """Grupo-alvo das inserções (grupo do item selecionado)."""
        items = self.tree_widget.selectedItems()
        if not items:
            return self._root_item
        item = items[0]
        if item.data(0, self._ROLE_KIND) == "element":
            parent = item.parent()
            return parent if parent is not None else self._root_item
        return item

    def _walk_element_items(
        self, item: QTreeWidgetItem
    ) -> list[QTreeWidgetItem]:
        """Itens de elemento na mesma ordem de percurso da árvore."""
        result: list[QTreeWidgetItem] = []
        if item.data(0, self._ROLE_KIND) == "element":
            result.append(item)
        for i in range(item.childCount()):
            result.extend(self._walk_element_items(item.child(i)))
        return result

    # -- Ações de edição ---------------------------------------------------
    def _add_element(self) -> None:
        code = self.element_combo.currentData()
        group = self._selected_group_item()
        group.addChild(self._make_element_item(code))
        group.setExpanded(True)
        self._rebuild()

    def _add_group(self, kind: str) -> None:
        group = self._selected_group_item()
        item = self._make_group_item(kind)
        group.addChild(item)
        group.setExpanded(True)
        self.tree_widget.setCurrentItem(item)
        self._rebuild()

    def _remove_selected(self) -> None:
        items = self.tree_widget.selectedItems()
        if not items or items[0] is self._root_item:
            return
        item = items[0]
        parent = item.parent()
        if parent is not None:
            parent.removeChild(item)
        self._rebuild()

    def _move_selected(self, delta: int) -> None:
        items = self.tree_widget.selectedItems()
        if not items or items[0] is self._root_item:
            return
        item = items[0]
        parent = item.parent()
        if parent is None:
            return
        row = parent.indexOfChild(item)
        new_row = row + delta
        if new_row < 0 or new_row >= parent.childCount():
            return
        parent.takeChild(row)
        parent.insertChild(new_row, item)
        self.tree_widget.setCurrentItem(item)
        self._rebuild()

    def _load_template(self) -> None:
        key = self.template_combo.currentData()
        self._populate_from_tree(
            self._root_item, circuitos.preset_tree(key)
        )
        self.tree_widget.expandAll()
        self._rebuild()

    # -- Sincronização -------------------------------------------------------
    def _rebuild(self) -> None:
        """Revalida a árvore e atualiza string, diagrama e tabela."""
        tree = self._tree_from_item(self._root_item)
        try:
            spec = circuitos.build_circuit_spec(tree)
        except ValueError as exc:
            self.spec = None
            self.string_label.setText("—")
            self.status_label.setText(f"Circuito incompleto: {exc}")
            self.diagram.set_circuit(None)
            self._updating_table = True
            try:
                self.guess_table.setRowCount(0)
            finally:
                self._updating_table = False
            return

        self.spec = spec
        self.status_label.setText("")
        self.string_label.setText(spec.circuit_string)

        element_items = self._walk_element_items(self._root_item)
        for item, label, code in zip(
            element_items, spec.element_labels, spec.element_codes
        ):
            info = circuitos.ELEMENTS[code]
            item.setText(0, f"{label} — {info.display_name}")

        defaults = circuitos.default_guesses(spec, self._measurement)
        values = [
            self._guess_cache.get(name, default)
            for name, default in zip(spec.param_names, defaults)
        ]

        self._updating_table = True
        try:
            self.guess_table.setRowCount(len(values))
            for row, (name, unit, value) in enumerate(
                zip(spec.param_names, spec.param_units, values)
            ):
                name_item = QTableWidgetItem(name)
                name_item.setFlags(
                    name_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )
                unit_item = QTableWidgetItem(unit)
                unit_item.setFlags(
                    unit_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )
                self.guess_table.setItem(row, 0, name_item)
                self.guess_table.setItem(row, 1, unit_item)
                self.guess_table.setItem(
                    row, 2, QTableWidgetItem(f"{value:.6g}")
                )
        finally:
            self._updating_table = False

        self.diagram.set_circuit(
            spec.tree, circuit_value_lines(spec, values)
        )

    def _on_guess_edited(self, row: int, column: int) -> None:
        if self._updating_table or column != 2 or self.spec is None:
            return
        item = self.guess_table.item(row, column)
        name_item = self.guess_table.item(row, 0)
        if item is None or name_item is None:
            return
        value = parse_number(item.text())
        if value is not None:
            self._guess_cache[name_item.text()] = value
            defaults = circuitos.default_guesses(
                self.spec, self._measurement
            )
            values = [
                self._guess_cache.get(name, default)
                for name, default in zip(
                    self.spec.param_names, defaults
                )
            ]
            self.diagram.set_circuit(
                self.spec.tree,
                circuit_value_lines(self.spec, values),
            )

    def guesses(self) -> list[float]:
        """Estimativas iniciais atuais, na ordem dos parâmetros.

        Raises:
            ValueError: Se alguma célula da tabela não for numérica.
        """
        if self.spec is None:
            raise ValueError("O circuito não é válido.")
        values: list[float] = []
        invalid: list[str] = []
        for row in range(self.guess_table.rowCount()):
            item = self.guess_table.item(row, 2)
            name_item = self.guess_table.item(row, 0)
            value = parse_number(item.text()) if item is not None else None
            if value is None:
                invalid.append(
                    name_item.text() if name_item is not None else f"linha {row + 1}"
                )
            else:
                values.append(value)
        if invalid:
            raise ValueError(
                "Estimativas iniciais inválidas para: "
                + ", ".join(invalid)
            )
        return values

    def _on_accept(self) -> None:
        if self.spec is None:
            QMessageBox.warning(
                self,
                "Editor de circuito",
                "O circuito ainda não é válido — verifique a mensagem "
                "de status.",
            )
            return
        try:
            self.guesses()
        except ValueError as exc:
            QMessageBox.warning(self, "Editor de circuito", str(exc))
            return
        logger.info(
            "Circuito personalizado definido: %s",
            self.spec.circuit_string,
        )
        self.accept()


# ---------------------------------------------------------------------------
# Abas de análise
# ---------------------------------------------------------------------------
class KKTab(QWidget):
    """Aba de validação de Kramers-Kronig."""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self._window = window

        self.measurement_combo = QComboBox(self)
        self.run_button = QPushButton("Validar Kramers-Kronig", self)
        self.run_button.clicked.connect(self.run_validation)

        self.metrics_table = QTableWidget(0, 2, self)
        self.metrics_table.setHorizontalHeaderLabels(
            ["Métrica", "Valor"]
        )
        self.metrics_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.metrics_table.verticalHeader().setVisible(False)
        self.metrics_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.metrics_table.setMaximumWidth(380)

        self.canvas = PlotCanvas(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Medição:", self))
        top.addWidget(self.measurement_combo, 1)
        top.addWidget(self.run_button)

        content = QHBoxLayout()
        content.addWidget(self.canvas, 1)
        content.addWidget(self.metrics_table)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(content, 1)

    def run_validation(self) -> None:
        """Executa a validação KK da medição escolhida."""
        name = self.measurement_combo.currentText()
        measurement = self._window.measurements.get(name)
        if measurement is None:
            QMessageBox.information(
                self,
                "Kramers-Kronig",
                "Adicione e selecione uma medição primeiro.",
            )
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = kk_module.kk_transform(measurement)
        except ValueError as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Kramers-Kronig", str(exc))
            return
        except Exception as exc:  # pragma: no cover - proteção geral
            QApplication.restoreOverrideCursor()
            logger.exception("Erro inesperado na validação KK.")
            QMessageBox.critical(
                self,
                "Kramers-Kronig",
                f"Erro inesperado na validação:\n{exc}",
            )
            return
        QApplication.restoreOverrideCursor()

        self._window.kk_results[name] = result
        self.canvas.clear()
        plot_kk(self.canvas.figure, result, self._window.plot_style())
        self.canvas.draw()

        self.metrics_table.setRowCount(0)
        for key, label in kk_module.METRIC_LABELS.items():
            row = self.metrics_table.rowCount()
            self.metrics_table.insertRow(row)
            self.metrics_table.setItem(row, 0, QTableWidgetItem(label))
            self.metrics_table.setItem(
                row,
                1,
                QTableWidgetItem(f"{result.metrics[key]:.5g}"),
            )
        row = self.metrics_table.rowCount()
        self.metrics_table.insertRow(row)
        self.metrics_table.setItem(row, 0, QTableWidgetItem("R∞ ajustado"))
        self.metrics_table.setItem(
            row, 1, QTableWidgetItem(f"{result.r_inf:.5g} Ω")
        )
        self._window.show_status(
            f"Validação KK de '{name}' concluída "
            f"(erro percentual médio: "
            f"{result.metrics['pct_error_mean']:.3g} %)."
        )


class CircuitTab(QWidget):
    """Aba de ajuste de circuito equivalente.

    Oferece os modelos de Randles pré-definidos e o editor de
    circuito livre (estilo NOVA 2), com o desenho esquemático do
    circuito e os valores ajustados sob cada elemento.
    """

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self._window = window
        self._custom_spec: Optional[circuitos.CircuitSpec] = None
        self._custom_guesses: Optional[list[float]] = None

        self.measurement_combo = QComboBox(self)
        self.model_combo = QComboBox(self)
        for key, model in circuitos.MODELS.items():
            self.model_combo.addItem(model.display_name, key)
        self.model_combo.currentIndexChanged.connect(
            lambda _index: self._update_diagram_preview()
        )

        self.editor_button = QPushButton("Editor de circuito…", self)
        self.editor_button.setToolTip(
            "Monta um circuito livre com R, C, L, CPE, Warburg (W, O, "
            "T), Gerischer e outros elementos, em série e em paralelo."
        )
        self.editor_button.clicked.connect(self.open_editor)

        self.fit_button = QPushButton("Ajustar circuito", self)
        self.fit_button.clicked.connect(self.run_fit)

        self.params_table = QTableWidget(0, 3, self)
        self.params_table.setHorizontalHeaderLabels(
            ["Parâmetro", "Valor", "Incerteza (1σ)"]
        )
        self.params_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.params_table.verticalHeader().setVisible(False)
        self.params_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.params_table.setMaximumWidth(420)

        self.stats_label = QLabel("—", self)
        self.stats_label.setWordWrap(True)

        self.canvas = PlotCanvas(self)

        self.diagram = CircuitDiagramWidget(self)
        diagram_scroll = QScrollArea(self)
        diagram_scroll.setWidget(self.diagram)
        diagram_scroll.setWidgetResizable(True)
        diagram_scroll.setMinimumHeight(170)
        diagram_scroll.setMaximumHeight(230)

        top = QHBoxLayout()
        top.addWidget(QLabel("Medição:", self))
        top.addWidget(self.measurement_combo, 1)
        top.addWidget(QLabel("Modelo:", self))
        top.addWidget(self.model_combo, 1)
        top.addWidget(self.editor_button)
        top.addWidget(self.fit_button)

        side = QVBoxLayout()
        diagram_box = QGroupBox("Circuito", self)
        diagram_layout = QVBoxLayout(diagram_box)
        diagram_layout.addWidget(diagram_scroll)
        side.addWidget(diagram_box)
        side.addWidget(self.params_table, 1)
        stats_box = QGroupBox("Qualidade do ajuste", self)
        stats_layout = QVBoxLayout(stats_box)
        stats_layout.addWidget(self.stats_label)
        side.addWidget(stats_box)
        side_widget = QWidget(self)
        side_widget.setLayout(side)
        side_widget.setMaximumWidth(440)

        content = QHBoxLayout()
        content.addWidget(self.canvas, 1)
        content.addWidget(side_widget)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(content, 1)

        self._update_diagram_preview()

    # -- Circuito atual -----------------------------------------------------
    def _current_spec(self) -> Optional["circuitos.CircuitSpec"]:
        """Especificação do circuito atualmente selecionado."""
        model_key = self.model_combo.currentData()
        if model_key == "__custom__":
            return self._custom_spec
        try:
            return circuitos.build_circuit_spec(
                circuitos.preset_tree(model_key)
            )
        except (KeyError, ValueError):
            return None

    def _update_diagram_preview(self) -> None:
        """Mostra o circuito selecionado no diagrama (sem valores)."""
        spec = self._current_spec()
        if spec is None:
            self.diagram.set_circuit(None)
            return
        if (
            self.model_combo.currentData() == "__custom__"
            and self._custom_guesses is not None
        ):
            lines = circuit_value_lines(spec, self._custom_guesses)
        else:
            lines = None
        self.diagram.set_circuit(spec.tree, lines)

    def open_editor(self) -> None:
        """Abre o editor de circuito livre."""
        measurement = self._window.measurements.get(
            self.measurement_combo.currentText()
        )
        dialog = CircuitBuilderDialog(
            self,
            measurement=measurement,
            spec=self._custom_spec,
            guesses=self._custom_guesses,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._custom_spec = dialog.spec
        self._custom_guesses = dialog.guesses()
        text = f"Personalizado — {self._custom_spec.circuit_string}"
        index = self.model_combo.findData("__custom__")
        if index < 0:
            self.model_combo.addItem(text, "__custom__")
            index = self.model_combo.count() - 1
        else:
            self.model_combo.setItemText(index, text)
        self.model_combo.setCurrentIndex(index)
        self._update_diagram_preview()
        self._window.show_status(
            "Circuito personalizado definido: "
            f"{self._custom_spec.circuit_string}"
        )

    def run_fit(self) -> None:
        """Executa o ajuste de circuito da medição escolhida."""
        name = self.measurement_combo.currentText()
        measurement = self._window.measurements.get(name)
        if measurement is None:
            QMessageBox.information(
                self,
                "Ajuste de circuito",
                "Adicione e selecione uma medição primeiro.",
            )
            return
        model_key = self.model_combo.currentData()
        spec = self._current_spec()
        if model_key == "__custom__" and spec is None:
            QMessageBox.information(
                self,
                "Ajuste de circuito",
                "Defina primeiro o circuito no Editor de circuito…",
            )
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            if model_key == "__custom__":
                result = circuitos.fit_custom_circuit(
                    measurement, spec, self._custom_guesses
                )
            else:
                result = circuitos.fit_circuit(measurement, model_key)
        except (ValueError, RuntimeError, KeyError) as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Ajuste de circuito", str(exc))
            return
        except Exception as exc:  # pragma: no cover - proteção geral
            QApplication.restoreOverrideCursor()
            logger.exception("Erro inesperado no ajuste de circuito.")
            QMessageBox.critical(
                self,
                "Ajuste de circuito",
                f"Erro inesperado no ajuste:\n{exc}",
            )
            return
        QApplication.restoreOverrideCursor()

        self._window.fit_results[name] = result
        self.canvas.clear()
        plot_circuit_fit(
            self.canvas.figure, result, self._window.plot_style()
        )
        self.canvas.draw()

        if spec is not None:
            self.diagram.set_circuit(
                spec.tree,
                circuit_value_lines(
                    spec, [float(v) for v in result.param_values]
                ),
            )

        self.params_table.setRowCount(0)
        for param_name, value_text, error_text in result.summary_rows():
            row = self.params_table.rowCount()
            self.params_table.insertRow(row)
            self.params_table.setItem(
                row, 0, QTableWidgetItem(param_name)
            )
            self.params_table.setItem(
                row, 1, QTableWidgetItem(value_text)
            )
            self.params_table.setItem(
                row, 2, QTableWidgetItem(error_text)
            )

        self.stats_label.setText(
            f"Modelo: {result.model_name}\n"
            f"Circuito: {result.circuit_string}\n"
            f"χ² = {result.chi_squared:.5g}\n"
            f"χ² reduzido = {result.chi_squared_reduced:.5g}\n"
            f"RMSE = {result.rmse:.5g} Ω\n"
            f"R² = {result.r_squared:.6f}"
        )
        self._window.show_status(
            f"Ajuste de '{name}' concluído "
            f"(R² = {result.r_squared:.6f})."
        )


class ComparisonTab(QWidget):
    """Aba de comparação sobreposta de medições."""

    _KINDS: tuple[tuple[str, str], ...] = (
        ("Nyquist", "nyquist"),
        ("Bode — Magnitude", "bode_mag"),
        ("Bode — Fase", "bode_phase"),
        ("Bode completo (|Z| + Fase)", "bode_completo"),
    )

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self._window = window

        self.kind_combo = QComboBox(self)
        for label, kind in self._KINDS:
            self.kind_combo.addItem(label, kind)
        self.kind_combo.currentIndexChanged.connect(
            lambda _index: self.refresh()
        )

        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.list_widget.setMaximumWidth(260)
        self.list_widget.itemSelectionChanged.connect(self.refresh)

        self.select_all_button = QPushButton("Selecionar todas", self)
        self.select_all_button.clicked.connect(self.list_widget.selectAll)

        self.canvas = PlotCanvas(self)

        side = QVBoxLayout()
        side.addWidget(QLabel("Medições a comparar:", self))
        side.addWidget(self.list_widget, 1)
        side.addWidget(self.select_all_button)
        side_widget = QWidget(self)
        side_widget.setLayout(side)
        side_widget.setMaximumWidth(280)

        top = QHBoxLayout()
        top.addWidget(QLabel("Tipo de gráfico:", self))
        top.addWidget(self.kind_combo, 1)

        content = QHBoxLayout()
        content.addWidget(side_widget)
        content.addWidget(self.canvas, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(content, 1)

    def sync_measurements(self, names: Sequence[str]) -> None:
        """Sincroniza a lista de medições, preservando a seleção."""
        selected = {
            item.text() for item in self.list_widget.selectedItems()
        }
        self.list_widget.blockSignals(True)
        try:
            self.list_widget.clear()
            for name in names:
                item = QListWidgetItem(name, self.list_widget)
                item.setSelected(name in selected)
        finally:
            self.list_widget.blockSignals(False)
        self.refresh()

    def refresh(self) -> None:
        """Redesenha a comparação com as medições selecionadas."""
        names = [
            item.text() for item in self.list_widget.selectedItems()
        ]
        measurements = [
            self._window.measurements[name]
            for name in names
            if name in self._window.measurements
        ]
        self.canvas.clear()
        if measurements:
            kind = self.kind_combo.currentData()
            plot_comparison(
                self.canvas.figure,
                measurements,
                kind,
                self._window.plot_style(),
            )
        self.canvas.draw()


# ---------------------------------------------------------------------------
# Janela principal
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    """Janela principal do AMOSTRAS FRA 2.0."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{util.APP_NAME}")
        icon_file = util.icon_path()
        if icon_file is not None:
            self.setWindowIcon(QIcon(str(icon_file)))
        self.resize(1360, 840)

        #: Medições ativas, indexadas por nome (ordem de inserção).
        self.measurements: dict[str, Measurement] = {}
        #: Curvas I-V do módulo, indexadas por nome.
        self.iv_curves: dict[str, util.IVCurve] = {}
        #: Cores personalizadas por medição (``{nome: "#rrggbb"}``).
        self.curve_colors: dict[str, str] = {}
        #: Resultados de Kramers-Kronig por medição.
        self.kk_results: dict[str, kk_module.KKResult] = {}
        #: Resultados de ajuste de circuito por medição.
        self.fit_results: dict[str, circuitos.FitResult] = {}
        #: Resultados de ajuste do modelo de diodo por curva I-V.
        self.iv_fit_results: dict[str, iv_model.IVFitResult] = {}
        #: Biblioteca de correções do instrumento (``{nome: correção}``).
        self.corrections: dict[str, InstrumentCorrection] = {}
        #: Janela de simulação do módulo FV (criada sob demanda).
        self._simulation_dialog: Optional[PVSimulationDialog] = None
        #: Janela de conexão serial (criada sob demanda).
        self._serial_dialog: Optional[SerialDialog] = None
        #: Janelas do criador de gráficos abertas.
        self._chart_dialogs: list[ChartBuilderDialog] = []

        self._build_central_tabs()
        self._build_measurement_dock()
        self._build_options_dock()
        self._build_menus_and_toolbar()
        self.statusBar().showMessage(
            "Pronto. Cole ou importe dados na aba \"Dados\" e adicione "
            "medições."
        )

    # -- Construção da interface ----------------------------------------
    def _build_central_tabs(self) -> None:
        """Cria a área central com as abas de dados e gráficos."""
        self.tabs = QTabWidget(self)

        self.data_panel = DataEntryPanel(
            self, corrections_provider=lambda: self.corrections
        )
        self.data_panel.measurementCreated.connect(self.add_measurement)
        self.data_panel.measurementUpdated.connect(
            self._update_selected_measurement
        )
        self.data_panel.ivCurvesImported.connect(
            self._on_iv_curves_imported
        )

        self.nyquist_canvas = PlotCanvas(self)
        self.bode_mag_canvas = PlotCanvas(self)
        self.bode_phase_canvas = PlotCanvas(self)
        self.kk_tab = KKTab(self)
        self.circuit_tab = CircuitTab(self)
        self.comparison_tab = ComparisonTab(self)
        self.iv_tab = IVTab(self)

        self.tabs.addTab(self.data_panel, "Dados")
        self.tabs.addTab(self.iv_tab, "Curva I-V")
        self.tabs.addTab(self.nyquist_canvas, "Nyquist")
        self.tabs.addTab(self.bode_mag_canvas, "Bode Magnitude")
        self.tabs.addTab(self.bode_phase_canvas, "Bode Fase")
        self.tabs.addTab(self.kk_tab, "Kramers-Kronig")
        self.tabs.addTab(self.circuit_tab, "Circuito Equivalente")
        self.tabs.addTab(self.comparison_tab, "Comparação")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.setCentralWidget(self.tabs)

    def _build_measurement_dock(self) -> None:
        """Cria o dock lateral com a lista de medições."""
        self.measurement_list = QListWidget(self)
        self.measurement_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.measurement_list.itemChanged.connect(
            self._on_measurement_item_changed
        )
        self.measurement_list.itemDoubleClicked.connect(
            self._on_measurement_double_clicked
        )

        load_button = QPushButton("Carregar na tabela", self)
        load_button.clicked.connect(self._load_selected_into_table)
        rename_button = QPushButton("Renomear", self)
        rename_button.clicked.connect(self._rename_selected_measurement)
        duplicate_button = QPushButton("Duplicar", self)
        duplicate_button.clicked.connect(
            self._duplicate_selected_measurement
        )
        remove_button = QPushButton("Remover", self)
        remove_button.clicked.connect(self._remove_selected_measurements)

        color_button = QPushButton("Cor da curva…", self)
        color_button.setToolTip(
            "Define a cor das medições selecionadas nos gráficos."
        )
        color_button.clicked.connect(self._set_selected_curve_color)
        auto_color_button = QPushButton("Cor automática", self)
        auto_color_button.setToolTip(
            "Volta as medições selecionadas às cores automáticas."
        )
        auto_color_button.clicked.connect(self._clear_selected_curve_color)

        check_all_button = QPushButton("Marcar todas", self)
        check_all_button.clicked.connect(
            lambda: self._set_all_checked(True)
        )
        uncheck_all_button = QPushButton("Desmarcar todas", self)
        uncheck_all_button.clicked.connect(
            lambda: self._set_all_checked(False)
        )

        hint = QLabel(
            "Amostras compartilhadas entre FRA e Curva I-V — cada uma "
            "pode ter FRA, curva I-V ou ambos (passe o mouse para ver). "
            "Marque para exibir nos gráficos (Nyquist/Bode e I-V). "
            "Clique duas vezes para carregar o FRA na tabela; use "
            "\"Cor da curva…\" para a cor.",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9a9a9a;")

        layout = QVBoxLayout()
        layout.addWidget(hint)
        layout.addWidget(self.measurement_list, 1)
        row1 = QHBoxLayout()
        row1.addWidget(load_button)
        row1.addWidget(rename_button)
        layout.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addWidget(duplicate_button)
        row2.addWidget(remove_button)
        layout.addLayout(row2)
        row_color = QHBoxLayout()
        row_color.addWidget(color_button)
        row_color.addWidget(auto_color_button)
        layout.addLayout(row_color)
        row3 = QHBoxLayout()
        row3.addWidget(check_all_button)
        row3.addWidget(uncheck_all_button)
        layout.addLayout(row3)

        container = QWidget(self)
        container.setLayout(layout)

        self.measurement_dock = QDockWidget("Medições", self)
        self.measurement_dock.setObjectName("dock_medicoes")
        self.measurement_dock.setWidget(container)
        self.addDockWidget(
            Qt.DockWidgetArea.LeftDockWidgetArea, self.measurement_dock
        )

    def _build_options_dock(self) -> None:
        """Cria o dock de opções de estilo dos gráficos."""
        self.marker_combo = QComboBox(self)
        for label, marker in _MARKERS:
            self.marker_combo.addItem(label, marker)

        self.marker_size_spin = QDoubleSpinBox(self)
        self.marker_size_spin.setRange(1.0, 20.0)
        self.marker_size_spin.setSingleStep(0.5)
        self.marker_size_spin.setValue(4.5)

        self.line_width_spin = QDoubleSpinBox(self)
        self.line_width_spin.setRange(0.2, 8.0)
        self.line_width_spin.setSingleStep(0.2)
        self.line_width_spin.setValue(1.4)

        self.line_style_combo = QComboBox(self)
        for label, style in _LINE_STYLES:
            self.line_style_combo.addItem(label, style)

        self.grid_checkbox = QCheckBox("Exibir grade", self)
        self.grid_checkbox.setChecked(True)

        # Cores de fundo (padrão: tema escuro dos gráficos).
        self.figure_color_button = ColorButton(
            default="#1e1e1e", parent=self
        )
        self.figure_color_button.set_color("#1e1e1e")
        self.axes_color_button = ColorButton(
            default="#252526", parent=self
        )
        self.axes_color_button.set_color("#252526")
        self.grid_color_button = ColorButton(
            default="#3c3c3c", parent=self
        )
        self.grid_color_button.set_color("#3c3c3c")
        self.text_color_button = ColorButton(
            default="#d4d4d4", parent=self
        )
        self.text_color_button.set_color("#d4d4d4")

        reset_colors_button = QPushButton("Restaurar cores do tema", self)
        reset_colors_button.clicked.connect(self._reset_plot_colors)

        light_preset_button = QPushButton("Fundo claro (publicação)", self)
        light_preset_button.clicked.connect(self._apply_light_preset)

        for widget_signal in (
            self.marker_combo.currentIndexChanged,
            self.line_style_combo.currentIndexChanged,
        ):
            widget_signal.connect(lambda _index: self.refresh_plots())
        self.marker_size_spin.valueChanged.connect(
            lambda _value: self.refresh_plots()
        )
        self.line_width_spin.valueChanged.connect(
            lambda _value: self.refresh_plots()
        )
        self.grid_checkbox.toggled.connect(
            lambda _checked: self.refresh_plots()
        )
        for button in (
            self.figure_color_button,
            self.axes_color_button,
            self.grid_color_button,
            self.text_color_button,
        ):
            button.colorChanged.connect(self.refresh_plots)

        form = QFormLayout()
        form.addRow("Marcador:", self.marker_combo)
        form.addRow("Tamanho do marcador:", self.marker_size_spin)
        form.addRow("Espessura da linha:", self.line_width_spin)
        form.addRow("Estilo da linha:", self.line_style_combo)
        form.addRow(self.grid_checkbox)
        form.addRow(QLabel("— Cores —", self))
        form.addRow("Fundo da figura:", self.figure_color_button)
        form.addRow("Fundo do gráfico:", self.axes_color_button)
        form.addRow("Grade:", self.grid_color_button)
        form.addRow("Texto/eixos:", self.text_color_button)
        form.addRow(light_preset_button)
        form.addRow(reset_colors_button)

        hint = QLabel(
            "Dica: para mudar a cor de uma curva, selecione-a na lista "
            "\"Medições\" e clique em \"Cor da curva…\". Zoom, pan e "
            "salvar imagem ficam na barra de cada gráfico.",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9a9a9a;")
        form.addRow(hint)

        container = QWidget(self)
        container.setLayout(form)

        self.options_dock = QDockWidget("Estilo dos gráficos", self)
        self.options_dock.setObjectName("dock_estilo")
        self.options_dock.setWidget(container)
        self.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea, self.options_dock
        )

    def _reset_plot_colors(self) -> None:
        """Restaura as cores de fundo/grade/texto do tema escuro."""
        for button in (
            self.figure_color_button,
            self.axes_color_button,
            self.grid_color_button,
            self.text_color_button,
        ):
            button.blockSignals(True)
            button.reset()
            button.blockSignals(False)
        self.refresh_plots()

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
        self.refresh_plots()

    def _build_menus_and_toolbar(self) -> None:
        """Cria menus, ações e toolbar."""
        style = self.style()

        # -- Ações -------------------------------------------------------
        self.action_import = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton),
            "Importar dados…",
            self,
        )
        self.action_import.setShortcut(QKeySequence.StandardKey.Open)
        self.action_import.triggered.connect(
            self.data_panel._on_import_clicked
        )

        self.action_add_measurement = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder),
            "Adicionar tabela como medição",
            self,
        )
        self.action_add_measurement.setShortcut("Ctrl+M")
        self.action_add_measurement.triggered.connect(
            self.data_panel._on_add_measurement
        )

        self.action_export_excel = QAction("Exportar Excel…", self)
        self.action_export_excel.triggered.connect(self._export_excel)

        self.action_export_csv = QAction("Exportar CSV…", self)
        self.action_export_csv.triggered.connect(self._export_csv)

        self.action_save_project = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton),
            "Salvar projeto…",
            self,
        )
        self.action_save_project.setShortcut(QKeySequence.StandardKey.Save)
        self.action_save_project.setToolTip(
            "Salva a sessão inteira (FRA, I-V, correções, ajustes de "
            "circuito e de diodo, cores e marcações) em um arquivo .fra."
        )
        self.action_save_project.triggered.connect(self._save_project)

        self.action_open_project = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
            "Abrir projeto…",
            self,
        )
        self.action_open_project.setToolTip(
            "Abre um projeto .fra, restaurando toda a sessão salva."
        )
        self.action_open_project.triggered.connect(self._open_project)

        self.action_export_image = QAction(
            "Exportar imagem do gráfico atual…", self
        )
        self.action_export_image.triggered.connect(self._export_image)

        self.action_report = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            "Gerar relatório PDF…",
            self,
        )
        self.action_report.triggered.connect(self._generate_report)

        self.action_quit = QAction("Sair", self)
        self.action_quit.setShortcut(QKeySequence.StandardKey.Quit)
        self.action_quit.triggered.connect(self.close)

        self.action_paste = QAction("Colar na tabela", self)
        self.action_paste.setShortcut(QKeySequence.StandardKey.Paste)
        self.action_paste.triggered.connect(self._paste_into_table)

        self.action_kk = QAction("Validar Kramers-Kronig", self)
        self.action_kk.triggered.connect(self._run_kk_from_menu)

        self.action_fit = QAction("Ajustar circuito equivalente", self)
        self.action_fit.triggered.connect(self._run_fit_from_menu)

        self.action_correction = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView),
            "Correção do Instrumento…",
            self,
        )
        self.action_correction.triggered.connect(
            self._open_correction_dialog
        )

        self.action_apply_correction = QAction(
            "Aplicar correção às medições marcadas…", self
        )
        self.action_apply_correction.setToolTip(
            "Escolhe uma correção da biblioteca e a aplica às medições "
            "marcadas (as demais ficam sem correção)."
        )
        self.action_apply_correction.triggered.connect(
            self._apply_correction
        )

        self.action_simulation = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
            "Simulação do módulo FV…",
            self,
        )
        self.action_simulation.setToolTip(
            "Animação didática do corte do módulo fotovoltaico: "
            "camadas, fingers, fótons e elétrons percorrendo o "
            "circuito, com a correspondência para o circuito "
            "equivalente."
        )
        self.action_simulation.triggered.connect(self._open_simulation)

        self.action_serial = QAction(
            style.standardIcon(
                QStyle.StandardPixmap.SP_ComputerIcon
            ),
            "Conexão Serial…",
            self,
        )
        self.action_serial.setToolTip(
            "Recebe pontos de medição de um sistema embarcado por "
            "porta serial (padrão 115200 baud): frequência, tensão, "
            "corrente e fase."
        )
        self.action_serial.triggered.connect(self._open_serial_dialog)

        self.action_chart_builder = QAction(
            style.standardIcon(
                QStyle.StandardPixmap.SP_FileDialogListView
            ),
            "Criador de gráficos…",
            self,
        )
        self.action_chart_builder.setToolTip(
            "Compõe gráficos personalizados (Bode ganho+fase, Nyquist) "
            "com qualquer quantidade de medições, paletas de cor e "
            "zoom de destaque."
        )
        self.action_chart_builder.triggered.connect(
            self._open_chart_builder
        )

        self.action_help = QAction("Guia do usuário", self)
        self.action_help.setShortcut(
            QKeySequence(QKeySequence.StandardKey.HelpContents)
        )
        self.action_help.setToolTip(
            "Abre o guia completo do programa (F1)."
        )
        self.action_help.triggered.connect(self._open_help)

        self.action_about = QAction("Sobre…", self)
        self.action_about.triggered.connect(self._show_about)

        # -- Menus ---------------------------------------------------------
        menu_file = self.menuBar().addMenu("&Arquivo")
        menu_file.addAction(self.action_open_project)
        menu_file.addAction(self.action_save_project)
        menu_file.addSeparator()
        menu_file.addAction(self.action_import)
        export_menu = menu_file.addMenu("Exportar")
        export_menu.addAction(self.action_export_excel)
        export_menu.addAction(self.action_export_csv)
        export_menu.addAction(self.action_export_image)
        export_menu.addAction(self.action_report)
        menu_file.addSeparator()
        menu_file.addAction(self.action_quit)

        menu_edit = self.menuBar().addMenu("&Editar")
        menu_edit.addAction(self.action_paste)
        menu_edit.addAction(
            "Adicionar 20 linhas à tabela",
            lambda: self.data_panel.table.add_rows(20),
        )
        menu_edit.addAction(
            "Limpar tabela", self.data_panel.table.clear_all
        )

        menu_meas = self.menuBar().addMenu("&Medições")
        menu_meas.addAction(self.action_add_measurement)
        menu_meas.addAction(
            "Atualizar medição selecionada",
            self.data_panel._on_update_measurement,
        )
        menu_meas.addSeparator()
        menu_meas.addAction(
            "Carregar medição na tabela",
            self._load_selected_into_table,
        )
        menu_meas.addAction("Renomear", self._rename_selected_measurement)
        menu_meas.addAction(
            "Duplicar", self._duplicate_selected_measurement
        )
        menu_meas.addAction(
            "Remover", self._remove_selected_measurements
        )
        menu_meas.addSeparator()
        menu_meas.addAction(
            "Marcar todas", lambda: self._set_all_checked(True)
        )
        menu_meas.addAction(
            "Desmarcar todas", lambda: self._set_all_checked(False)
        )

        menu_analysis = self.menuBar().addMenu("&Análise")
        menu_analysis.addAction(self.action_kk)
        menu_analysis.addAction(self.action_fit)
        menu_analysis.addSeparator()
        menu_analysis.addAction(self.action_correction)
        menu_analysis.addAction(self.action_apply_correction)

        menu_tools = self.menuBar().addMenu("&Ferramentas")
        menu_tools.addAction(self.action_serial)
        menu_tools.addAction(self.action_chart_builder)
        menu_tools.addAction(self.action_simulation)

        menu_view = self.menuBar().addMenu("E&xibir")
        menu_view.addAction(self.measurement_dock.toggleViewAction())
        menu_view.addAction(self.options_dock.toggleViewAction())

        menu_help = self.menuBar().addMenu("A&juda")
        menu_help.addAction(self.action_help)
        menu_help.addSeparator()
        menu_help.addAction(self.action_about)

        # -- Toolbar ---------------------------------------------------------
        toolbar = QToolBar("Principal", self)
        toolbar.setObjectName("toolbar_principal")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        toolbar.addAction(self.action_open_project)
        toolbar.addAction(self.action_save_project)
        toolbar.addSeparator()
        toolbar.addAction(self.action_import)
        toolbar.addAction(self.action_add_measurement)
        toolbar.addSeparator()
        toolbar.addAction(self.action_kk)
        toolbar.addAction(self.action_fit)
        toolbar.addAction(self.action_correction)
        toolbar.addSeparator()
        toolbar.addAction(self.action_serial)
        toolbar.addAction(self.action_chart_builder)
        toolbar.addAction(self.action_simulation)
        toolbar.addAction(self.action_report)
        self.addToolBar(toolbar)

    # -- Estilo dos gráficos -----------------------------------------------
    def plot_style(self) -> PlotStyle:
        """Estilo atual escolhido pelo usuário no dock de opções."""
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
            colors=dict(self.curve_colors),
        )

    # -- Gerência de medições ------------------------------------------------
    def checked_measurements(self) -> list[Measurement]:
        """Medições (FRA/EIS) das amostras marcadas na lista lateral."""
        result: list[Measurement] = []
        for index in range(self.measurement_list.count()):
            item = self.measurement_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                measurement = self.measurements.get(item.text())
                if measurement is not None:
                    result.append(measurement)
        return result

    def checked_iv_curves(self) -> list[util.IVCurve]:
        """Curvas I-V das amostras marcadas na lista lateral."""
        result: list[util.IVCurve] = []
        for index in range(self.measurement_list.count()):
            item = self.measurement_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                curve = self.iv_curves.get(item.text())
                if curve is not None:
                    result.append(curve)
        return result

    def sample_names(self) -> list[str]:
        """Nomes das amostras na lista lateral, em ordem."""
        return [
            self.measurement_list.item(i).text()
            for i in range(self.measurement_list.count())
        ]

    def _ensure_sample_item(
        self, name: str, checked: bool
    ) -> QListWidgetItem:
        """Encontra o item da amostra ``name`` na lista (ou o cria).

        Se o item já existe (amostra com FRA ou I-V), ele é reutilizado
        — apenas é marcado quando ``checked`` for verdadeiro.
        """
        for index in range(self.measurement_list.count()):
            item = self.measurement_list.item(index)
            if item.text() == name:
                if (
                    checked
                    and item.checkState() != Qt.CheckState.Checked
                ):
                    self.measurement_list.blockSignals(True)
                    try:
                        item.setCheckState(Qt.CheckState.Checked)
                    finally:
                        self.measurement_list.blockSignals(False)
                return item
        self.measurement_list.blockSignals(True)
        try:
            item = QListWidgetItem(name, self.measurement_list)
            item.setFlags(
                item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(
                Qt.CheckState.Checked
                if checked
                else Qt.CheckState.Unchecked
            )
        finally:
            self.measurement_list.blockSignals(False)
        return item

    def update_sample_tooltip(self, name: str) -> None:
        """Atualiza a dica do item indicando o que a amostra contém."""
        contents: list[str] = []
        if name in self.measurements:
            contents.append("FRA/EIS")
        if name in self.iv_curves:
            contents.append("Curva I-V")
        tip = f"{name}: {' + '.join(contents) or 'vazia'}"
        for index in range(self.measurement_list.count()):
            item = self.measurement_list.item(index)
            if item.text() == name:
                item.setToolTip(tip)
                return

    def add_measurement(
        self, measurement: Measurement, checked: bool = True
    ) -> None:
        """Adiciona/associa uma medição (FRA/EIS) a uma amostra.

        Args:
            measurement: Medição a adicionar.
            checked: Se a amostra inicia marcada para exibição.
        """
        name = unique_name(
            measurement.name, list(self.measurements.keys())
        )
        if name != measurement.name:
            measurement = measurement.copy(new_name=name)
        self.measurements[name] = measurement
        self._ensure_sample_item(name, checked)
        self.update_sample_tooltip(name)

        logger.info(
            "Medição adicionada: '%s' (%d pontos).",
            name,
            measurement.n_points,
        )
        self._sync_measurement_widgets()
        self.refresh_plots()
        self.iv_tab.refresh()
        self.show_status(
            f"Medição '{name}' adicionada "
            f"({measurement.n_points} pontos)."
        )

    def add_iv_curve(
        self, curve: util.IVCurve, checked: bool = True
    ) -> None:
        """Adiciona/associa uma curva I-V a uma amostra.

        Se já existir uma amostra com o mesmo nome (por exemplo, com um
        FRA), a curva I-V é associada a ela; caso contrário, cria uma
        nova amostra.

        Args:
            curve: Curva a adicionar.
            checked: Se a amostra inicia marcada para exibição.
        """
        # Nome único apenas entre as curvas I-V; nomes que coincidem
        # com amostras de FRA são atrelados (associação FRA↔I-V).
        name = unique_name(curve.name, list(self.iv_curves.keys()))
        if name != curve.name:
            curve = curve.copy(new_name=name)
        self.iv_curves[name] = curve
        self._ensure_sample_item(name, checked)
        self.update_sample_tooltip(name)

        logger.info(
            "Curva I-V adicionada: '%s' (%d pontos).",
            name,
            curve.n_points,
        )
        self._sync_measurement_widgets()
        self.iv_tab.refresh()
        self.show_status(
            f"Curva I-V '{name}' associada à amostra "
            f"({curve.n_points} pontos; Pmáx = {curve.p_max:.4g} W)."
        )

    def _on_iv_curves_imported(self, curves: "Sequence[util.IVCurve]") -> None:
        """Restaura curvas I-V vindas de um CSV de sessão (importação).

        Cada curva é associada à amostra de mesmo nome (por exemplo, o
        FRA recém-importado); nomes sem amostra correspondente criam
        uma amostra nova.  Atualiza a lista e o gráfico uma única vez.
        """
        added = 0
        for curve in curves:
            name = unique_name(curve.name, list(self.iv_curves.keys()))
            if name != curve.name:
                curve = curve.copy(new_name=name)
            self.iv_curves[name] = curve
            self.iv_fit_results.pop(name, None)
            self._ensure_sample_item(name, checked=True)
            self.update_sample_tooltip(name)
            added += 1
        if added:
            self._sync_measurement_widgets()
            self.iv_tab.refresh()
            logger.info("Importadas %d curva(s) I-V de sessão.", added)
            self.show_status(
                f"{added} curva(s) I-V importada(s) e associada(s) às "
                "amostras."
            )

    def _selected_list_item(
        self, warn: bool = True
    ) -> Optional[QListWidgetItem]:
        """Item atualmente selecionado na lista (ou None)."""
        items = self.measurement_list.selectedItems()
        if not items:
            if warn:
                QMessageBox.information(
                    self,
                    "Amostras",
                    "Selecione uma amostra na lista lateral primeiro.",
                )
            return None
        return items[0]

    def selected_sample_name(self, warn: bool = True) -> Optional[str]:
        """Nome da amostra selecionada na lista lateral (ou None)."""
        item = self._selected_list_item(warn=warn)
        return item.text() if item is not None else None

    def set_iv_curve(
        self, sample_name: str, curve: util.IVCurve, checked: bool = True
    ) -> None:
        """Define a curva I-V de uma amostra (cria a amostra se preciso)."""
        self.iv_curves[sample_name] = curve.copy(new_name=sample_name)
        self._ensure_sample_item(sample_name, checked)
        self.update_sample_tooltip(sample_name)
        self._sync_measurement_widgets()
        self.iv_tab.refresh()

    def _remove_sample_item(self, name: str) -> None:
        """Remove o item da amostra ``name`` da lista lateral."""
        self.measurement_list.blockSignals(True)
        try:
            for index in range(self.measurement_list.count()):
                if self.measurement_list.item(index).text() == name:
                    self.measurement_list.takeItem(index)
                    return
        finally:
            self.measurement_list.blockSignals(False)

    def import_iv_curves_with_mapping(
        self,
        curves: Sequence[util.IVCurve],
        mapping: dict[str, str],
    ) -> int:
        """Adiciona curvas I-V aplicando a associação escolhida.

        Args:
            curves: Curvas importadas.
            mapping: ``{nome da curva: alvo}`` — nome de amostra,
                ``IVAssociationDialog.NEW`` ou ``.SKIP``.

        Returns:
            Número de curvas efetivamente importadas.
        """
        added = 0
        for curve in curves:
            choice = mapping.get(curve.name, IVAssociationDialog.NEW)
            if choice == IVAssociationDialog.SKIP:
                continue
            if choice == IVAssociationDialog.NEW:
                self.add_iv_curve(curve, checked=True)
            else:
                self.set_iv_curve(choice, curve, checked=True)
            added += 1
        return added

    def reassign_iv_curve(self, from_name: str, to_name: str) -> None:
        """Move a curva I-V da amostra ``from_name`` para ``to_name``."""
        if from_name == to_name or from_name not in self.iv_curves:
            return
        curve = self.iv_curves.pop(from_name)
        self.iv_curves[to_name] = curve.copy(new_name=to_name)
        # O ajuste de diodo deixa de valer para o novo par de dados.
        self.iv_fit_results.pop(from_name, None)
        self.iv_fit_results.pop(to_name, None)
        if (
            from_name in self.curve_colors
            and to_name not in self.curve_colors
        ):
            self.curve_colors[to_name] = self.curve_colors[from_name]
        # Remove a amostra de origem se ela não tiver mais FRA nem I-V.
        if (
            from_name not in self.measurements
            and from_name not in self.iv_curves
        ):
            self._remove_sample_item(from_name)
            self.curve_colors.pop(from_name, None)
        self._ensure_sample_item(to_name, checked=True)
        self.update_sample_tooltip(to_name)
        self.update_sample_tooltip(from_name)

    def reassign_iv_curves(self, mapping: dict[str, str]) -> int:
        """Aplica um mapeamento de reassociação de curvas I-V.

        Args:
            mapping: ``{nome atual: nome da amostra alvo}``.

        Returns:
            Número de curvas reassociadas.
        """
        moved = 0
        for from_name, to_name in mapping.items():
            if (
                to_name in (
                    IVAssociationDialog.NEW,
                    IVAssociationDialog.SKIP,
                )
                or to_name == from_name
            ):
                continue
            self.reassign_iv_curve(from_name, to_name)
            moved += 1
        if moved:
            self._sync_measurement_widgets()
            self._apply_list_item_colors()
            self.refresh_plots()
            self.iv_tab.refresh()
        return moved

    def _update_selected_measurement(
        self, template: Measurement
    ) -> None:
        """Atualiza a medição selecionada com os dados da tabela.

        O estado de correção (``corrected`` e a nota) vem do
        ``template``, refletindo a correção escolhida no seletor da
        aba Dados.
        """
        item = self._selected_list_item()
        if item is None:
            return
        name = item.text()
        updated = template.copy(new_name=name)
        self.measurements[name] = updated
        self.kk_results.pop(name, None)
        self.fit_results.pop(name, None)
        logger.info(
            "Medição '%s' atualizada pela tabela (corrigida=%s).",
            name,
            updated.corrected,
        )
        self.refresh_plots()
        status = f"Medição '{name}' atualizada."
        if updated.corrected:
            status += " Correção do instrumento aplicada."
        self.show_status(status)

    def _load_selected_into_table(self) -> None:
        """Carrega a medição selecionada na tabela de dados."""
        item = self._selected_list_item()
        if item is None:
            return
        measurement = self.measurements.get(item.text())
        if measurement is None:
            return
        self.data_panel.load_measurement(measurement)
        self.tabs.setCurrentWidget(self.data_panel)
        self.show_status(
            f"Medição '{measurement.name}' carregada na tabela."
        )

    def _on_measurement_double_clicked(
        self, item: QListWidgetItem
    ) -> None:
        """Duplo clique na lista: carrega a medição na tabela."""
        measurement = self.measurements.get(item.text())
        if measurement is None:
            return
        self.data_panel.load_measurement(measurement)
        self.tabs.setCurrentWidget(self.data_panel)

    def _rename_selected_measurement(self) -> None:
        """Renomeia a medição selecionada."""
        item = self._selected_list_item()
        if item is None:
            return
        old_name = item.text()
        new_name, ok = QInputDialog.getText(
            self,
            "Renomear medição",
            "Novo nome:",
            text=old_name,
        )
        new_name = new_name.strip()
        if not ok or not new_name or new_name == old_name:
            return
        if new_name in self.measurements or new_name in self.iv_curves:
            QMessageBox.warning(
                self,
                "Renomear amostra",
                f"Já existe uma amostra chamada '{new_name}'.",
            )
            return
        if old_name in self.measurements:
            measurement = self.measurements.pop(old_name)
            self.measurements[new_name] = measurement.copy(
                new_name=new_name
            )
        if old_name in self.iv_curves:
            curve = self.iv_curves.pop(old_name)
            self.iv_curves[new_name] = curve.copy(new_name=new_name)
        if old_name in self.kk_results:
            kk_result = self.kk_results.pop(old_name)
            kk_result.measurement_name = new_name
            self.kk_results[new_name] = kk_result
        if old_name in self.fit_results:
            fit_result = self.fit_results.pop(old_name)
            fit_result.measurement_name = new_name
            self.fit_results[new_name] = fit_result
        if old_name in self.iv_fit_results:
            iv_fit = self.iv_fit_results.pop(old_name)
            iv_fit.curve_name = new_name
            self.iv_fit_results[new_name] = iv_fit
        if old_name in self.curve_colors:
            self.curve_colors[new_name] = self.curve_colors.pop(old_name)
        self.measurement_list.blockSignals(True)
        try:
            item.setText(new_name)
        finally:
            self.measurement_list.blockSignals(False)
        self.update_sample_tooltip(new_name)
        logger.info(
            "Amostra renomeada: '%s' → '%s'.", old_name, new_name
        )
        self._sync_measurement_widgets()
        self.refresh_plots()
        self.iv_tab.refresh()

    def _duplicate_selected_measurement(self) -> None:
        """Duplica a amostra selecionada (FRA e/ou curva I-V)."""
        item = self._selected_list_item()
        if item is None:
            return
        old_name = item.text()
        new_name = unique_name(
            f"{old_name} (cópia)",
            list(self.measurements) + list(self.iv_curves),
        )
        measurement = self.measurements.get(old_name)
        curve = self.iv_curves.get(old_name)
        if measurement is None and curve is None:
            return
        if measurement is not None:
            self.measurements[new_name] = measurement.copy(
                new_name=new_name
            )
        if curve is not None:
            self.iv_curves[new_name] = curve.copy(new_name=new_name)
        self._ensure_sample_item(new_name, checked=False)
        self.update_sample_tooltip(new_name)
        self._sync_measurement_widgets()
        self.refresh_plots()
        self.iv_tab.refresh()
        self.show_status(f"Amostra '{new_name}' criada por duplicação.")

    def _remove_selected_measurements(self) -> None:
        """Remove as amostras selecionadas (FRA e curva I-V)."""
        items = self.measurement_list.selectedItems()
        if not items:
            QMessageBox.information(
                self,
                "Amostras",
                "Selecione ao menos uma amostra para remover.",
            )
            return
        names = [item.text() for item in items]
        answer = QMessageBox.question(
            self,
            "Remover amostras",
            "Remover as amostras selecionadas (FRA e curva I-V)?\n\n"
            + "\n".join(names),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        for name in names:
            self.measurements.pop(name, None)
            self.iv_curves.pop(name, None)
            self.kk_results.pop(name, None)
            self.fit_results.pop(name, None)
            self.iv_fit_results.pop(name, None)
            self.curve_colors.pop(name, None)
        self.measurement_list.blockSignals(True)
        try:
            for item in items:
                self.measurement_list.takeItem(
                    self.measurement_list.row(item)
                )
        finally:
            self.measurement_list.blockSignals(False)
        logger.info("Amostras removidas: %s.", ", ".join(names))
        self._sync_measurement_widgets()
        self.refresh_plots()
        self.iv_tab.refresh()

    def _set_all_checked(self, checked: bool) -> None:
        """Marca/desmarca todas as amostras da lista."""
        state = (
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        )
        self.measurement_list.blockSignals(True)
        try:
            for index in range(self.measurement_list.count()):
                self.measurement_list.item(index).setCheckState(state)
        finally:
            self.measurement_list.blockSignals(False)
        self.refresh_plots()
        self.iv_tab.refresh()

    def _set_selected_curve_color(self) -> None:
        """Escolhe a cor das medições selecionadas na lista."""
        items = self.measurement_list.selectedItems()
        if not items:
            QMessageBox.information(
                self,
                "Cor da curva",
                "Selecione ao menos uma medição na lista.",
            )
            return
        names = [item.text() for item in items]
        initial = QColor(self.curve_colors.get(names[0], "#4fc3f7"))
        chosen = QColorDialog.getColor(
            initial, self, "Cor da(s) amostra(s)"
        )
        if not chosen.isValid():
            return
        for name in names:
            self.curve_colors[name] = chosen.name()
        self._apply_list_item_colors()
        self.refresh_plots()
        self.iv_tab.refresh()

    def _clear_selected_curve_color(self) -> None:
        """Volta as amostras selecionadas às cores automáticas."""
        items = self.measurement_list.selectedItems()
        if not items:
            return
        for item in items:
            self.curve_colors.pop(item.text(), None)
        self._apply_list_item_colors()
        self.refresh_plots()
        self.iv_tab.refresh()

    def _apply_list_item_colors(self) -> None:
        """Colore o texto dos itens conforme a cor da curva."""
        default = QColor("#d4d4d4")
        for index in range(self.measurement_list.count()):
            item = self.measurement_list.item(index)
            color = self.curve_colors.get(item.text())
            item.setForeground(QColor(color) if color else default)

    def _on_measurement_item_changed(
        self, _item: QListWidgetItem
    ) -> None:
        """Reage à marcação/desmarcação de amostras."""
        self.refresh_plots()
        self.iv_tab.refresh()

    def _sync_measurement_widgets(self) -> None:
        """Sincroniza combos e a lista da aba de comparação."""
        names = list(self.measurements.keys())
        for combo in (
            self.kk_tab.measurement_combo,
            self.circuit_tab.measurement_combo,
        ):
            current = combo.currentText()
            combo.blockSignals(True)
            try:
                combo.clear()
                combo.addItems(names)
                if current in names:
                    combo.setCurrentText(current)
            finally:
                combo.blockSignals(False)
        self.comparison_tab.sync_measurements(names)

    # -- Gráficos --------------------------------------------------------
    def refresh_plots(self) -> None:
        """Redesenha os gráficos de Nyquist e Bode e a comparação."""
        measurements = self.checked_measurements()
        style = self.plot_style()

        self.nyquist_canvas.clear()
        if measurements:
            ax = self.nyquist_canvas.figure.add_subplot(111)
            plot_nyquist(ax, measurements, style)
        self.nyquist_canvas.draw()

        self.bode_mag_canvas.clear()
        if measurements:
            ax = self.bode_mag_canvas.figure.add_subplot(111)
            plot_bode_magnitude(ax, measurements, style)
        self.bode_mag_canvas.draw()

        self.bode_phase_canvas.clear()
        if measurements:
            ax = self.bode_phase_canvas.figure.add_subplot(111)
            plot_bode_phase(ax, measurements, style)
        self.bode_phase_canvas.draw()

        self.comparison_tab.refresh()

    def _on_tab_changed(self, _index: int) -> None:
        """Atualiza a barra de status ao trocar de aba."""
        count = len(self.checked_measurements())
        self.show_status(
            f"{len(self.measurements)} medição(ões) na sessão; "
            f"{count} marcada(s) para exibição."
        )

    def show_status(self, message: str) -> None:
        """Exibe uma mensagem na barra de status."""
        self.statusBar().showMessage(message, 8000)

    # -- Análise -----------------------------------------------------------
    def _run_kk_from_menu(self) -> None:
        """Atalho de menu: abre a aba KK e executa a validação."""
        self.tabs.setCurrentWidget(self.kk_tab)
        self.kk_tab.run_validation()

    def _run_fit_from_menu(self) -> None:
        """Atalho de menu: abre a aba de circuito e executa o ajuste."""
        self.tabs.setCurrentWidget(self.circuit_tab)
        self.circuit_tab.run_fit()

    def _open_correction_dialog(self) -> None:
        """Abre a janela de Correção do Instrumento (biblioteca)."""
        dialog = CorrectionDialog(self, self.corrections)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.corrections = dialog.corrections
            self.data_panel.refresh_corrections()
            if self.corrections:
                names = ", ".join(self.corrections)
                self.show_status(
                    f"{len(self.corrections)} correção(ões) na "
                    f"biblioteca: {names}."
                )
            else:
                self.show_status("Nenhuma correção configurada.")

    def _apply_correction(self) -> None:
        """Aplica uma correção escolhida às medições marcadas.

        As amostras que não precisam de correção simplesmente não são
        corrigidas (basta não aplicar); para as demais, escolhe-se qual
        correção da biblioteca usar.  As versões corrigidas são
        adicionadas à lista como novas medições.
        """
        if not self.corrections:
            QMessageBox.information(
                self,
                "Correção do instrumento",
                "Configure primeiro ao menos uma correção em "
                "Análise → Correção do Instrumento…",
            )
            return
        measurements = self.checked_measurements()
        if not measurements:
            QMessageBox.information(
                self,
                "Correção do instrumento",
                "Marque na lista lateral as medições que precisam de "
                "correção (as que não precisam, deixe desmarcadas).",
            )
            return

        names = list(self.corrections)
        if len(names) == 1:
            chosen = names[0]
        else:
            chosen, ok = QInputDialog.getItem(
                self,
                "Aplicar correção",
                "Correção a aplicar nas medições marcadas:",
                names,
                0,
                False,
            )
            if not ok or not chosen:
                return
        correction = self.corrections[chosen]

        applied = 0
        skipped = 0
        for measurement in measurements:
            if measurement.corrected:
                logger.info(
                    "Medição '%s' já corrigida; ignorada.",
                    measurement.name,
                )
                skipped += 1
                continue
            corrected = correction.apply(measurement)
            self.add_measurement(corrected, checked=False)
            applied += 1
        message = (
            f"Correção '{chosen}' aplicada a {applied} medição(ões); "
            "as versões corrigidas foram adicionadas à lista."
        )
        if skipped:
            message += f" {skipped} já estava(m) corrigida(s)."
        self.show_status(message)

    # -- Edição -------------------------------------------------------------
    def _paste_into_table(self) -> None:
        """Cola a área de transferência na tabela da aba ativa.

        Com a aba Curva I-V ativa, cola na tabela de I-V; nas demais,
        cola na tabela de dados (aba Dados).
        """
        if self.tabs.currentWidget() is self.iv_tab:
            self.iv_tab.table.paste_from_clipboard()
        else:
            self.tabs.setCurrentWidget(self.data_panel)
            self.data_panel.table.paste_from_clipboard()

    # -- Exportação -----------------------------------------------------------
    def _measurements_for_export(self) -> list[Measurement]:
        """Medições marcadas, com aviso se não houver nenhuma."""
        measurements = self.checked_measurements()
        if not measurements:
            QMessageBox.information(
                self,
                "Exportar",
                "Marque ao menos uma medição na lista lateral.",
            )
        return measurements

    def _export_excel(self) -> None:
        """Exporta as medições marcadas para XLSX."""
        measurements = self._measurements_for_export()
        if not measurements:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar Excel",
            "amostras_fra.xlsx",
            "Planilha do Excel (*.xlsx)",
        )
        if not path:
            return
        names = {m.name for m in measurements}
        try:
            exportacao.export_measurements_excel(
                measurements,
                path,
                fit_results=[
                    fit
                    for name, fit in self.fit_results.items()
                    if name in names
                ],
                kk_results=[
                    result
                    for name, result in self.kk_results.items()
                    if name in names
                ],
            )
        except (OSError, ValueError) as exc:
            logger.exception("Falha ao exportar Excel.")
            QMessageBox.critical(
                self,
                "Exportar Excel",
                f"Não foi possível exportar:\n{exc}",
            )
            return
        self.show_status(f"Excel exportado: {path}")

    def _export_csv(self) -> None:
        """Exporta as amostras marcadas (FRA + I-V) para CSV.

        O CSV é autocontido: guarda tanto o espectro FRA quanto a curva
        I-V de cada amostra (coluna ``Tipo``), permitindo restaurar a
        sessão inteira ao reimportar.
        """
        measurements = self.checked_measurements()
        iv_curves = self.checked_iv_curves()
        if not measurements and not iv_curves:
            QMessageBox.information(
                self,
                "Exportar CSV",
                "Marque ao menos uma amostra (com FRA ou curva I-V) na "
                "lista lateral.",
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar CSV",
            "amostras_fra.csv",
            "Arquivo CSV (*.csv)",
        )
        if not path:
            return
        try:
            exportacao.export_measurements_csv(
                measurements, path, iv_curves=iv_curves
            )
        except (OSError, ValueError) as exc:
            logger.exception("Falha ao exportar CSV.")
            QMessageBox.critical(
                self,
                "Exportar CSV",
                f"Não foi possível exportar:\n{exc}",
            )
            return
        self.show_status(
            f"CSV exportado: {path} "
            f"({len(measurements)} FRA, {len(iv_curves)} I-V)."
        )

    # -- Projeto (sessão completa) ---------------------------------------
    def _collect_project_data(self) -> "projeto.ProjectData":
        """Reúne o estado atual da sessão para salvar em projeto."""
        checked = [
            self.measurement_list.item(i).text()
            for i in range(self.measurement_list.count())
            if self.measurement_list.item(i).checkState()
            == Qt.CheckState.Checked
        ]
        return projeto.ProjectData(
            samples=self.sample_names(),
            checked=checked,
            measurements=dict(self.measurements),
            iv_curves=dict(self.iv_curves),
            curve_colors=dict(self.curve_colors),
            corrections=dict(self.corrections),
            fit_results=dict(self.fit_results),
            iv_fit_results=dict(self.iv_fit_results),
            kk_results=dict(self.kk_results),
        )

    def _save_project(self) -> None:
        """Salva a sessão inteira em um arquivo de projeto (.fra)."""
        if not self.measurements and not self.iv_curves:
            QMessageBox.information(
                self,
                "Salvar projeto",
                "Não há nada para salvar. Adicione medições ou curvas "
                "I-V primeiro.",
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar projeto",
            f"projeto{projeto.PROJECT_SUFFIX}",
            f"Projeto AMOSTRAS FRA (*{projeto.PROJECT_SUFFIX})",
        )
        if not path:
            return
        if not path.lower().endswith(projeto.PROJECT_SUFFIX):
            path += projeto.PROJECT_SUFFIX
        try:
            projeto.save_project(path, self._collect_project_data())
        except (OSError, ValueError) as exc:
            logger.exception("Falha ao salvar projeto.")
            QMessageBox.critical(
                self,
                "Salvar projeto",
                f"Não foi possível salvar:\n{exc}",
            )
            return
        self.show_status(f"Projeto salvo: {path}")

    def _open_project(self) -> None:
        """Abre um projeto (.fra), restaurando a sessão completa."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir projeto",
            "",
            f"Projeto AMOSTRAS FRA (*{projeto.PROJECT_SUFFIX});;"
            "Todos os arquivos (*)",
        )
        if not path:
            return
        try:
            data = projeto.load_project(path)
        except (OSError, ValueError) as exc:
            logger.exception("Falha ao abrir projeto.")
            QMessageBox.critical(
                self,
                "Abrir projeto",
                f"Não foi possível abrir:\n{exc}",
            )
            return
        if self.measurements or self.iv_curves:
            answer = QMessageBox.question(
                self,
                "Abrir projeto",
                "Abrir o projeto substitui a sessão atual — medições, "
                "curvas e ajustes não salvos serão perdidos. Continuar?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._apply_project_data(data)
        self.show_status(
            f"Projeto aberto: {path} "
            f"({len(data.measurements)} FRA, {len(data.iv_curves)} I-V)."
        )

    def _reset_session(self) -> None:
        """Limpa toda a sessão (dados, listas e resultados)."""
        self.measurements.clear()
        self.iv_curves.clear()
        self.corrections.clear()
        self.fit_results.clear()
        self.iv_fit_results.clear()
        self.kk_results.clear()
        self.curve_colors.clear()
        self.measurement_list.blockSignals(True)
        try:
            self.measurement_list.clear()
        finally:
            self.measurement_list.blockSignals(False)

    def _apply_project_data(self, data: "projeto.ProjectData") -> None:
        """Substitui a sessão atual pelo conteúdo de um projeto."""
        self._reset_session()
        self.measurements.update(data.measurements)
        self.iv_curves.update(data.iv_curves)
        self.corrections.update(data.corrections)
        self.fit_results.update(data.fit_results)
        self.iv_fit_results.update(data.iv_fit_results)
        self.kk_results.update(data.kk_results)
        self.curve_colors.update(data.curve_colors)

        ordered = list(data.samples)
        for name in list(data.measurements) + list(data.iv_curves):
            if name not in ordered:
                ordered.append(name)
        checked = set(data.checked)
        for name in ordered:
            self._ensure_sample_item(name, checked=name in checked)
            self.update_sample_tooltip(name)

        self._apply_list_item_colors()
        self._sync_measurement_widgets()
        self.data_panel.refresh_corrections()
        self.refresh_plots()
        self.iv_tab.refresh()

    def _current_canvas(self) -> Optional[PlotCanvas]:
        """Canvas da aba atualmente visível (ou None)."""
        widget = self.tabs.currentWidget()
        if isinstance(widget, PlotCanvas):
            return widget
        if isinstance(widget, (KKTab, CircuitTab, ComparisonTab)):
            return widget.canvas
        return None

    def _export_image(self) -> None:
        """Exporta a figura da aba atual para PNG/PDF/SVG."""
        canvas = self._current_canvas()
        if canvas is None:
            QMessageBox.information(
                self,
                "Exportar imagem",
                "Abra uma aba de gráfico para exportar a imagem.",
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar imagem",
            "grafico.png",
            "Imagem PNG (*.png);;Documento PDF (*.pdf);;"
            "Imagem SVG (*.svg)",
        )
        if not path:
            return
        try:
            exportacao.export_figure(canvas.figure, path)
        except (OSError, ValueError) as exc:
            logger.exception("Falha ao exportar imagem.")
            QMessageBox.critical(
                self,
                "Exportar imagem",
                f"Não foi possível exportar:\n{exc}",
            )
            return
        self.show_status(f"Imagem exportada: {path}")

    def _generate_report(self) -> None:
        """Gera o relatório PDF completo das medições marcadas."""
        measurements = self._measurements_for_export()
        if not measurements:
            return
        dialog = ReportDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Gerar relatório PDF",
            "relatorio_amostras_fra.pdf",
            "Documento PDF (*.pdf)",
        )
        if not path:
            return
        names = {m.name for m in measurements}
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            exportacao.generate_pdf_report(
                path,
                measurements,
                kk_results=[
                    result
                    for name, result in self.kk_results.items()
                    if name in names
                ],
                fit_results=[
                    fit
                    for name, fit in self.fit_results.items()
                    if name in names
                ],
                corrections=list(self.corrections.values()),
                observations=dialog.observations(),
            )
        except (OSError, ValueError) as exc:
            logger.exception("Falha ao gerar relatório PDF.")
            QMessageBox.critical(
                self,
                "Relatório PDF",
                f"Não foi possível gerar o relatório:\n{exc}",
            )
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.show_status(f"Relatório PDF gerado: {path}")

    # -- Criador de gráficos --------------------------------------------------
    def _open_chart_builder(self) -> None:
        """Abre uma nova janela do criador de gráficos."""
        dialog = ChartBuilderDialog(
            self, lambda: self.measurements, lambda: self.iv_curves
        )
        self._chart_dialogs.append(dialog)
        dialog.finished.connect(
            lambda _result, d=dialog: self._chart_dialogs.remove(d)
            if d in self._chart_dialogs
            else None
        )
        dialog.show()
        dialog.raise_()

    # -- Simulação ---------------------------------------------------------------
    def _open_simulation(self) -> None:
        """Abre (ou traz à frente) a janela de simulação do módulo."""
        if self._simulation_dialog is None:
            self._simulation_dialog = PVSimulationDialog(self)
        self._simulation_dialog.show()
        self._simulation_dialog.raise_()
        self._simulation_dialog.activateWindow()

    # -- Conexão serial --------------------------------------------------------
    def _open_serial_dialog(self) -> None:
        """Pergunta o tipo de dispositivo e abre a janela serial."""
        options = (
            "Dispositivo genérico (porta COM)",
            "AD5933 — analisador de impedância (via ESP32)",
        )
        current = 1 if (
            self._serial_dialog is not None
            and self._serial_dialog.mode == "ad5933"
        ) else 0
        choice, ok = QInputDialog.getItem(
            self,
            "Conexão Serial",
            "Qual dispositivo será conectado?",
            list(options),
            current,
            False,
        )
        if not ok:
            return
        mode = "ad5933" if choice == options[1] else "generico"
        # Recria a janela se o tipo de dispositivo mudou.
        if (
            self._serial_dialog is not None
            and self._serial_dialog.mode != mode
        ):
            self._serial_dialog.close()
            self._serial_dialog.deleteLater()
            self._serial_dialog = None
        if self._serial_dialog is None:
            self._serial_dialog = SerialDialog(self, mode=mode)
            self._serial_dialog.measurementCreated.connect(
                self.add_measurement
            )
            self._serial_dialog.rowsToTable.connect(
                self._serial_rows_to_table
            )
        self._serial_dialog.refresh_ports()
        self._serial_dialog.show()
        self._serial_dialog.raise_()
        self._serial_dialog.activateWindow()

    def _serial_rows_to_table(
        self, rows: list[list[Optional[float]]]
    ) -> None:
        """Preenche a tabela de dados com pontos recebidos pela serial."""
        self.data_panel.table.set_rows(rows)
        self.tabs.setCurrentWidget(self.data_panel)
        self.show_status(
            f"{len(rows)} ponto(s) da serial carregados na tabela de "
            "dados."
        )

    # -- Ajuda -----------------------------------------------------------------
    def _open_help(self) -> None:
        """Abre (ou traz à frente) o Guia do usuário (F1)."""
        if getattr(self, "_help_dialog", None) is None:
            self._help_dialog = ajuda.HelpDialog(self)
        self._help_dialog.show()
        self._help_dialog.raise_()
        self._help_dialog.activateWindow()

    def _show_about(self) -> None:
        """Exibe a janela "Sobre"."""
        QMessageBox.about(
            self,
            f"Sobre — {util.APP_NAME}",
            f"<h3>{util.APP_NAME}</h3>"
            f"<p>Versão {util.APP_VERSION}</p>"
            "<p>Software científico de Espectroscopia de Impedância "
            "(EIS/FRA) para detecção e classificação de falhas em "
            "módulos fotovoltaicos.</p>"
            "<p>Recursos: entrada de dados tipo Excel, curvas I-V, "
            "diagramas de Nyquist e Bode, validação de "
            "Kramers-Kronig, correção do instrumento, ajuste de "
            "circuitos equivalentes (impedance.py), criador de "
            "gráficos, simulação do módulo FV e relatórios em "
            "PDF.</p>"
            "<p><b>Software sem fins lucrativos, desenvolvido pelo "
            "Eng. Leones Moura dos Santos.</b></p>",
        )
