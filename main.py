"""IPTV Stream Checker — Entry point."""

import sys
import os
import traceback
import logging

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtGui import QFont

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
log = logging.getLogger("iptv-checker")


def _global_exception_handler(exc_type, exc_value, exc_tb):
    """Catch unhandled exceptions so the app doesn't silently crash."""
    if exc_type is KeyboardInterrupt:
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    log.critical("Unhandled exception:\n%s", msg)
    try:
        QMessageBox.critical(None, "Unexpected Error", f"An error occurred:\n\n{msg[:800]}")
    except Exception:
        pass


def load_stylesheet() -> str:
    """Load the dark theme QSS from assets."""
    if hasattr(sys, "_MEIPASS"):
        qss_path = os.path.join(sys._MEIPASS, "assets", "dark_theme.qss")
    else:
        qss_path = os.path.join(os.path.dirname(__file__), "assets", "dark_theme.qss")

    if os.path.exists(qss_path):
        with open(qss_path, "r") as f:
            return f.read()
    return ""


def main():
    sys.excepthook = _global_exception_handler

    app = QApplication(sys.argv)
    app.setApplicationName("IPTV Stream Checker")

    # Set default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Apply dark theme
    stylesheet = load_stylesheet()
    if stylesheet:
        app.setStyleSheet(stylesheet)

    from ui.main_window import MainWindow
    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
