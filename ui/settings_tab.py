"""Settings Tab — configure app-wide options (Reddit URLs, scan limits, etc.)."""
from __future__ import annotations

import re
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QSpinBox,
    QGroupBox, QMessageBox, QAbstractItemView, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal, QUrl
from PyQt5.QtGui import QColor, QDesktopServices, QFont

from utils.app_settings import settings, extract_subreddit_json_url, reddit_url_to_display

# Basic Reddit subreddit URL validator
_SUB_RE = re.compile(
    r'^(https?://)?(www\.)?reddit\.com/r/[A-Za-z0-9_]+/?$'
    r'|^/?r/[A-Za-z0-9_]+/?$'
    r'|^[A-Za-z0-9_]{2,}$'
)


class SettingsTab(QWidget):
    """Tab that lets the user configure which Reddit channels to scan."""

    # Emitted whenever the user saves settings so other tabs can react
    settings_saved = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._load_into_ui()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(20, 16, 20, 16)

        # ── Header ───────────────────────────────────────────────────────────
        header = QLabel("⚙  Settings")
        f = header.font()
        f.setPointSize(14)
        f.setBold(True)
        header.setFont(f)
        header.setStyleSheet("color: #cba6f7;")
        root.addWidget(header)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #313244;")
        root.addWidget(line)

        # ── Reddit Channels group ─────────────────────────────────────────────
        reddit_box = QGroupBox("Reddit Channels to Scan")
        reddit_box.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
        """)
        reddit_layout = QVBoxLayout(reddit_box)
        reddit_layout.setSpacing(8)

        # Explanation
        info = QLabel(
            "Add one or more subreddit URLs below. The scanner will scan ALL of them when you click "
            "\"Scan Reddit\".\n"
            "You can enter a full URL like <b>https://www.reddit.com/r/IPTV_ZONENEW/</b> "
            "or just the name like <b>IPTV_ZONENEW</b>."
        )
        info.setWordWrap(True)
        info.setTextFormat(Qt.RichText)
        info.setStyleSheet("color: #a6adc8; font-size: 11px; padding-bottom: 4px;")
        reddit_layout.addWidget(info)

        # List of current channels
        self._url_list = QListWidget()
        self._url_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._url_list.setAlternatingRowColors(True)
        self._url_list.setMinimumHeight(160)
        self._url_list.setStyleSheet("""
            QListWidget {
                background-color: #1e1e2e;
                border: 1px solid #45475a;
                border-radius: 4px;
                font-size: 12px;
                color: #cdd6f4;
            }
            QListWidget::item:selected {
                background-color: #45475a;
            }
        """)
        reddit_layout.addWidget(self._url_list)

        # Input row
        input_row = QHBoxLayout()

        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText(
            "e.g.  https://www.reddit.com/r/IPTV_ZONENEW/  or just  IPTV_ZONENEW"
        )
        self._url_input.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e2e;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 6px 10px;
                color: #cdd6f4;
                font-size: 12px;
            }
            QLineEdit:focus { border-color: #cba6f7; }
        """)
        self._url_input.returnPressed.connect(self._add_url)
        input_row.addWidget(self._url_input, 1)

        add_btn = QPushButton("➕  Add")
        add_btn.setStyleSheet(
            "background-color: #a6e3a1; color: #1e1e2e; font-weight: bold; padding: 6px 16px;"
        )
        add_btn.clicked.connect(self._add_url)
        input_row.addWidget(add_btn)

        remove_btn = QPushButton("🗑  Remove Selected")
        remove_btn.setStyleSheet(
            "background-color: #f38ba8; color: #1e1e2e; font-weight: bold; padding: 6px 14px;"
        )
        remove_btn.clicked.connect(self._remove_selected)
        input_row.addWidget(remove_btn)

        reddit_layout.addLayout(input_row)

        # Quick-open button
        open_row = QHBoxLayout()
        open_btn = QPushButton("🌐  Open Selected in Browser")
        open_btn.setStyleSheet("color: #89b4fa; padding: 4px 10px;")
        open_btn.clicked.connect(self._open_in_browser)
        open_row.addWidget(open_btn)
        open_row.addStretch()
        reddit_layout.addLayout(open_row)

        root.addWidget(reddit_box)

        # ── Scan options group ────────────────────────────────────────────────
        scan_box = QGroupBox("Scan Options")
        scan_box.setStyleSheet(reddit_box.styleSheet())
        scan_layout = QVBoxLayout(scan_box)
        scan_layout.setSpacing(10)

        # Pages per scan
        pages_row = QHBoxLayout()
        pages_label = QLabel("Pages per subreddit (100 posts each):")
        pages_label.setStyleSheet("color: #cdd6f4;")
        pages_row.addWidget(pages_label)

        self._pages_spin = QSpinBox()
        self._pages_spin.setRange(1, 20)
        self._pages_spin.setValue(settings.reddit_max_pages)
        self._pages_spin.setToolTip(
            "How many pages (×100 posts) to fetch from each subreddit.\n"
            "5 pages = up to 500 posts per channel."
        )
        self._pages_spin.setFixedWidth(70)
        pages_row.addWidget(self._pages_spin)
        pages_row.addStretch()
        scan_layout.addLayout(pages_row)

        # Test workers
        workers_row = QHBoxLayout()
        workers_label = QLabel("Concurrent test workers (how many credentials tested at once):")
        workers_label.setStyleSheet("color: #cdd6f4;")
        workers_row.addWidget(workers_label)

        self._workers_spin = QSpinBox()
        self._workers_spin.setRange(1, 20)
        self._workers_spin.setValue(settings.reddit_test_workers)
        self._workers_spin.setFixedWidth(70)
        workers_row.addWidget(self._workers_spin)
        workers_row.addStretch()
        scan_layout.addLayout(workers_row)

        root.addWidget(scan_box)

        # ── Save button ───────────────────────────────────────────────────────
        save_row = QHBoxLayout()
        save_row.addStretch()

        self._save_btn = QPushButton("💾  Save Settings")
        self._save_btn.setStyleSheet(
            "background-color: #cba6f7; color: #1e1e2e; font-weight: bold;"
            "padding: 10px 30px; font-size: 13px;"
        )
        self._save_btn.clicked.connect(self._save)
        save_row.addWidget(self._save_btn)
        save_row.addStretch()

        root.addLayout(save_row)

        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet("color: #a6e3a1; font-size: 11px;")
        root.addWidget(self._status_label)

        root.addStretch()

    # ── Load / save ───────────────────────────────────────────────────────────
    def _load_into_ui(self):
        """Populate the UI from the current settings."""
        self._url_list.clear()
        for url in settings.reddit_urls:
            self._add_item(url)
        self._pages_spin.setValue(settings.reddit_max_pages)
        self._workers_spin.setValue(settings.reddit_test_workers)

    def _save(self):
        """Validate, persist settings, and notify other tabs."""
        urls = self._current_urls()
        if not urls:
            QMessageBox.warning(
                self, "No URLs",
                "Add at least one Reddit channel URL before saving."
            )
            return

        settings.reddit_urls      = urls
        settings.reddit_max_pages = self._pages_spin.value()
        settings.reddit_test_workers = self._workers_spin.value()
        settings.save()

        self._status_label.setText("✔  Settings saved!")
        self.settings_saved.emit()

    # ── List management ───────────────────────────────────────────────────────
    def _add_url(self):
        raw = self._url_input.text().strip()
        if not raw:
            return

        if not _is_valid_reddit_input(raw):
            QMessageBox.warning(
                self, "Invalid URL",
                f"That doesn't look like a valid subreddit URL or name:\n\n{raw}\n\n"
                "Try something like:\n"
                "  https://www.reddit.com/r/IPTV_ZONENEW/\n"
                "  IPTV_ZONENEW"
            )
            return

        # Normalise to a clean display URL
        json_url    = extract_subreddit_json_url(raw)
        display_url = reddit_url_to_display(json_url)

        # Duplicate check
        existing = self._current_urls()
        if display_url in existing or json_url in existing:
            self._status_label.setText("Already in the list.")
            self._url_input.clear()
            return

        self._add_item(display_url)
        self._url_input.clear()
        self._status_label.setText(f"Added: {display_url}")

    def _add_item(self, display_url: str):
        item = QListWidgetItem(display_url)
        item.setForeground(QColor("#89b4fa"))
        self._url_list.addItem(item)

    def _remove_selected(self):
        for item in self._url_list.selectedItems():
            self._url_list.takeItem(self._url_list.row(item))
        if self._url_list.count() == 0:
            self._status_label.setText("⚠  No channels left — add at least one before saving.")

    def _current_urls(self) -> list:
        return [self._url_list.item(i).text()
                for i in range(self._url_list.count())]

    def _open_in_browser(self):
        for item in self._url_list.selectedItems():
            url = item.text()
            if not url.startswith("http"):
                url = "https://" + url
            QDesktopServices.openUrl(QUrl(url))


# ── Validation helper ─────────────────────────────────────────────────────────
def _is_valid_reddit_input(text: str) -> bool:
    """Return True if text looks like a subreddit URL or bare name."""
    # Full URL
    if "reddit.com/r/" in text:
        return True
    # /r/name or r/name
    if re.match(r'^/?r/[A-Za-z0-9_]{2,}', text):
        return True
    # Bare name: letters, digits, underscores
    if re.match(r'^[A-Za-z0-9_]{2,}$', text):
        return True
    return False
