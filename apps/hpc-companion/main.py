"""HPC Companion 入口。"""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from core import config
from ui import theme
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setOrganizationName(config.ORG)
    theme.CURRENT = config.load_settings().get("theme", "dark")
    app.setStyleSheet(theme.stylesheet())

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
