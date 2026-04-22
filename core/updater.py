"""App update checker — compares current version against the latest GitHub release."""
from __future__ import annotations

import threading
import webbrowser
from packaging.version import Version

import requests
from PyQt5.QtCore import QObject, pyqtSignal, Qt
from PyQt5.QtWidgets import QMessageBox, QPushButton, QDialog, QVBoxLayout, QLabel, QHBoxLayout

from utils.constants import APP_NAME, APP_VERSION

GITHUB_OWNER    = "dj2nazty"
GITHUB_REPO     = "iptv-checker"
RELEASES_API    = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE   = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"


# ── Worker that fetches the release info off the UI thread ────────────────────
class _UpdateWorker(QObject):
    result = pyqtSignal(dict)   # {"latest": "2.1.0", "url": "...", "notes": "..."}
    error  = pyqtSignal(str)

    def fetch(self):
        try:
            resp = requests.get(
                RELEASES_API,
                timeout=10,
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": f"{APP_NAME}/{APP_VERSION}"},
            )
            resp.raise_for_status()
            data     = resp.json()
            tag      = data.get("tag_name", "").lstrip("v")
            html_url = data.get("html_url", RELEASES_PAGE)
            notes    = data.get("body", "")[:800]
            self.result.emit({"latest": tag, "url": html_url, "notes": notes})
        except Exception as exc:
            self.error.emit(str(exc))


# ── Public API ────────────────────────────────────────────────────────────────
def check_for_updates(parent=None, silent: bool = False):
    """
    Check for a newer release on GitHub.

    Args:
        parent: parent QWidget for dialogs
        silent: if True, show a dialog only when an update IS available
                (used for automatic startup checks).
    """
    worker = _UpdateWorker()
    worker.result.connect(lambda data: _on_result(data, parent, silent))
    worker.error.connect(lambda err: _on_error(err, parent, silent))

    t = threading.Thread(target=worker.fetch, daemon=True)
    t.start()


def _on_result(data: dict, parent, silent: bool):
    latest_str  = data["latest"]
    release_url = data["url"]
    notes       = data["notes"]

    try:
        is_newer = Version(latest_str) > Version(APP_VERSION)
    except Exception:
        is_newer = latest_str != APP_VERSION

    if not is_newer:
        if not silent:
            QMessageBox.information(
                parent, "Up to Date",
                f"{APP_NAME} v{APP_VERSION} is the latest version. ✓"
            )
        return

    # Update available — show a rich dialog
    dlg = _UpdateDialog(parent, APP_VERSION, latest_str, release_url, notes)
    dlg.exec_()


def _on_error(err: str, parent, silent: bool):
    if not silent:
        QMessageBox.warning(
            parent, "Update Check Failed",
            f"Could not reach GitHub to check for updates.\n\nError: {err}"
        )


# ── Update dialog ─────────────────────────────────────────────────────────────
class _UpdateDialog(QDialog):
    def __init__(self, parent, current: str, latest: str, url: str, notes: str):
        super().__init__(parent)
        self.setWindowTitle("Update Available")
        self.setMinimumWidth(480)
        self._url = url

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        title = QLabel(f"🎉  A new version of {APP_NAME} is available!")
        f = title.font(); f.setBold(True); f.setPointSize(12); title.setFont(f)
        title.setStyleSheet("color: #a6e3a1;")
        layout.addWidget(title)

        # Version info
        ver_label = QLabel(
            f"<b>Current version:</b> v{current}<br>"
            f"<b>Latest version:</b>  v{latest}"
        )
        ver_label.setTextFormat(Qt.RichText)
        ver_label.setStyleSheet("color: #cdd6f4; font-size: 12px;")
        layout.addWidget(ver_label)

        # Release notes
        if notes.strip():
            notes_title = QLabel("Release notes:")
            notes_title.setStyleSheet("color: #a6adc8; font-size: 11px; font-weight: bold;")
            layout.addWidget(notes_title)

            notes_label = QLabel(notes.strip())
            notes_label.setWordWrap(True)
            notes_label.setStyleSheet(
                "background: #1e1e2e; border: 1px solid #45475a; border-radius: 4px;"
                "padding: 8px; color: #cdd6f4; font-size: 11px;"
            )
            layout.addWidget(notes_label)

        # Buttons
        btn_row = QHBoxLayout()

        download_btn = QPushButton("⬇  Download v" + latest)
        download_btn.setStyleSheet(
            "background-color: #a6e3a1; color: #1e1e2e; font-weight: bold; padding: 8px 20px;"
        )
        download_btn.clicked.connect(self._open_download)
        btn_row.addWidget(download_btn)

        later_btn = QPushButton("Later")
        later_btn.setStyleSheet("padding: 8px 16px;")
        later_btn.clicked.connect(self.reject)
        btn_row.addWidget(later_btn)

        layout.addLayout(btn_row)

    def _open_download(self):
        webbrowser.open(self._url)
        self.accept()


# ── Simple version comparison without packaging lib ───────────────────────────
# Fall back if packaging is not installed
try:
    from packaging.version import Version
except ImportError:
    class Version:  # type: ignore
        def __init__(self, s: str):
            self._parts = tuple(int(x) for x in s.strip().split(".") if x.isdigit())

        def __gt__(self, other):
            a, b = self._parts, other._parts
            return a > b
