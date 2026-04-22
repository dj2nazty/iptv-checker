"""Reddit IPTV Tab — scans r/IPTV_ZONENEW, decodes base64 credentials,
tests connections, and displays results sorted by post date."""
from __future__ import annotations

import json
import os
import threading

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QProgressBar, QSpinBox, QComboBox, QMenu, QApplication,
    QMessageBox, QFileDialog, QCheckBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QUrl, QTimer
from PyQt5.QtGui import QColor, QDesktopServices, QFont

from core.reddit_scraper import RedditEntry, RedditScraper, RedditTester
from utils.app_settings import settings, extract_subreddit_json_url

# Persistent cache next to the app's root
_HERE     = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_HERE)
CACHE_FILE = os.path.join(_APP_ROOT, "reddit_cache.json")

# ── Status colours (Catppuccin Mocha palette) ─────────────────────────────────
STATUS_COLORS = {
    "active":   "#a6e3a1",   # green
    "expired":  "#fab387",   # peach
    "blocked":  "#f38ba8",   # red
    "dead":     "#6c7086",   # overlay0 (grey)
    "error":    "#f38ba8",   # red
    "untested": "#cdd6f4",   # text (white-ish)
}


class RedditTab(QWidget):
    """Tab that scrapes, decodes, and displays IPTV credentials from Reddit."""

    # Emitted when the user wants to load a link into the Results tab
    load_link_requested = pyqtSignal(str)   # m3u_url

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list     = []
        self._entry_keys: set   = set()   # O(1) dedup — mirrors unique_key() of _entries
        self._scraper  = RedditScraper(self)
        self._tester   = RedditTester(self)
        self._testing  = False
        self._scanning = False

        # ── Debounce timer ─────────────────────────────────────────────────────
        # Instead of rebuilding the table on every single entry arrival (which
        # causes exponential slowdown when a paste has 50+ credentials), we wait
        # 350 ms after the last entry before doing ONE rebuild.
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(350)
        self._rebuild_timer.timeout.connect(self._rebuild_table)

        self._setup_ui()
        self._connect_signals()
        self._load_cache()

    # ── UI setup ──────────────────────────────────────────────────────────────
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ── Top toolbar ──────────────────────────────────────────────────────
        toolbar = QHBoxLayout()

        self._scan_btn = QPushButton("🔍  Scan Reddit")
        self._scan_btn.setStyleSheet(
            "background-color: #cba6f7; color: #1e1e2e; font-weight: bold; padding: 8px 18px;")
        self._scan_btn.clicked.connect(self._start_scan)
        toolbar.addWidget(self._scan_btn)

        self._stop_btn = QPushButton("⏹  Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet(
            "background-color: #f38ba8; color: #1e1e2e; font-weight: bold; padding: 8px 14px;")
        self._stop_btn.clicked.connect(self._stop_all)
        toolbar.addWidget(self._stop_btn)

        toolbar.addWidget(QLabel("Pages:"))
        self._pages_spin = QSpinBox()
        self._pages_spin.setRange(1, 20)
        self._pages_spin.setValue(5)
        self._pages_spin.setToolTip("Reddit pages to scan (100 posts per page)")
        toolbar.addWidget(self._pages_spin)

        toolbar.addSpacing(12)

        self._test_sel_btn = QPushButton("⚡  Test Selected")
        self._test_sel_btn.setStyleSheet(
            "background-color: #f9e2af; color: #1e1e2e; font-weight: bold; padding: 8px 14px;")
        self._test_sel_btn.clicked.connect(self._test_selected)
        toolbar.addWidget(self._test_sel_btn)

        self._test_all_btn = QPushButton("⚡  Test All Untested")
        self._test_all_btn.setStyleSheet(
            "background-color: #f9e2af; color: #1e1e2e; font-weight: bold; padding: 8px 14px;")
        self._test_all_btn.clicked.connect(self._test_all_untested)
        toolbar.addWidget(self._test_all_btn)

        toolbar.addSpacing(12)

        self._save_btn = QPushButton("💾  Save")
        self._save_btn.clicked.connect(self._save_cache)
        toolbar.addWidget(self._save_btn)

        self._load_file_btn = QPushButton("📂  Load")
        self._load_file_btn.clicked.connect(self._load_from_file)
        toolbar.addWidget(self._load_file_btn)

        self._clear_btn = QPushButton("🗑  Clear All")
        self._clear_btn.setStyleSheet(
            "background-color: #9399b2; color: #1e1e2e; font-weight: bold; padding: 8px 12px;")
        self._clear_btn.clicked.connect(self._clear_all)
        toolbar.addWidget(self._clear_btn)

        toolbar.addStretch()
        root.addLayout(toolbar)

        # ── Filter bar ───────────────────────────────────────────────────────
        filter_bar = QHBoxLayout()

        filter_bar.addWidget(QLabel("Filter:"))
        self._status_filter = QComboBox()
        self._status_filter.addItems(["All", "active", "untested", "expired", "blocked", "dead", "error"])
        self._status_filter.currentIndexChanged.connect(self._apply_filter)
        filter_bar.addWidget(self._status_filter)

        filter_bar.addSpacing(10)

        filter_bar.addWidget(QLabel("Sort by:"))
        self._sort_combo = QComboBox()
        self._sort_combo.addItems(["Date (newest)", "Date (oldest)", "Status", "Server"])
        self._sort_combo.currentIndexChanged.connect(self._rebuild_table)
        filter_bar.addWidget(self._sort_combo)

        filter_bar.addStretch()

        self._stats_label = QLabel("0 credentials found")
        self._stats_label.setStyleSheet("color: #cba6f7; font-weight: bold;")
        filter_bar.addWidget(self._stats_label)

        root.addLayout(filter_bar)

        # ── Progress bar ──────────────────────────────────────────────────────
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        self._progress_bar.setFixedHeight(14)
        root.addWidget(self._progress_bar)

        self._status_label = QLabel("Ready — click 'Scan Reddit' to fetch credentials from r/IPTV_ZONENEW")
        self._status_label.setStyleSheet("color: #a6adc8; font-size: 11px;")
        root.addWidget(self._status_label)

        # ── Table ─────────────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(11)
        self._table.setHorizontalHeaderLabels([
            "✓", "#", "Date Posted", "Post Title",
            "Server", "Username", "Password",
            "Status", "Active/Max", "Expiry", "Live Ch"
        ])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.doubleClicked.connect(self._on_double_click)

        hdr = self._table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)   # Post Title stretches
        hdr.resizeSection(0,  38)   # ✓
        hdr.resizeSection(1,  35)   # #
        hdr.resizeSection(2, 130)   # Date
        hdr.resizeSection(4, 190)   # Server
        hdr.resizeSection(5, 110)   # Username
        hdr.resizeSection(6, 110)   # Password
        hdr.resizeSection(7,  75)   # Status
        hdr.resizeSection(8,  85)   # Active/Max
        hdr.resizeSection(9, 130)   # Expiry
        hdr.resizeSection(10, 60)   # Live Ch

        root.addWidget(self._table, 1)

        # ── Bottom hint ───────────────────────────────────────────────────────
        hint = QLabel(
            "Double-click a row to load its M3U into Results  |  Right-click for more options  "
            "|  Credentials auto-save on scan complete"
        )
        hint.setStyleSheet("color: #6c7086; font-size: 10px;")
        root.addWidget(hint)

    # ── Signal wiring ─────────────────────────────────────────────────────────
    def _connect_signals(self):
        self._scraper.entry_found.connect(self._on_entry_found)
        self._scraper.progress.connect(self._on_scan_progress)
        self._scraper.finished.connect(self._on_scan_finished)
        self._scraper.scrape_error.connect(self._on_error)

        self._tester.entry_tested.connect(self._on_entry_tested)
        self._tester.test_progress.connect(self._on_test_progress)
        self._tester.test_finished.connect(self._on_test_finished)

    # ── Scan ──────────────────────────────────────────────────────────────────
    def _start_scan(self):
        if self._scanning:
            return
        self._scanning = True
        self._scan_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)   # indeterminate

        # Build .json API URLs from saved settings
        json_urls = [extract_subreddit_json_url(u) for u in settings.reddit_urls]
        sub_names = [u.split("/r/")[-1].split("/")[0] for u in json_urls]
        self._status_label.setText(
            f"Connecting to Reddit — scanning: {', '.join(sub_names)}…"
        )
        self._scraper.start(
            max_pages=self._pages_spin.value(),
            reddit_json_urls=json_urls,
        )

    def on_settings_changed(self):
        """Called by MainWindow when the user saves settings."""
        self._pages_spin.setValue(settings.reddit_max_pages)
        names = []
        for url in settings.reddit_urls:
            if "/r/" in url:
                names.append(url.split("/r/")[-1].strip("/"))
            else:
                names.append(url)
        self._status_label.setText(
            f"Settings updated — will scan: {', '.join(names)}"
        )

    def _stop_all(self):
        self._scraper.stop()
        self._tester.stop()
        self._stop_btn.setEnabled(False)
        self._status_label.setText("Stopping…")

    def _on_scan_progress(self, current: int, total: int, msg: str):
        if total > 0:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(current)
        self._status_label.setText(msg)

    def _on_scan_finished(self, summary: str):
        self._scanning = False
        self._scan_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._progress_bar.setVisible(False)
        self._status_label.setText(summary)

        # Flush any pending debounced rebuild first
        if self._rebuild_timer.isActive():
            self._rebuild_timer.stop()
            self._rebuild_table()

        # Save to disk in a background thread so the UI stays responsive
        self._save_cache_async()

    def _on_error(self, msg: str):
        self._status_label.setText(f"Error: {msg}")

    # ── Entry received from scraper ───────────────────────────────────────────
    def _on_entry_found(self, entry: RedditEntry):
        """Called on the UI thread for every new credential the scraper finds.

        KEY FIX: previously this called _rebuild_table() on every single entry,
        causing 50+ full table rebuilds when a paste.sh paste decrypts many
        credentials at once — freezing the UI.  Now we:
          1. Use a set for O(1) dedup (was O(n) linear scan).
          2. Append the entry to the list immediately.
          3. Schedule ONE debounced rebuild 350 ms after the last arrival.
        """
        key = entry.unique_key()
        if key in self._entry_keys:         # O(1) — no more linear scan
            return
        self._entry_keys.add(key)
        self._entries.append(entry)
        # Start (or restart) the 350 ms debounce timer.
        # If 50 entries arrive in 100 ms, the timer resets each time and only
        # fires once — 350 ms after the final entry. One rebuild total.
        self._rebuild_timer.start()

    # ── Testing ───────────────────────────────────────────────────────────────
    def _test_selected(self):
        rows = self._checked_rows() or self._selected_rows()
        if not rows:
            QMessageBox.information(self, "Select rows", "Check or select rows to test.")
            return
        vis = self._visible_entries()       # compute once, not once per row
        entries = [vis[r] for r in rows if r < len(vis)]
        indices = rows[:len(entries)]
        self._start_testing(entries, indices)

    def _test_all_untested(self):
        vis = self._visible_entries()
        indices = [i for i, e in enumerate(vis) if e.status == "untested"]
        entries = [vis[i] for i in indices]
        if not entries:
            QMessageBox.information(self, "Nothing to test", "No untested entries found.")
            return
        self._start_testing(entries, indices)

    def _start_testing(self, entries: list, indices: list):
        if self._testing:
            return
        self._testing = True
        self._stop_btn.setEnabled(True)
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, len(entries))
        self._progress_bar.setValue(0)
        self._status_label.setText(f"Testing {len(entries)} credential(s)…")

        # Map visible table rows → actual master-list indices
        vis = self._visible_entries()
        real_indices = []
        for vi in indices:
            if vi < len(vis):
                entry = vis[vi]
                try:
                    real_indices.append(self._entries.index(entry))
                except ValueError:
                    real_indices.append(vi)

        self._tester.start(entries, real_indices)

    def _on_test_progress(self, current: int, total: int):
        self._progress_bar.setValue(current)
        self._status_label.setText(f"Testing… {current}/{total}")

    def _on_entry_tested(self, index: int, entry: RedditEntry):
        """Update the master list and refresh only the matching table row."""
        if 0 <= index < len(self._entries):
            self._entries[index] = entry

        # Update only the one affected row — no full rebuild needed
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 1)
            if item and item.data(Qt.UserRole) == index:
                self._populate_row(row, entry, index)
                break

    def _on_test_finished(self):
        self._testing = False
        self._stop_btn.setEnabled(False)
        self._progress_bar.setVisible(False)
        active = sum(1 for e in self._entries if e.status == "active")
        self._status_label.setText(
            f"Testing done! {active} active of {len(self._entries)} total.")
        self._save_cache_async()

    # ── Table management ─────────────────────────────────────────────────────
    def _visible_entries(self) -> list:
        """Return entries that pass the current status filter, in sort order."""
        sf = self._status_filter.currentText()
        filtered = [e for e in self._entries if sf == "All" or e.status == sf]

        sort_idx = self._sort_combo.currentIndex()
        if sort_idx == 0:    # newest first
            filtered.sort(key=lambda e: e.post_timestamp, reverse=True)
        elif sort_idx == 1:  # oldest first
            filtered.sort(key=lambda e: e.post_timestamp)
        elif sort_idx == 2:  # by status
            order = {"active": 0, "expired": 1, "blocked": 2,
                     "dead": 3, "error": 4, "untested": 5}
            filtered.sort(key=lambda e: (order.get(e.status, 9), -e.post_timestamp))
        elif sort_idx == 3:  # by server
            filtered.sort(key=lambda e: e.server.lower())

        return filtered

    def _rebuild_table(self):
        """Repopulate the table from scratch.

        Wrapped with viewport.setUpdatesEnabled(False/True) so Qt only redraws
        once at the end, not once per cell — critical for 500+ row tables.
        """
        vis = self._visible_entries()

        vp = self._table.viewport()
        vp.setUpdatesEnabled(False)
        try:
            self._table.setRowCount(len(vis))
            for row, entry in enumerate(vis):
                real_idx = self._entries.index(entry) if entry in self._entries else row
                self._populate_row(row, entry, real_idx)
        finally:
            vp.setUpdatesEnabled(True)

        total    = len(self._entries)
        active   = sum(1 for e in self._entries if e.status == "active")
        untested = sum(1 for e in self._entries if e.status == "untested")
        self._stats_label.setText(
            f"{total} found  |  {active} active  |  {untested} untested"
        )

    def _apply_filter(self):
        self._rebuild_table()

    def _populate_row(self, row: int, entry: RedditEntry, real_idx: int):
        """Fill one table row with entry data — reuses existing items where possible."""
        # Col 0: checkbox (only create once)
        chk = self._table.item(row, 0)
        if chk is None:
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Unchecked)
            self._table.setItem(row, 0, chk)

        def _cell(text: str, col: int, color: str = "", bold: bool = False):
            item = self._table.item(row, col)
            if item is None:
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(row, col, item)
            else:
                item.setText(text)
            if color:
                item.setForeground(QColor(color))
            if bold:
                f = item.font(); f.setBold(True); item.setFont(f)
            if col == 1:
                item.setData(Qt.UserRole, real_idx)

        _cell(str(row + 1),              1)
        _cell(entry.post_date,           2)
        _cell(entry.post_title,          3)
        _cell(entry.server,              4)
        _cell(entry.username,            5)
        _cell(entry.password,            6)

        status_color = STATUS_COLORS.get(entry.status, "#cdd6f4")
        _cell(entry.status,              7, color=status_color, bold=True)

        cons = (f"{entry.active_connections}/{entry.max_connections}"
                if entry.max_connections else "—")
        _cell(cons,                      8)
        _cell(entry.expiry or "—",       9)
        _cell(str(entry.live_channels) if entry.live_channels else "—", 10)

    # ── Interaction ───────────────────────────────────────────────────────────
    def _on_double_click(self, index):
        row = index.row()
        vis = self._visible_entries()
        if 0 <= row < len(vis) and vis[row].m3u_url:
            self.load_link_requested.emit(vis[row].m3u_url)

    def _show_context_menu(self, pos):
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        vis = self._visible_entries()
        if row >= len(vis):
            return
        entry = vis[row]

        menu = QMenu(self)
        load_act   = menu.addAction("📺  Load Channels (double-click)")
        open_post  = menu.addAction("🌐  Open Reddit Post in Browser")
        menu.addSeparator()
        copy_creds = menu.addAction("📋  Copy Credentials (server|user|pass)")
        copy_m3u   = menu.addAction("📋  Copy M3U URL")
        copy_user  = menu.addAction("📋  Copy Username")
        copy_pass  = menu.addAction("📋  Copy Password")
        menu.addSeparator()
        test_act   = menu.addAction("⚡  Test This Credential")
        menu.addSeparator()
        del_act    = menu.addAction("🗑  Remove from List")

        action = menu.exec_(self._table.viewport().mapToGlobal(pos))
        clip = QApplication.clipboard()

        if action == load_act and entry.m3u_url:
            self.load_link_requested.emit(entry.m3u_url)
        elif action == open_post:
            QDesktopServices.openUrl(QUrl(entry.post_url))
        elif action == copy_creds:
            clip.setText(f"{entry.server}|{entry.username}|{entry.password}")
        elif action == copy_m3u:
            clip.setText(entry.m3u_url)
        elif action == copy_user:
            clip.setText(entry.username)
        elif action == copy_pass:
            clip.setText(entry.password)
        elif action == test_act:
            self._start_testing([entry], [row])
        elif action == del_act:
            key = entry.unique_key()
            self._entry_keys.discard(key)
            if entry in self._entries:
                self._entries.remove(entry)
            self._rebuild_table()

    def _checked_rows(self) -> list:
        return [r for r in range(self._table.rowCount())
                if (self._table.item(r, 0) or _dummy()).checkState() == Qt.Checked]

    def _selected_rows(self) -> list:
        return list({idx.row() for idx in self._table.selectedIndexes()})

    # ── Persistence ───────────────────────────────────────────────────────────
    def _save_cache(self):
        """Synchronous save — used when the user explicitly clicks Save."""
        try:
            data = {
                "version": 1,
                "entries": [e.to_dict() for e in self._entries],
            }
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            self._status_label.setText(f"Save failed: {exc}")

    def _save_cache_async(self):
        """Save to disk in a background thread so the UI stays responsive."""
        entries_snapshot = [e.to_dict() for e in self._entries]  # snapshot on UI thread

        def _write():
            try:
                data = {"version": 1, "entries": entries_snapshot}
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass  # non-critical — user can always click Save manually

        threading.Thread(target=_write, daemon=True).start()

    def _load_cache(self):
        if not os.path.exists(CACHE_FILE):
            return
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = [RedditEntry.from_dict(d) for d in data.get("entries", [])]
            added = 0
            for e in entries:
                k = e.unique_key()
                if k not in self._entry_keys:
                    self._entry_keys.add(k)
                    self._entries.append(e)
                    added += 1
            if added:
                self._rebuild_table()
                self._status_label.setText(f"Loaded {added} saved credential(s) from cache.")
        except Exception as exc:
            self._status_label.setText(f"Cache load failed: {exc}")

    def _load_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Reddit Cache", "", "JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = [RedditEntry.from_dict(d) for d in data.get("entries", [])]
            added = 0
            for e in entries:
                k = e.unique_key()
                if k not in self._entry_keys:
                    self._entry_keys.add(k)
                    self._entries.append(e)
                    added += 1
            self._rebuild_table()
            QMessageBox.information(self, "Loaded", f"Added {added} new credential(s).")
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _clear_all(self):
        if not self._entries:
            return
        if QMessageBox.question(
            self, "Clear All",
            f"Remove all {len(self._entries)} credential(s)?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            self._entries.clear()
            self._entry_keys.clear()        # keep the set in sync
            self._rebuild_table()
            self._save_cache_async()


# ── tiny helper ──────────────────────────────────────────────────────────────
def _dummy() -> QTableWidgetItem:
    """Return an unchecked dummy item (used as fallback)."""
    i = QTableWidgetItem()
    i.setCheckState(Qt.Unchecked)
    return i
