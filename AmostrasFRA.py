"""AMOSTRAS FRA 2.0 — ponto de entrada da aplicação.

Software científico de Espectroscopia de Impedância (EIS/FRA) para
detecção e classificação de falhas em módulos fotovoltaicos.

Execução:

.. code-block:: console

    python AmostrasFRA.py

Compilação com PyInstaller:

.. code-block:: console

    pyinstaller --noconfirm --windowed --name AmostrasFRA AmostrasFRA.py
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

import util

logger = logging.getLogger(__name__)


def main() -> int:
    """Inicializa e executa a aplicação.

    Returns:
        Código de saída do loop de eventos do Qt.
    """
    util.configure_logging(logging.INFO)
    logger.info("Iniciando %s (versão %s).", util.APP_NAME, util.APP_VERSION)

    # No Windows, a barra de tarefas escolhe o ícone pelo AppUserModelID
    # do processo. Sem um ID próprio, ela usaria o ícone do python.exe
    # (genérico) em vez do ícone da janela. Definir um ID explícito faz
    # a barra de tarefas exibir o ícone do aplicativo.
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                f"AmostrasFRA.EIS.{util.APP_VERSION}"
            )
        except Exception:  # pragma: no cover - específico do Windows
            logger.debug(
                "Não foi possível definir o AppUserModelID.",
                exc_info=True,
            )

    app = QApplication(sys.argv)
    app.setApplicationName(util.APP_NAME)
    app.setApplicationVersion(util.APP_VERSION)
    app.setOrganizationName("AmostrasFRA")

    icon_file = util.icon_path()
    if icon_file is not None:
        app.setWindowIcon(QIcon(str(icon_file)))

    try:
        # Importações tardias: o tema do Matplotlib e a janela principal
        # exigem a QApplication já criada.
        from gui import MainWindow, apply_dark_theme
        from plots import apply_dark_theme_to_matplotlib

        apply_dark_theme(app)
        apply_dark_theme_to_matplotlib()

        window = MainWindow()
        window.show()
    except Exception as exc:  # pragma: no cover - proteção de startup
        logger.exception("Falha crítica na inicialização.")
        QMessageBox.critical(
            None,
            util.APP_NAME,
            "Falha crítica na inicialização da aplicação:\n"
            f"{exc}\n\n"
            "Consulte o arquivo de log em ~/.amostras_fra/ para "
            "detalhes.",
        )
        return 1

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
