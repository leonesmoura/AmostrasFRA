"""Simulação didática do módulo fotovoltaico (AMOSTRAS FRA 2.0).

Janela com duas visualizações animadas:

1. **Módulo (corte transversal)** — camadas do módulo com fótons,
   pares elétron-lacuna e o percurso dos portadores pelo circuito
   externo, com a correspondência física ↔ circuito equivalente
   (fótons → ``I_ph``; junção → ``D ∥ C ∥ Rp``; metalização/cabos →
   ``Rs``).  Tecnologias disponíveis:

   * Silício tipo p (PERC/Al-BSF) — emissor n⁺ frontal; elétrons
     coletados na frente;
   * Silício tipo n (TOPCon) — emissor p⁺ frontal; lacunas coletadas
     na frente e elétrons no contato traseiro (fluxo invertido);
   * Perovskita — vidro/TCO/ETL/perovskita/HTL/eletrodo de ouro, sem
     fingers (coleta pelo TCO);
   * CdTe (filme fino) — vidro/TCO/CdS/CdTe/contato traseiro.

2. **Modelo atômico do silício** — rede cristalina 2-D com ligações
   covalentes animadas, um átomo de fósforo (doador, dopagem tipo n)
   com seu 5º elétron livre vagando pela rede e um átomo de boro
   (aceitador, dopagem tipo p) com a lacuna saltando entre ligações
   vizinhas.

Toda a geometria é definida em um canvas virtual de 1000 × 640 e
escalada para o tamanho real do widget, preservando a proporção.
"""

from __future__ import annotations

import logging
import math
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

#: Dimensões do canvas virtual.
_VW: float = 1000.0
_VH: float = 640.0

# -- Geometria comum do módulo (coordenadas virtuais) ------------------------
_MOD_LEFT: float = 60.0
_MOD_RIGHT: float = 640.0
_MOD_TOP: float = 90.0
_MOD_BOTTOM: float = 470.0

#: Posições x centrais dos fingers e sua meia-largura.
_FINGER_XS: tuple[float, ...] = (110.0, 190.0, 270.0, 350.0, 430.0,
                                 510.0, 590.0)
_FINGER_HALF_W: float = 5.0

# -- Circuito externo ---------------------------------------------------------
_WIRE_X: float = 880.0
_RS_X1: float = 730.0
_RS_X2: float = 810.0
_LOAD_Y1: float = 245.0
_LOAD_Y2: float = 295.0

# -- Cores ---------------------------------------------------------------------
_COLOR_GLASS = QColor(127, 179, 213, 100)
_COLOR_EVA = QColor(247, 220, 111, 55)
_COLOR_BACK = QColor(149, 165, 166)
_COLOR_BACKSHEET = QColor(208, 211, 212)
_COLOR_FRAME = QColor(128, 139, 150)
_COLOR_METAL = QColor(213, 216, 220)
_COLOR_WIRE = QColor(190, 190, 190)
_COLOR_PHOTON = QColor(255, 214, 10)
_COLOR_ELECTRON = QColor(0, 229, 255)
_COLOR_HOLE = QColor(255, 99, 71)
_COLOR_RS = QColor(230, 126, 34)
_COLOR_JUNCTION = QColor(0, 229, 255)
_COLOR_TEXT = QColor(212, 212, 212)
_COLOR_SUN = QColor(255, 196, 0)


@dataclass(frozen=True)
class LayerSpec:
    """Camada do corte do módulo.

    Attributes:
        label: Rótulo exibido dentro da camada.
        y1: Topo da camada (coordenadas virtuais).
        y2: Base da camada.
        color: Cor de preenchimento.
        dark_text: Usa texto escuro (camadas claras).
    """

    label: str
    y1: float
    y2: float
    color: QColor
    dark_text: bool = False


@dataclass(frozen=True)
class ModuleTech:
    """Tecnologia de módulo fotovoltaico simulada.

    Attributes:
        key: Identificador interno.
        display_name: Nome exibido no seletor.
        layers: Pilha de camadas, do topo para a base.
        absorber: Faixa ``(y1, y2)`` onde os fótons geram pares.
        junction: Faixa ``(y1, y2)`` destacada como junção
            (``D ∥ C ∥ Rp``).
        collect_y: Nível (y) de coleta frontal (fita/busbar ou TCO).
        entry_y: Nível (y) logo abaixo da coleta frontal (emissor/ETL).
        back_y: Nível (y) do contato traseiro.
        has_fingers: Desenha fingers/busbar de prata na frente.
        electrons_to_front: ``True`` quando os elétrons são coletados
            na frente (tipo p, perovskita, CdTe); ``False`` quando são
            coletados no contato traseiro (tipo n/TOPCon).
        junction_label: Texto do mapeamento da junção.
        rs_label: Texto do mapeamento de ``Rs``.
        description: Linha explicativa exibida sob o seletor.
    """

    key: str
    display_name: str
    layers: tuple[LayerSpec, ...]
    absorber: tuple[float, float]
    junction: tuple[float, float]
    collect_y: float
    entry_y: float
    back_y: float
    has_fingers: bool
    electrons_to_front: bool
    junction_label: str
    rs_label: str
    description: str


#: Tecnologias disponíveis na simulação.
TECHNOLOGIES: dict[str, ModuleTech] = {
    "p_si": ModuleTech(
        key="p_si",
        display_name="Silício tipo p (PERC/Al-BSF)",
        layers=(
            LayerSpec("Vidro", 90.0, 150.0, _COLOR_GLASS),
            LayerSpec("EVA", 150.0, 195.0, _COLOR_EVA),
            LayerSpec("Emissor n⁺ (fósforo)", 195.0, 215.0,
                      QColor(74, 144, 217)),
            LayerSpec("Base p (silício + boro)", 215.0, 355.0,
                      QColor(31, 58, 95)),
            LayerSpec("Contato traseiro (Al)", 355.0, 375.0,
                      _COLOR_BACK),
            LayerSpec("EVA", 375.0, 420.0, _COLOR_EVA),
            LayerSpec("Backsheet", 420.0, 470.0, _COLOR_BACKSHEET,
                      dark_text=True),
        ),
        absorber=(227.0, 340.0),
        junction=(195.0, 375.0),
        collect_y=172.0,
        entry_y=205.0,
        back_y=365.0,
        has_fingers=True,
        electrons_to_front=True,
        junction_label="Junção p-n  →  D ∥ C ∥ Rp",
        rs_label="metalização + cabos → Rs",
        description=(
            "Base dopada com boro (tipo p) e emissor n⁺ de fósforo na "
            "face frontal: os elétrons são coletados pelos fingers na "
            "frente."
        ),
    ),
    "n_si": ModuleTech(
        key="n_si",
        display_name="Silício tipo n (TOPCon)",
        layers=(
            LayerSpec("Vidro", 90.0, 150.0, _COLOR_GLASS),
            LayerSpec("EVA", 150.0, 195.0, _COLOR_EVA),
            LayerSpec("Emissor p⁺ (boro)", 195.0, 215.0,
                      QColor(176, 106, 90)),
            LayerSpec("Base n (silício + fósforo)", 215.0, 345.0,
                      QColor(30, 84, 92)),
            LayerSpec("TOPCon: óxido fino + poli-Si n⁺", 345.0, 362.0,
                      QColor(111, 168, 184)),
            LayerSpec("Contato traseiro (Ag)", 362.0, 378.0,
                      _COLOR_BACK),
            LayerSpec("EVA", 378.0, 420.0, _COLOR_EVA),
            LayerSpec("Backsheet", 420.0, 470.0, _COLOR_BACKSHEET,
                      dark_text=True),
        ),
        absorber=(227.0, 332.0),
        junction=(195.0, 345.0),
        collect_y=172.0,
        entry_y=205.0,
        back_y=370.0,
        has_fingers=True,
        electrons_to_front=False,
        junction_label="Junção p⁺-n  →  D ∥ C ∥ Rp",
        rs_label="metalização + cabos → Rs",
        description=(
            "Base dopada com fósforo (tipo n) e emissor p⁺ de boro na "
            "frente: as LACUNAS são coletadas pelos fingers e os "
            "elétrons saem pelo contato traseiro (fluxo invertido)."
        ),
    ),
    "perovskita": ModuleTech(
        key="perovskita",
        display_name="Perovskita (filme fino)",
        layers=(
            LayerSpec("Vidro", 90.0, 150.0, _COLOR_GLASS),
            LayerSpec("TCO (ITO/FTO)", 150.0, 172.0,
                      QColor(159, 211, 199, 170)),
            LayerSpec("ETL (SnO₂/TiO₂)", 172.0, 195.0,
                      QColor(127, 179, 213)),
            LayerSpec("Perovskita (absorvedor)", 195.0, 330.0,
                      QColor(122, 74, 43)),
            LayerSpec("HTL (Spiro-OMeTAD)", 330.0, 355.0,
                      QColor(122, 79, 122)),
            LayerSpec("Eletrodo (Au)", 355.0, 375.0,
                      QColor(201, 162, 39)),
            LayerSpec("Encapsulante", 375.0, 420.0, _COLOR_EVA),
            LayerSpec("Vidro traseiro", 420.0, 470.0, _COLOR_GLASS),
        ),
        absorber=(207.0, 318.0),
        junction=(172.0, 355.0),
        collect_y=161.0,
        entry_y=184.0,
        back_y=365.0,
        has_fingers=False,
        electrons_to_front=True,
        junction_label="Perovskita + interfaces ETL/HTL → D ∥ C ∥ Rp",
        rs_label="TCO + cabos → Rs",
        description=(
            "Célula de perovskita: o TCO transparente coleta os "
            "elétrons (via ETL) na frente, sem fingers; as lacunas "
            "saem pelo HTL até o eletrodo de ouro."
        ),
    ),
    "cdte": ModuleTech(
        key="cdte",
        display_name="CdTe (filme fino)",
        layers=(
            LayerSpec("Vidro", 90.0, 150.0, _COLOR_GLASS),
            LayerSpec("TCO", 150.0, 172.0,
                      QColor(159, 211, 199, 170)),
            LayerSpec("CdS (janela, tipo n)", 172.0, 195.0,
                      QColor(184, 184, 66)),
            LayerSpec("CdTe (absorvedor, tipo p)", 195.0, 340.0,
                      QColor(59, 74, 107)),
            LayerSpec("Contato traseiro (Cu/Mo)", 340.0, 375.0,
                      QColor(96, 106, 116)),
            LayerSpec("Encapsulante", 375.0, 420.0, _COLOR_EVA),
            LayerSpec("Vidro traseiro", 420.0, 470.0, _COLOR_GLASS),
        ),
        absorber=(207.0, 328.0),
        junction=(172.0, 340.0),
        collect_y=161.0,
        entry_y=184.0,
        back_y=357.0,
        has_fingers=False,
        electrons_to_front=True,
        junction_label="Heterojunção CdS/CdTe → D ∥ C ∥ Rp",
        rs_label="TCO + cabos → Rs",
        description=(
            "Filme fino de CdTe: heterojunção com a janela de CdS "
            "(tipo n); elétrons coletados pelo TCO frontal e lacunas "
            "pelo contato traseiro."
        ),
    ),
}


@dataclass
class _Particle:
    """Partícula animada (fóton, elétron ou lacuna).

    Attributes:
        kind: ``"photon"``, ``"electron"`` ou ``"hole"``.
        x: Posição x atual (coordenadas virtuais).
        y: Posição y atual.
        waypoints: Pontos a percorrer, em ordem.
        speed: Velocidade base, em unidades virtuais por quadro.
        counted: Se o elétron já foi contado no medidor de corrente.
    """

    kind: str
    x: float
    y: float
    waypoints: list[tuple[float, float]] = field(default_factory=list)
    speed: float = 2.0
    counted: bool = False

    def advance(self, factor: float) -> bool:
        """Move a partícula rumo ao próximo waypoint.

        Args:
            factor: Multiplicador de velocidade.

        Returns:
            ``True`` se ainda há caminho a percorrer; ``False`` quando
            todos os waypoints foram atingidos.
        """
        step = self.speed * factor
        while self.waypoints and step > 0.0:
            tx, ty = self.waypoints[0]
            dx = tx - self.x
            dy = ty - self.y
            distance = (dx * dx + dy * dy) ** 0.5
            if distance <= step:
                self.x, self.y = tx, ty
                self.waypoints.pop(0)
                step -= distance
            else:
                self.x += dx / distance * step
                self.y += dy / distance * step
                step = 0.0
        return bool(self.waypoints)


class PVSimulationWidget(QWidget):
    """Canvas animado do corte do módulo fotovoltaico."""

    _TICK_MS: int = 30
    _MAX_PHOTONS: int = 50
    _MAX_ELECTRONS: int = 140

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(760, 480)
        self._tech: ModuleTech = TECHNOLOGIES["p_si"]
        self._photons: list[_Particle] = []
        self._electrons: list[_Particle] = []
        self._holes: list[_Particle] = []
        self._irradiance: int = 20          # fótons/segundo
        self._speed_factor: float = 1.0
        self._show_mapping: bool = True
        self._spawn_accumulator: float = 0.0
        self._crossings: deque[float] = deque(maxlen=400)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)

    # -- Controles ----------------------------------------------------------
    def set_technology(self, key: str) -> None:
        """Troca a tecnologia do módulo simulado.

        Args:
            key: Chave de :data:`TECHNOLOGIES`.

        Raises:
            KeyError: Se a tecnologia não existir.
        """
        self._tech = TECHNOLOGIES[key]
        self._photons.clear()
        self._electrons.clear()
        self._holes.clear()
        self._crossings.clear()
        self._spawn_accumulator = 0.0
        logger.info(
            "Simulação FV: tecnologia alterada para '%s'.",
            self._tech.display_name,
        )
        self.update()

    @property
    def technology(self) -> ModuleTech:
        """Tecnologia atualmente simulada."""
        return self._tech

    def set_irradiance(self, photons_per_second: int) -> None:
        """Define a taxa de fótons (irradiância)."""
        self._irradiance = max(0, int(photons_per_second))

    def set_speed_factor(self, factor: float) -> None:
        """Define o multiplicador de velocidade da animação."""
        self._speed_factor = max(0.1, float(factor))

    def set_show_mapping(self, show: bool) -> None:
        """Exibe/oculta a correspondência com o circuito equivalente."""
        self._show_mapping = bool(show)
        self.update()

    def start(self) -> None:
        """Inicia a animação."""
        if not self._timer.isActive():
            self._timer.start(self._TICK_MS)
            logger.debug("Simulação FV iniciada.")

    def stop(self) -> None:
        """Pausa a animação."""
        self._timer.stop()

    @property
    def running(self) -> bool:
        """Indica se a animação está em execução."""
        return self._timer.isActive()

    def electrons_per_second(self) -> float:
        """Elétrons que atravessaram o circuito externo por segundo."""
        now = time.monotonic()
        while self._crossings and now - self._crossings[0] > 1.0:
            self._crossings.popleft()
        return float(len(self._crossings))

    # -- Ciclo de vida -----------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 (API Qt)
        """Inicia a animação quando a janela aparece."""
        super().showEvent(event)
        self.start()

    def hideEvent(self, event) -> None:  # noqa: N802 (API Qt)
        """Pausa a animação quando a janela é ocultada."""
        self.stop()
        super().hideEvent(event)

    # -- Física simplificada -------------------------------------------------
    def _nearest_finger(self, x: float) -> float:
        """Posição x do finger mais próximo."""
        return min(_FINGER_XS, key=lambda fx: abs(fx - x))

    def _spawn_photon(self) -> None:
        """Cria um fóton vindo do sol até um ponto do absorvedor."""
        tech = self._tech
        x = random.uniform(_MOD_LEFT + 25.0, _MOD_RIGHT - 25.0)
        depth = random.uniform(*tech.absorber)
        self._photons.append(
            _Particle(
                kind="photon",
                x=x,
                y=58.0,
                waypoints=[(x, depth)],
                speed=6.5,
            )
        )

    def _spawn_pair(self, x: float, y: float) -> None:
        """Gera o par elétron-lacuna no ponto de absorção do fóton."""
        if len(self._electrons) >= self._MAX_ELECTRONS:
            return
        tech = self._tech
        front_x = self._nearest_finger(x) if tech.has_fingers else x
        recombine_x = random.uniform(_MOD_LEFT + 40.0, _MOD_RIGHT - 40.0)

        if tech.electrons_to_front:
            electron_waypoints = [
                (x, tech.entry_y),                 # deriva até a frente
                (front_x, tech.entry_y),           # difusão lateral
                (front_x, tech.collect_y),         # coleta frontal
                (_RS_X1, tech.collect_y),          # fita/TCO
                (_WIRE_X, tech.collect_y),         # passa por Rs
                (_WIRE_X, tech.back_y),            # desce pela carga
                (_MOD_RIGHT + 6.0, tech.back_y),   # retorna ao módulo
                (recombine_x, tech.back_y),        # contato traseiro
            ]
            hole_waypoints = [(x, tech.back_y)]
        else:
            # Tipo n (TOPCon): elétrons saem pelo contato traseiro e
            # retornam pela frente; lacunas coletadas nos fingers.
            electron_waypoints = [
                (x, tech.back_y),                  # deriva para trás
                (_MOD_RIGHT + 6.0, tech.back_y),   # sai pelo traseiro
                (_WIRE_X, tech.back_y),            # cabo inferior
                (_WIRE_X, tech.collect_y),         # sobe pela carga
                (_RS_X2, tech.collect_y),          # passa por Rs
                (_MOD_RIGHT, tech.collect_y),      # entra pela frente
                (front_x, tech.collect_y),         # fita/busbar
                (front_x, tech.entry_y),           # recombina na frente
            ]
            hole_waypoints = [
                (x, tech.entry_y),
                (front_x, tech.entry_y),
                (front_x, tech.collect_y),
            ]

        self._electrons.append(
            _Particle(
                kind="electron",
                x=x,
                y=y,
                waypoints=electron_waypoints,
                speed=2.4,
            )
        )
        self._holes.append(
            _Particle(
                kind="hole",
                x=x,
                y=y,
                waypoints=hole_waypoints,
                speed=1.4,
            )
        )

    def _advance(self) -> None:
        """Avança um quadro da simulação."""
        factor = self._speed_factor
        # Nascimento de fótons conforme a irradiância.
        self._spawn_accumulator += (
            self._irradiance * self._TICK_MS / 1000.0
        ) * factor
        while (
            self._spawn_accumulator >= 1.0
            and len(self._photons) < self._MAX_PHOTONS
        ):
            self._spawn_photon()
            self._spawn_accumulator -= 1.0

        survivors: list[_Particle] = []
        for photon in self._photons:
            if photon.advance(factor):
                survivors.append(photon)
            else:
                self._spawn_pair(photon.x, photon.y)
        self._photons = survivors

        now = time.monotonic()
        survivors = []
        for electron in self._electrons:
            alive = electron.advance(factor)
            if not electron.counted and electron.x >= _RS_X2:
                electron.counted = True
                self._crossings.append(now)
            if alive:
                survivors.append(electron)
        self._electrons = survivors

        self._holes = [h for h in self._holes if h.advance(factor)]
        self.update()

    # -- Desenho ---------------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802 (API Qt)
        """Desenha o módulo, o circuito externo e as partículas."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(24, 24, 24))

        scale = min(self.width() / _VW, self.height() / _VH)
        painter.translate(
            (self.width() - _VW * scale) / 2.0,
            (self.height() - _VH * scale) / 2.0,
        )
        painter.scale(scale, scale)

        self._draw_sun(painter)
        self._draw_module(painter)
        self._draw_external_circuit(painter)
        if self._show_mapping:
            self._draw_mapping(painter)
        self._draw_particles(painter)
        self._draw_legend(painter)

    def _draw_sun(self, painter: QPainter) -> None:
        painter.setPen(QPen(_COLOR_SUN, 2.0))
        painter.setBrush(_COLOR_SUN)
        painter.drawEllipse(QPointF(90.0, 40.0), 16.0, 16.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for dx, dy in ((-30, 0), (30, 0), (0, -26), (22, -20),
                       (-22, -20), (24, 18), (-24, 18)):
            painter.drawLine(
                QPointF(90.0 + dx * 0.72, 40.0 + dy * 0.72),
                QPointF(90.0 + dx, 40.0 + dy),
            )

    def _draw_module(self, painter: QPainter) -> None:
        tech = self._tech
        font = painter.font()
        font.setPointSizeF(9.0)
        painter.setFont(font)

        for layer in tech.layers:
            rect = QRectF(
                _MOD_LEFT, layer.y1,
                _MOD_RIGHT - _MOD_LEFT, layer.y2 - layer.y1,
            )
            painter.fillRect(rect, layer.color)
            painter.setPen(
                QPen(QColor(60, 60, 60) if layer.dark_text
                     else _COLOR_TEXT)
            )
            painter.drawText(
                QRectF(_MOD_LEFT + 8.0, layer.y1, 300.0,
                       layer.y2 - layer.y1),
                Qt.AlignmentFlag.AlignVCenter,
                layer.label,
            )

        # Linha da junção (interface superior do absorvedor).
        painter.setPen(QPen(QColor(255, 255, 255, 130), 1.0,
                            Qt.PenStyle.DashLine))
        painter.drawLine(
            QPointF(_MOD_LEFT, tech.junction[0] + 20.0),
            QPointF(_MOD_RIGHT, tech.junction[0] + 20.0),
        )

        if tech.has_fingers:
            # Fingers de prata + fita coletora (busbar).
            painter.setPen(QPen(_COLOR_METAL, 1.0))
            painter.setBrush(_COLOR_METAL)
            for fx in _FINGER_XS:
                painter.drawRect(
                    QRectF(
                        fx - _FINGER_HALF_W,
                        tech.collect_y,
                        2 * _FINGER_HALF_W,
                        tech.entry_y - 10.0 - tech.collect_y + 3.0,
                    )
                )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(_COLOR_METAL, 3.0))
            painter.drawLine(
                QPointF(_FINGER_XS[0] - 12.0, tech.collect_y),
                QPointF(_MOD_RIGHT, tech.collect_y),
            )
            painter.setPen(QPen(_COLOR_TEXT))
            painter.drawText(QPointF(228.0, 122.0), "fingers / busbar")
            painter.setPen(QPen(_COLOR_METAL, 1.0))
            painter.drawLine(
                QPointF(288.0, 128.0),
                QPointF(270.0, tech.collect_y - 6.0),
            )

        # Moldura do módulo.
        painter.setPen(QPen(_COLOR_FRAME, 2.5))
        painter.drawRect(
            QRectF(
                _MOD_LEFT - 6.0,
                _MOD_TOP - 6.0,
                _MOD_RIGHT - _MOD_LEFT + 12.0,
                _MOD_BOTTOM - _MOD_TOP + 12.0,
            )
        )

    def _draw_external_circuit(self, painter: QPainter) -> None:
        tech = self._tech
        pen = QPen(_COLOR_WIRE, 2.0)
        painter.setPen(pen)
        # Frente → Rs → descida → carga → contato traseiro.
        painter.drawLine(
            QPointF(_MOD_RIGHT, tech.collect_y),
            QPointF(_RS_X1, tech.collect_y),
        )
        self._draw_resistor_h(painter, _RS_X1, _RS_X2, tech.collect_y)
        painter.drawLine(
            QPointF(_RS_X2, tech.collect_y),
            QPointF(_WIRE_X, tech.collect_y),
        )
        painter.drawLine(
            QPointF(_WIRE_X, tech.collect_y),
            QPointF(_WIRE_X, _LOAD_Y1),
        )
        painter.drawRect(
            QRectF(_WIRE_X - 22.0, _LOAD_Y1, 44.0, _LOAD_Y2 - _LOAD_Y1)
        )
        painter.drawLine(
            QPointF(_WIRE_X, _LOAD_Y2), QPointF(_WIRE_X, tech.back_y)
        )
        painter.drawLine(
            QPointF(_WIRE_X, tech.back_y),
            QPointF(_MOD_RIGHT, tech.back_y),
        )
        painter.setPen(QPen(_COLOR_TEXT))
        painter.drawText(
            QRectF(_WIRE_X - 22.0, _LOAD_Y1, 44.0, _LOAD_Y2 - _LOAD_Y1),
            Qt.AlignmentFlag.AlignCenter,
            "Carga",
        )

    def _draw_resistor_h(
        self, painter: QPainter, x1: float, x2: float, y: float
    ) -> None:
        """Resistor em zigue-zague horizontal (símbolo de Rs)."""
        segments = 6
        amplitude = 8.0
        lead = 8.0
        points = [QPointF(x1, y), QPointF(x1 + lead, y)]
        seg_w = (x2 - x1 - 2 * lead) / segments
        for i in range(segments):
            px = x1 + lead + seg_w * (i + 0.5)
            py = y + (amplitude if i % 2 else -amplitude)
            points.append(QPointF(px, py))
        points.append(QPointF(x2 - lead, y))
        points.append(QPointF(x2, y))
        painter.setPen(QPen(_COLOR_RS, 2.2))
        painter.drawPolyline(points)
        painter.setPen(QPen(_COLOR_RS))
        painter.drawText(
            QPointF((x1 + x2) / 2.0 - 10.0, y - 14.0), "Rs"
        )
        painter.setPen(QPen(_COLOR_WIRE, 2.0))

    def _draw_mapping(self, painter: QPainter) -> None:
        """Realces da correspondência com o circuito equivalente."""
        tech = self._tech
        # Junção → D ∥ C ∥ Rp.
        pen = QPen(_COLOR_JUNCTION, 1.6, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(
            QRectF(
                _MOD_LEFT + 2.0,
                tech.junction[0],
                _MOD_RIGHT - _MOD_LEFT - 4.0,
                tech.junction[1] - tech.junction[0],
            )
        )
        painter.drawText(
            QRectF(
                _MOD_LEFT,
                (tech.junction[0] + tech.junction[1]) / 2.0 + 18.0,
                _MOD_RIGHT - _MOD_LEFT,
                24.0,
            ),
            Qt.AlignmentFlag.AlignCenter,
            tech.junction_label,
        )
        # Fótons → I_ph.
        painter.setPen(QPen(_COLOR_SUN, 1.6))
        painter.drawText(QPointF(660.0, 108.0), "Fótons → I_ph")
        # Metalização/TCO → Rs.
        painter.setPen(QPen(_COLOR_RS, 1.4, Qt.PenStyle.DashLine))
        painter.drawRect(
            QRectF(
                _MOD_LEFT + 20.0,
                tech.collect_y - 12.0,
                _MOD_RIGHT - _MOD_LEFT + 12.0,
                34.0,
            )
        )
        painter.setPen(QPen(_COLOR_RS))
        painter.drawText(
            QPointF(826.0, tech.collect_y - 26.0), tech.rs_label
        )

    def _draw_particles(self, painter: QPainter) -> None:
        # Fótons: cometas amarelos.
        painter.setPen(QPen(_COLOR_PHOTON, 2.0))
        for photon in self._photons:
            painter.drawLine(
                QPointF(photon.x, photon.y - 12.0),
                QPointF(photon.x, photon.y),
            )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_COLOR_PHOTON)
        for photon in self._photons:
            painter.drawEllipse(QPointF(photon.x, photon.y), 2.6, 2.6)

        # Lacunas (vermelho) e elétrons (ciano) com halo.
        painter.setBrush(QColor(255, 99, 71, 70))
        for hole in self._holes:
            painter.drawEllipse(QPointF(hole.x, hole.y), 5.0, 5.0)
        painter.setBrush(_COLOR_HOLE)
        for hole in self._holes:
            painter.drawEllipse(QPointF(hole.x, hole.y), 2.6, 2.6)

        painter.setBrush(QColor(0, 229, 255, 60))
        for electron in self._electrons:
            painter.drawEllipse(
                QPointF(electron.x, electron.y), 5.4, 5.4
            )
        painter.setBrush(_COLOR_ELECTRON)
        for electron in self._electrons:
            painter.drawEllipse(
                QPointF(electron.x, electron.y), 2.8, 2.8
            )
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_legend(self, painter: QPainter) -> None:
        tech = self._tech
        font = painter.font()
        font.setPointSizeF(9.0)
        painter.setFont(font)
        if tech.electrons_to_front:
            electron_text = (
                "elétron: absorvedor → frente → Rs → carga → "
                "contato traseiro"
            )
            hole_text = (
                "lacuna: deriva para o contato traseiro (recombinação)"
            )
        else:
            electron_text = (
                "elétron: base → contato traseiro → carga → Rs → "
                "frente (recombina)"
            )
            hole_text = "lacuna: coletada pelos fingers na frente"
        y = 505.0
        entries = (
            (_COLOR_PHOTON, "fóton (luz solar) → fonte de corrente I_ph"),
            (_COLOR_ELECTRON, electron_text),
            (_COLOR_HOLE, hole_text),
            (_COLOR_RS, f"Rs — {tech.rs_label.split('→')[0].strip()}"),
            (_COLOR_JUNCTION, f"D ∥ C ∥ Rp — {tech.junction_label.split('→')[0].strip()}"),
        )
        for color, text in entries:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(70.0, y - 4.0), 5.0, 5.0)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(_COLOR_TEXT))
            painter.drawText(QPointF(84.0, y), text)
            y += 22.0
        painter.setPen(QPen(_COLOR_ELECTRON))
        painter.drawText(
            QPointF(660.0, 505.0),
            f"Corrente: {self.electrons_per_second():.0f} e⁻/s",
        )


# ---------------------------------------------------------------------------
# Modelo atômico do silício (dopagem n e p)
# ---------------------------------------------------------------------------
class AtomicModelWidget(QWidget):
    """Rede cristalina 2-D do silício com dopantes N (P) e P (B).

    Mostra as ligações covalentes (pares de elétrons animados), o
    átomo de fósforo doador com seu 5º elétron livre vagando pela rede
    e o átomo de boro aceitador com a lacuna saltando entre ligações
    vizinhas.
    """

    _TICK_MS: int = 40
    _COLS: int = 6
    _ROWS: int = 4
    _X0: float = 130.0
    _Y0: float = 120.0
    _DX: float = 118.0
    _DY: float = 112.0
    _ATOM_R: float = 17.0
    #: Posições (coluna, linha) dos dopantes.
    _P_POS: tuple[int, int] = (1, 1)
    _B_POS: tuple[int, int] = (4, 2)
    _HOLE_JUMP_S: float = 1.1

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(760, 480)
        self._phase: float = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)

        # Ligações entre vizinhos (horizontais e verticais).
        self._bonds: list[tuple[tuple[int, int], tuple[int, int]]] = []
        for row in range(self._ROWS):
            for col in range(self._COLS):
                if col + 1 < self._COLS:
                    self._bonds.append(((col, row), (col + 1, row)))
                if row + 1 < self._ROWS:
                    self._bonds.append(((col, row), (col, row + 1)))

        # Lacuna: começa numa ligação vizinha ao boro.
        self.hole_bond = self._random_bond_near(self._B_POS)
        self.hole_slot = 0
        self._last_jump = time.monotonic()

        # Elétron livre do fósforo.
        px, py = self._atom_xy(*self._P_POS)
        self._free_x = px + 40.0
        self._free_y = py - 30.0
        angle = random.uniform(0.0, 2.0 * math.pi)
        self._free_vx = 2.2 * math.cos(angle)
        self._free_vy = 2.2 * math.sin(angle)

    # -- Geometria ----------------------------------------------------------
    def _atom_xy(self, col: int, row: int) -> tuple[float, float]:
        """Centro do átomo na coluna/linha indicadas."""
        return (self._X0 + col * self._DX, self._Y0 + row * self._DY)

    def _atom_symbol(self, col: int, row: int) -> str:
        if (col, row) == self._P_POS:
            return "P"
        if (col, row) == self._B_POS:
            return "B"
        return "Si"

    def _bonds_near(
        self, pos: tuple[int, int]
    ) -> list[int]:
        """Índices das ligações que tocam o átomo indicado."""
        return [
            index
            for index, (a, b) in enumerate(self._bonds)
            if a == pos or b == pos
        ]

    def _random_bond_near(self, pos: tuple[int, int]) -> int:
        return random.choice(self._bonds_near(pos))

    def _adjacent_bonds(self, bond_index: int) -> list[int]:
        """Ligações que compartilham um átomo com a ligação dada."""
        a, b = self._bonds[bond_index]
        adjacent = set(self._bonds_near(a)) | set(self._bonds_near(b))
        adjacent.discard(bond_index)
        return sorted(adjacent)

    # -- Animação ------------------------------------------------------------
    def start(self) -> None:
        """Inicia a animação."""
        if not self._timer.isActive():
            self._timer.start(self._TICK_MS)

    def stop(self) -> None:
        """Pausa a animação."""
        self._timer.stop()

    @property
    def running(self) -> bool:
        """Indica se a animação está em execução."""
        return self._timer.isActive()

    def showEvent(self, event) -> None:  # noqa: N802 (API Qt)
        super().showEvent(event)
        self.start()

    def hideEvent(self, event) -> None:  # noqa: N802 (API Qt)
        self.stop()
        super().hideEvent(event)

    def _advance(self) -> None:
        """Avança um quadro: vibração, elétron livre e salto da lacuna."""
        self._phase += 0.12

        # Elétron livre: caminhada com rebote na região da rede.
        self._free_x += self._free_vx
        self._free_y += self._free_vy
        self._free_vx += random.uniform(-0.35, 0.35)
        self._free_vy += random.uniform(-0.35, 0.35)
        speed = math.hypot(self._free_vx, self._free_vy)
        limit = 3.2
        if speed > limit:
            self._free_vx *= limit / speed
            self._free_vy *= limit / speed
        x_min = self._X0 - 60.0
        x_max = self._X0 + (self._COLS - 1) * self._DX + 60.0
        y_min = self._Y0 - 60.0
        y_max = self._Y0 + (self._ROWS - 1) * self._DY + 60.0
        if not x_min < self._free_x < x_max:
            self._free_vx = -self._free_vx
            self._free_x = min(max(self._free_x, x_min), x_max)
        if not y_min < self._free_y < y_max:
            self._free_vy = -self._free_vy
            self._free_y = min(max(self._free_y, y_min), y_max)

        # Lacuna: salta para uma ligação vizinha periodicamente.
        now = time.monotonic()
        if now - self._last_jump >= self._HOLE_JUMP_S:
            self._last_jump = now
            self.hole_bond = random.choice(
                self._adjacent_bonds(self.hole_bond)
            )
            self.hole_slot = random.randint(0, 1)
        self.update()

    # -- Desenho ----------------------------------------------------------------
    def _electron_slot_xy(
        self, bond_index: int, slot: int
    ) -> tuple[float, float]:
        """Posição do elétron ``slot`` (0/1) de uma ligação."""
        (c1, r1), (c2, r2) = self._bonds[bond_index]
        x1, y1 = self._atom_xy(c1, r1)
        x2, y2 = self._atom_xy(c2, r2)
        t = 0.38 if slot == 0 else 0.62
        bx = x1 + (x2 - x1) * t
        by = y1 + (y2 - y1) * t
        # Deslocamento perpendicular + vibração térmica.
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        offset = 4.0 if slot == 0 else -4.0
        jitter = 1.8 * math.sin(
            self._phase * 2.0 + bond_index * 1.7 + slot * 2.4
        )
        return (bx + nx * (offset + jitter), by + ny * (offset + jitter))

    def paintEvent(self, _event) -> None:  # noqa: N802 (API Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(24, 24, 24))

        scale = min(self.width() / _VW, self.height() / _VH)
        painter.translate(
            (self.width() - _VW * scale) / 2.0,
            (self.height() - _VH * scale) / 2.0,
        )
        painter.scale(scale, scale)

        font = painter.font()
        font.setPointSizeF(9.5)
        painter.setFont(font)
        painter.setPen(QPen(_COLOR_TEXT))
        painter.drawText(
            QPointF(130.0, 52.0),
            "Rede cristalina do silício — ligações covalentes e "
            "dopagem n (P) / p (B)",
        )

        # Ligações e elétrons compartilhados.
        bond_pen = QPen(QColor(120, 130, 140), 1.4)
        for index, ((c1, r1), (c2, r2)) in enumerate(self._bonds):
            x1, y1 = self._atom_xy(c1, r1)
            x2, y2 = self._atom_xy(c2, r2)
            painter.setPen(bond_pen)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            for slot in (0, 1):
                ex, ey = self._electron_slot_xy(index, slot)
                if index == self.hole_bond and slot == self.hole_slot:
                    # Lacuna: elétron ausente (anel vermelho).
                    painter.setPen(QPen(_COLOR_HOLE, 2.0))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(QPointF(ex, ey), 5.0, 5.0)
                else:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(0, 229, 255, 200))
                    painter.drawEllipse(QPointF(ex, ey), 3.0, 3.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Átomos.
        for row in range(self._ROWS):
            for col in range(self._COLS):
                x, y = self._atom_xy(col, row)
                symbol = self._atom_symbol(col, row)
                if symbol == "P":
                    fill = QColor(230, 126, 34)
                elif symbol == "B":
                    fill = QColor(231, 76, 60)
                else:
                    fill = QColor(52, 73, 94)
                painter.setPen(QPen(QColor(190, 200, 210), 1.2))
                painter.setBrush(fill)
                painter.drawEllipse(
                    QPointF(x, y), self._ATOM_R, self._ATOM_R
                )
                painter.setPen(QPen(QColor(255, 255, 255)))
                painter.drawText(
                    QRectF(x - self._ATOM_R, y - self._ATOM_R,
                           2 * self._ATOM_R, 2 * self._ATOM_R),
                    Qt.AlignmentFlag.AlignCenter,
                    symbol,
                )
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Rótulos dos dopantes.
        px, py = self._atom_xy(*self._P_POS)
        painter.setPen(QPen(QColor(230, 126, 34)))
        painter.drawText(
            QPointF(px - 58.0, py - self._ATOM_R - 10.0),
            "P: doador (tipo n)",
        )
        bx, by = self._atom_xy(*self._B_POS)
        painter.setPen(QPen(_COLOR_HOLE))
        painter.drawText(
            QPointF(bx - 62.0, by + self._ATOM_R + 20.0),
            "B: aceitador (tipo p)",
        )

        # Elétron livre do fósforo.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 229, 255, 60))
        painter.drawEllipse(QPointF(self._free_x, self._free_y),
                            8.0, 8.0)
        painter.setBrush(_COLOR_ELECTRON)
        painter.drawEllipse(QPointF(self._free_x, self._free_y),
                            3.4, 3.4)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(_COLOR_ELECTRON))
        painter.drawText(
            QPointF(self._free_x + 12.0, self._free_y - 8.0),
            "e⁻ livre",
        )

        # Painel explicativo à direita.
        painter.setPen(QPen(_COLOR_TEXT))
        blocks = (
            ("Silício (Si)",
             "4 elétrons de valência: cada átomo forma 4 ligações "
             "covalentes com os vizinhos (aqui, 2-D simplificado)."),
            ("Dopagem tipo n — fósforo (P)",
             "5 elétrons de valência: 4 formam ligações e o 5º fica "
             "fracamente ligado — vira um elétron LIVRE (portador "
             "negativo)."),
            ("Dopagem tipo p — boro (B)",
             "3 elétrons de valência: falta um elétron em uma "
             "ligação — a LACUNA (anel vermelho), que salta de "
             "ligação em ligação como portador positivo."),
            ("Junção p-n",
             "Unindo as regiões n e p forma-se a junção do módulo "
             "fotovoltaico — o diodo D e a capacitância C medidos "
             "pela EIS."),
        )
        y_text = 96.0
        for title, body in blocks:
            painter.setPen(QPen(QColor(79, 195, 247)))
            painter.drawText(QPointF(796.0, y_text), title)
            painter.setPen(QPen(_COLOR_TEXT))
            rect = QRectF(796.0, y_text + 8.0, 190.0, 110.0)
            painter.drawText(
                rect,
                Qt.TextFlag.TextWordWrap,
                body,
            )
            y_text += 128.0

        # Legenda inferior.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_COLOR_ELECTRON)
        painter.drawEllipse(QPointF(140.0, 566.0), 4.0, 4.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(_COLOR_TEXT))
        painter.drawText(
            QPointF(152.0, 570.0),
            "elétron (par da ligação covalente / livre)",
        )
        painter.setPen(QPen(_COLOR_HOLE, 2.0))
        painter.drawEllipse(QPointF(470.0, 566.0), 5.0, 5.0)
        painter.setPen(QPen(_COLOR_TEXT))
        painter.drawText(
            QPointF(484.0, 570.0),
            "lacuna (elétron ausente na ligação)",
        )


# ---------------------------------------------------------------------------
# Janela da simulação
# ---------------------------------------------------------------------------
class PVSimulationDialog(QDialog):
    """Janela "Simulação do módulo fotovoltaico"."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            "Simulação do módulo fotovoltaico — circuito FV animado"
        )
        self.resize(1060, 800)

        self.canvas = PVSimulationWidget(self)
        self.atomic = AtomicModelWidget(self)

        # -- Controles do módulo -----------------------------------------
        self.tech_combo = QComboBox(self)
        for key, tech in TECHNOLOGIES.items():
            self.tech_combo.addItem(tech.display_name, key)
        self.tech_combo.currentIndexChanged.connect(
            self._on_tech_changed
        )
        self.tech_label = QLabel(
            TECHNOLOGIES["p_si"].description, self
        )
        self.tech_label.setWordWrap(True)
        self.tech_label.setStyleSheet("color: #9a9a9a;")

        self.irradiance_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.irradiance_slider.setRange(0, 60)
        self.irradiance_slider.setValue(20)
        self.irradiance_slider.setToolTip(
            "Irradiância: taxa de fótons que atingem a célula."
        )
        self.irradiance_slider.valueChanged.connect(
            self._on_irradiance_changed
        )
        self._irradiance_label = QLabel("20 fótons/s", self)

        self.speed_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.speed_slider.setRange(2, 30)
        self.speed_slider.setValue(10)
        self.speed_slider.setToolTip("Velocidade da animação.")
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        self._speed_label = QLabel("1.0×", self)

        self.mapping_checkbox = QCheckBox(
            "Mostrar correspondência com o circuito equivalente", self
        )
        self.mapping_checkbox.setChecked(True)
        self.mapping_checkbox.toggled.connect(
            self.canvas.set_show_mapping
        )

        self.pause_button = QPushButton("Pausar", self)
        self.pause_button.clicked.connect(self._toggle_pause)

        tech_row = QHBoxLayout()
        tech_row.addWidget(QLabel("Tecnologia:", self))
        tech_row.addWidget(self.tech_combo, 1)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Irradiância:", self))
        controls.addWidget(self.irradiance_slider, 2)
        controls.addWidget(self._irradiance_label)
        controls.addSpacing(16)
        controls.addWidget(QLabel("Velocidade:", self))
        controls.addWidget(self.speed_slider, 1)
        controls.addWidget(self._speed_label)
        controls.addSpacing(16)
        controls.addWidget(self.pause_button)

        module_layout = QVBoxLayout()
        module_layout.addLayout(tech_row)
        module_layout.addWidget(self.tech_label)
        module_layout.addWidget(self.canvas, 1)
        module_layout.addLayout(controls)
        module_layout.addWidget(self.mapping_checkbox)
        module_page = QWidget(self)
        module_page.setLayout(module_layout)

        # -- Aba do modelo atômico ---------------------------------------------
        atomic_hint = QLabel(
            "O 5º elétron do fósforo (doador) fica livre e vaga pela "
            "rede; a ligação incompleta do boro (aceitador) cria a "
            "lacuna, que salta entre ligações vizinhas. São esses "
            "portadores que a junção p-n separa no módulo.",
            self,
        )
        atomic_hint.setWordWrap(True)
        atomic_hint.setStyleSheet("color: #9a9a9a;")
        atomic_layout = QVBoxLayout()
        atomic_layout.addWidget(atomic_hint)
        atomic_layout.addWidget(self.atomic, 1)
        atomic_page = QWidget(self)
        atomic_page.setLayout(atomic_layout)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(module_page, "Módulo (corte)")
        self.tabs.addTab(atomic_page, "Modelo atômico (Si, dopagem n/p)")

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close, self
        )
        button_box.rejected.connect(self.reject)
        button_box.button(
            QDialogButtonBox.StandardButton.Close
        ).clicked.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(button_box)

        logger.info("Janela de simulação do módulo FV aberta.")

    def _on_tech_changed(self, _index: int) -> None:
        key = self.tech_combo.currentData()
        self.canvas.set_technology(key)
        self.tech_label.setText(TECHNOLOGIES[key].description)

    def _on_irradiance_changed(self, value: int) -> None:
        self.canvas.set_irradiance(value)
        self._irradiance_label.setText(f"{value} fótons/s")

    def _on_speed_changed(self, value: int) -> None:
        factor = value / 10.0
        self.canvas.set_speed_factor(factor)
        self._speed_label.setText(f"{factor:.1f}×")

    def _toggle_pause(self) -> None:
        if self.canvas.running or self.atomic.running:
            self.canvas.stop()
            self.atomic.stop()
            self.pause_button.setText("Continuar")
        else:
            if self.tabs.currentIndex() == 0:
                self.canvas.start()
            else:
                self.atomic.start()
            self.pause_button.setText("Pausar")
