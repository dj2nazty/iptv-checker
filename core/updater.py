"""App update checker — fetches the latest GitHub release, downloads the
installer, and runs it so the user never has to open a browser."""
from __future__ import annotations

import os
import sys
import subprocess
import tempfile
import threading

import requests
from PyQt5.QtCore import QObject, pyqtSignal, Qt, QThread
from PyQt5.QtWidgets import (
    QMessageBox, QPushButton, QDialog, QVBoxLayout,
    QLabel, QHBoxLayout, QProgressBar,
)

from utils.constants import APP_NAME, APP_VERSION

GITHUB_OWNER  = "dj2nazty"
GITHUB_REPO   = "iptv-checker"
RELEASES_API  = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"


# ── Worker: fetch release info off the UI thread ──────────────────────────────
class _UpdateWorker(QObject):
    result = pyqtSignal(dict)   # {latest, url, notes, asset_url, asset_name}
    error  = pyqtSignal(str)

    def fetch(self):
        try:
            resp = requests.get(
                RELEASES_API,
                timeout=10,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"{APP_NAME}/{APP_VERSION}",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            tag      = data.get("tag_name", "").lstrip("v")
            html_url = data.get("html_url", RELEASES_PAGE)
            notes    = data.get("body", "")[:800]

            # Find the first .exe asset (the Inno Setup installer)
            asset_url  = ""
            asset_name = ""
            for asset in data.get("assets", []):
                if asset.get("name", "").lower().endswith(".exe"):
                    asset_url  = asset.get("browser_download_url", "")
                    asset_name = asset.get("name", "")
                    break

            self.result.emit({
                "latest":     tag,
                "url":        html_url,
                "notes":      notes,
                "asset_url":  asset_url,
                "asset_name": asset_name,
            })
        except Exception as exc:
            self.error.emit(str(exc))


# ── Worker: download installer in the background ──────────────────────────────
class _DownloadWorker(QObject):
    progress = pyqtSignal(int)   # 0-100
    done     = pyqtSignal(str)   # local file path
    failed   = pyqtSignal(str)   # error message

    def __init__(self, url: str, dest: str):
        super().__init__()
        self._url  = url
        self._dest = dest

    def run(self):
        try:
            resp = requests.get(self._url, stream=True, timeout=60,
                                headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
            resp.raise_for_status()

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(self._dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            self.progress.emit(int(downloaded * 100 / total))

            self.progress.emit(100)
            self.done.emit(self._dest)
        except Exception as exc:
            self.failed.emit(str(exc))


# ── Download + install dialog ─────────────────────────────────────────────────
class _InstallDialog(QDialog):
    """Shows a progress bar while downloading, then launches the installer."""

    def __init__(self, parent, asset_url: str, asset_name: str, version: str):
        super().__init__(parent)
        self.setWindowTitle("Downloading Update…")
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)

        self._dest = os.path.join(tempfile.gettempdir(), asset_name)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self._status = QLabel(f"Downloading {APP_NAME} v{version}…")
        self._status.setStyleSheet("color: #cdd6f4; font-size: 12px;")
        layout.addWidget(self._status)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        self._bar.setStyleSheet(
            "QProgressBar { border: 1px solid #45475a; border-radius: 4px;"
            "  background: #1e1e2e; color: #cdd6f4; text-align: center; }"
            "QProgressBar::chunk { background: #a6e3a1; border-radius: 3px; }"
        )
        layout.addWidget(self._bar)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setStyleSheet("padding: 6px 16px;")
        self._cancel_btn.clicked.connect(self.reject)
        layout.addWidget(self._cancel_btn, alignment=Qt.AlignRight)

        # Kick off download thread
        self._thread = QThread(self)
        self._worker = _DownloadWorker(asset_url, self._dest)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._bar.setValue)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    def _on_done(self, path: str):
        self._thread.quit()
        self._status.setText("Installing…  (the app will restart)")
        self._cancel_btn.setEnabled(False)

        # Launch the Inno Setup installer; it handles uninstall + install
        try:
            subprocess.Popen([path], creationflags=subprocess.DETACHED_PROCESS)
        except Exception as exc:
            QMessageBox.critical(self, "Launch Failed",
                                 f"Downloaded OK but could not run installer:\n{exc}\n\n"
                                 f"File saved to:\n{path}")
            self.reject()
            return

        # Close the app so the installer can replace the EXE
        self.accept()
        sys.exit(0)

    def _on_failed(self, msg: str):
        self._thread.quit()
        QMessageBox.critical(self, "Download Failed",
                             f"Could not download the update:\n\n{msg}")
        self.reject()

    def reject(self):
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)
        super().reject()


# ── Update-available dialog ───────────────────────────────────────────────────
class _UpdateDialog(QDialog):
    def __init__(self, parent, current: str, latest: str,
                 release_url: str, notes: str,
                 asset_url: str, asset_name: str):
        super().__init__(parent)
        self.setWindowTitle("Update Available")
        self.setMinimumWidth(500)

        self._parent     = parent
        self._release_url = release_url
        self._asset_url  = asset_url
        self._asset_name = asset_name
        self._latest     = latest

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
            f"<b>New version:</b>&nbsp;&nbsp;&nbsp; v{latest}"
        )
        ver_label.setTextFormat(Qt.RichText)
        ver_label.setStyleSheet("color: #cdd6f4; font-size: 12px;")
        layout.addWidget(ver_label)

        # Release notes
        if notes.strip():
            notes_title = QLabel("What's new:")
            notes_title.setStyleSheet(
                "color: #a6adc8; font-size: 11px; font-weight: bold;")
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

        if asset_url:
            install_btn = QPushButton(f"⬇  Install v{latest} Now")
            install_btn.setStyleSheet(
                "background-color: #a6e3a1; color: #1e1e2e;"
                "font-weight: bold; padding: 8px 20px; border-radius: 4px;"
            )
            install_btn.clicked.connect(self._install)
            btn_row.addWidget(install_btn)
        else:
            # No asset uploaded yet — fall back to opening the releases page
            import webbrowser
            open_btn = QPushButton(f"⬇  Open Download Page")
            open_btn.setStyleSheet(
                "background-color: #a6e3a1; color: #1e1e2e;"
                "font-weight: bold; padding: 8px 20px; border-radius: 4px;"
            )
            open_btn.clicked.connect(lambda: (webbrowser.open(release_url), self.accept()))
            btn_row.addWidget(open_btn)

        later_btn = QPushButton("Later")
        later_btn.setStyleSheet("padding: 8px 16px;")
        later_btn.clicked.connect(self.reject)
        btn_row.addWidget(later_btn)

        layout.addLayout(btn_row)

    def _install(self):
        self.accept()
        dlg = _InstallDialog(self._parent, self._asset_url,
                             self._asset_name, self._latest)
        dlg.exec_()


# ── Public API ────────────────────────────────────────────────────────────────
def check_for_updates(parent=None, silent: bool = False):
    """
    Check for a newer release on GitHub.

    Args:
        parent: parent QWidget for dialogs
        silent: if True, only show a dialog when an update IS available
                (used for silent startup checks).
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
    asset_url   = data["asset_url"]
    asset_name  = data["asset_name"]

    try:
        is_newer = _Version(latest_str) > _Version(APP_VERSION)
    except Exception:
        is_newer = latest_str != APP_VERSION

    if not is_newer:
        if not silent:
            QMessageBox.information(
                parent, "Up to Date",
                f"{APP_NAME} v{APP_VERSION} is the latest version. ✓"
            )
        return

    dlg = _UpdateDialog(parent, APP_VERSION, latest_str,
                        release_url, notes, asset_url, asset_name)
    dlg.exec_()


def _on_error(err: str, parent, silent: bool):
    if not silent:
        QMessageBox.warning(
            parent, "Update Check Failed",
            f"Could not reach GitHub to check for updates.\n\nError: {err}"
        )


# ── Simple version comparison (no external lib needed) ────────────────────────
class _Version:
    def __init__(self, s: str):
        self._parts = tuple(int(x) for x in s.strip().split(".") if x.isdigit())

    def __gt__(self, other: "_Version") -> bool:
        a, b = self._parts, other._parts
        # Pad shorter tuple
        length = max(len(a), len(b))
        a = a + (0,) * (length - len(a))
        b = b + (0,) * (length - len(b))
        return a > b

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _Version):
            return NotImplemented
        return self._parts == other._parts
