"""Gera as capturas de tela do Guia do usuário (assets/ajuda/*.png).

Executa o programa em modo offscreen com dados sintéticos (circuito de
Randles e curva I-V de diodo) e fotografa a janela principal, as abas
e as janelas auxiliares.  Rode a partir da raiz do projeto::

    python assets/gerar_ajuda.py

As imagens são referenciadas por ``ajuda.py``; se alguma faltar, o
guia simplesmente omite a figura.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Plataforma nativa (não "offscreen": ela renderiza sem fontes no
# Windows). Os widgets usam WA_DontShowOnScreen — nada pisca na tela.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "assets" / "ajuda"
OUT.mkdir(parents=True, exist_ok=True)

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

app = QApplication([])

import gui
import util


def salva(widget, nome: str) -> None:
    """Fotografa o widget e grava em assets/ajuda/<nome>.png."""
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    widget.show()
    app.processEvents()
    widget.grab().save(str(OUT / f"{nome}.png"))
    widget.hide()
    print(f"ok  {nome}.png")


# -- Dados sintéticos -------------------------------------------------------
def randles(rs: float, rp: float, c: float, f: np.ndarray) -> np.ndarray:
    """Impedância de um circuito de Randles simplificado (Rs + Rp||C)."""
    w = 2 * np.pi * f
    return rs + rp / (1 + 1j * w * rp * c)


freq = np.logspace(0, 5, 60)
window = gui.MainWindow()
window.resize(1280, 800)

for nome, rs, rp, c in (
    ("FRA0F (íntegro)", 10.0, 1000.0, 1e-6),
    ("FRA3F (degradado)", 25.0, 400.0, 2e-6),
):
    z = randles(rs, rp, c, freq)
    m = util.Measurement.from_components(
        name=nome,
        frequency=freq,
        z_real=z.real.tolist(),
        minus_z_imag=(-z.imag).tolist(),
    )
    window.add_measurement(m)

v = np.linspace(0.0, 34.0, 80)
il, i0, a, rp_iv = 8.5, 1e-9, 1.9, 350.0
i = np.clip(il - i0 * (np.exp(v / a) - 1) - v / rp_iv, 0.0, None)
window.add_iv_curve(
    util.IVCurve(name="IV FRA0F", voltage=v, current=i)
)

app.processEvents()

# -- Janela principal e abas ------------------------------------------------
ABAS = {
    "dados": 0,
    "curva_iv": 1,
    "nyquist": 2,
    "kk": 5,
    "circuito": 6,
    "comparacao": 7,
}
window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
window.show()
app.processEvents()
window.tabs.setCurrentIndex(2)
app.processEvents()
salva(window, "principal")
for nome, indice in ABAS.items():
    window.tabs.setCurrentIndex(indice)
    app.processEvents()
    salva(window.tabs.currentWidget(), nome)

salva(window.measurement_dock, "amostras")

# -- Janelas auxiliares -----------------------------------------------------
salva(gui.SerialDialog(window, mode="generico"), "serial_generico")
salva(gui.SerialDialog(window, mode="ad5933"), "serial_ad5933")
salva(gui.CorrectionDialog(window), "correcao")

salva(gui.DiodeFitDialog(window, window), "diodo")

salva(gui.CircuitBuilderDialog(window), "editor_circuito")

print("Capturas geradas em", OUT)
