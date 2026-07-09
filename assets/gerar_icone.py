"""Gera os arquivos de ícone (PNG e ICO) a partir de ``icone.svg``.

Rasteriza o SVG com o Qt (alta qualidade, independente de tela) e monta
um ``.ico`` multi-resolução com o Pillow, usado como ícone da janela e
pelo executável do PyInstaller.

Execução:

.. code-block:: console

    python assets/gerar_icone.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

ASSETS = Path(__file__).resolve().parent


def _render(renderer: QSvgRenderer, size: int) -> QImage:
    """Rasteriza o SVG num quadrado ``size`` × ``size`` transparente."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def _to_pillow(image: QImage):
    """Converte um :class:`QImage` para :class:`PIL.Image.Image`."""
    from PIL import Image  # importado aqui para não ser dependência do app
    from PySide6.QtCore import QBuffer

    buffer = io.BytesIO()
    qbuffer = QBuffer()
    qbuffer.open(QBuffer.OpenModeFlag.ReadWrite)
    image.save(qbuffer, "PNG")
    buffer.write(bytes(qbuffer.data()))
    buffer.seek(0)
    return Image.open(buffer).convert("RGBA")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    renderer = QSvgRenderer(str(ASSETS / "icone.svg"))
    if not renderer.isValid():
        print("SVG inválido:", ASSETS / "icone.svg")
        return 1

    # PNG principal (256) para README/pré-visualização.
    _render(renderer, 256).save(str(ASSETS / "icone.png"))

    # ICO multi-resolução (nitidez em cada tamanho via rasterização SVG).
    sizes = (16, 24, 32, 48, 64, 128, 256)
    frames = [_to_pillow(_render(renderer, s)) for s in sizes]
    frames[-1].save(
        ASSETS / "icone.ico",
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[:-1],
    )
    print("Gerados:", ASSETS / "icone.png", "e", ASSETS / "icone.ico")
    return 0


if __name__ == "__main__":
    sys.exit(main())
