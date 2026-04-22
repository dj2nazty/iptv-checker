"""Active Backup tab — stores good/active links found during bulk testing.

Allows browsing, playing, removing, saving to .txt, and loading from .txt.
Supports multi-select to append chosen links to an existing backup .txt file."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QHeaderView, QAbstractItemView,
    QMenu, QApplication, QFileDialog, QMessageBox, QCheckBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor

from core.bulk_tester import LinkResult


class ActiveBackupTab(QWidget):
    """Tab that stores all active/good links found during bulk testing."""

    play_link_requested = pyqtSignal(str)  # m3u_url to load into results & play

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[dict] = []  # list of dicts with link info
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # --- Top bar ---
        top_bar = QHBoxLayout()

        self._stats_label = QLabel("Active Backup: 0 links saved")
        self._stats_label.setObjectName("statsLabel")
        top_bar.addWidget(self._stats_label, 1)

        select_all_btn = QPushButton("Select All")
        select_all_btn.setStyleSheet(
            "background-color: #cba6f7; color: #1e1e2e; font-weight: bold; padding: 6px 14px;"
        )
        select_all_btn.clicked.connect(self._select_all)
        top_bar.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self._deselect_all)
        top_bar.addWidget(deselect_all_btn)

        layout.addLayout(top_bar)

        # --- Action bar ---
        action_bar = QHBoxLayout()

        add_to_file_btn = QPushButton("Add Selected to Backup File")
        add_to_file_btn.setStyleSheet(
            "background-color: #f9e2af; color: #1e1e2e; font-weight: bold; padding: 8px 18px;"
        )
        add_to_file_btn.clicked.connect(self._add_selected_to_file)
        action_bar.addWidget(add_to_file_btn)

        save_btn = QPushButton("Save All to New .txt")
        save_btn.setStyleSheet(
            "background-color: #a6e3a1; color: #1e1e2e; font-weight: bold; padding: 6px 14px;"
        )
        save_btn.clicked.connect(self._save_to_file)
        action_bar.addWidget(save_btn)

        load_btn = QPushButton("Load from .txt")
        load_btn.setStyleSheet(
            "background-color: #89b4fa; color: #1e1e2e; font-weight: bold; padding: 6px 14px;"
        )
        load_btn.clicked.connect(self._load_from_file)
        action_bar.addWidget(load_btn)

        action_bar.addStretch()

        remove_sel_btn = QPushButton("Remove Selected")
        remove_sel_btn.setStyleSheet(
            "background-color: #f38ba8; color: #1e1e2e; font-weight: bold; padding: 6px 14px;"
        )
        remove_sel_btn.clicked.connect(self._remove_selected)
        action_bar.addWidget(remove_sel_btn)

        clear_btn = QPushButton("Clear All")
        clear_btn.setStyleSheet(
            "background-color: #9399b2; color: #1e1e2e; font-weight: bold; padding: 6px 14px;"
        )
        clear_btn.clicked.connect(self._clear_all)
        action_bar.addWidget(clear_btn)

        layout.addLayout(action_bar)

        # --- Table ---
        self._table = QTableWidget()
        self._table.setColumnCount(10)
        self._table.setHorizontalHeaderLabels([
            "\u2714", "#", "Server", "Username", "Status", "Expiry",
            "Live Ch", "VOD", "Connections", "M3U URL"
        ])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.doubleClicked.connect(self._on_double_click)

        header = self._table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.resizeSection(0, 40)   # checkbox
        header.resizeSection(1, 35)   # #
        header.resizeSection(2, 200)  # Server
        header.resizeSection(3, 140)  # Username
        header.resizeSection(4, 70)   # Status
        header.resizeSection(5, 130)  # Expiry
        header.resizeSection(6, 65)   # Live Ch
        header.resizeSection(7, 50)   # VOD
        header.resizeSection(8, 100)  # Connections

        layout.addWidget(self._table, 1)

        # --- Bottom info ---
        self._selection_label = QLabel(
            "Check the boxes to select links, then click 'Add Selected to Backup File' to append them to an existing .txt"
        )
        self._selection_label.setObjectName("statsLabel")
        self._selection_label.setStyleSheet("color: #a6adc8; font-size: 11px;")
        layout.addWidget(self._selection_label)

    def add_active_link(self, result: LinkResult):
        """Add an active link from bulk testing. Skips duplicates."""
        for entry in self._entries:
            if entry["server"] == result.server and entry["username"] == result.username:
                return

        entry = {
            "server": result.server,
            "username": result.username,
            "password": result.password,
            "status": result.account_status or "Active",
            "expiry": result.expiry,
            "live_channels": result.live_channels,
            "vod_count": result.vod_count,
            "max_connections": result.max_connections,
            "active_connections": result.active_connections,
            "m3u_url": result.m3u_url,
            "raw_line": result.raw_line,
        }
        self._entries.append(entry)
        self._rebuild_table()

    def _rebuild_table(self):
        """Rebuild the table from the entries list."""
        self._table.setRowCount(len(self._entries))
        for row, entry in enumerate(self._entries):
            # Checkbox column
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk_item.setCheckState(Qt.Unchecked)
            self._table.setItem(row, 0, chk_item)

            data = [
                str(row + 1),
                entry["server"],
                entry["username"],
                entry["status"],
                entry["expiry"],
                str(entry["live_channels"]) if entry["live_channels"] else "\u2014",
                str(entry["vod_count"]) if entry["vod_count"] else "\u2014",
                f"{entry.get('active_connections', 0)}/{entry['max_connections']}" if entry["max_connections"] else "\u2014",
                entry["m3u_url"],
            ]
            for col, text in enumerate(data):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if col == 3:  # Status column
                    item.setForeground(QColor("#a6e3a1"))
                self._table.setItem(row, col + 1, item)

        self._stats_label.setText(f"Active Backup: {len(self._entries)} links saved")
        self._update_selection_count()

    def _get_checked_rows(self) -> list[int]:
        """Return list of row indices that are checked."""
        checked = []
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                checked.append(row)
        return checked

    def _update_selection_count(self):
        checked = self._get_checked_rows()
        if checked:
            self._selection_label.setText(
                f"{len(checked)} link(s) selected — click 'Add Selected to Backup File' to append to existing .txt"
            )
        else:
            self._selection_label.setText(
                "Check the boxes to select links, then click 'Add Selected to Backup File' to append them to an existing .txt"
            )

    def _select_all(self):
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked)
        self._update_selection_count()

    def _deselect_all(self):
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item:
                item.setCheckState(Qt.Unchecked)
        self._update_selection_count()

    def _add_selected_to_file(self):
        """Append only the checked/selected links to an existing backup .txt file."""
        checked = self._get_checked_rows()
        if not checked:
            QMessageBox.warning(self, "No Selection", "Check the boxes next to the links you want to add.")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Choose Backup File to Append To",
            "active_links.txt", "Text Files (*.txt);;All Files (*)"
        )
        if not filepath:
            return

        # Read existing content to avoid duplicates
        existing_lines = set()
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        existing_lines.add(line.lower())
        except FileNotFoundError:
            pass

        added = 0
        skipped = 0
        with open(filepath, "a", encoding="utf-8") as f:
            for row in checked:
                if row >= len(self._entries):
                    continue
                entry = self._entries[row]
                line = f"{entry['server']}|{entry['username']}|{entry.get('password', '')}"
                if line.lower() in existing_lines:
                    skipped += 1
                    continue
                f.write(line + "\n")
                existing_lines.add(line.lower())
                added += 1

        msg = f"Added {added} link(s) to:\n{filepath}"
        if skipped:
            msg += f"\n({skipped} duplicate(s) skipped)"
        QMessageBox.information(self, "Done", msg)

    def _remove_selected(self):
        """Remove only the checked rows."""
        checked = self._get_checked_rows()
        if not checked:
            QMessageBox.warning(self, "No Selection", "Check the boxes next to the links you want to remove.")
            return

        reply = QMessageBox.question(
            self, "Remove Selected",
            f"Remove {len(checked)} selected link(s) from backup?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # Remove in reverse order to preserve indices
        for row in sorted(checked, reverse=True):
            if row < len(self._entries):
                self._entries.pop(row)
        self._rebuild_table()

    def _on_double_click(self, index):
        row = index.row()
        col = index.column()
        # If they clicked the checkbox column, toggle it
        if col == 0:
            item = self._table.item(row, 0)
            if item:
                new_state = Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
                item.setCheckState(new_state)
                self._update_selection_count()
            return
        # Otherwise load the link
        if 0 <= row < len(self._entries):
            m3u_url = self._entries[row]["m3u_url"]
            if m3u_url:
                self.play_link_requested.emit(m3u_url)

    def _show_context_menu(self, pos):
        row = self._table.rowAt(pos.y())
        if row < 0 or row >= len(self._entries):
            return

        entry = self._entries[row]
        menu = QMenu(self)

        check_action = menu.addAction("Toggle Checkbox")
        menu.addSeparator()
        load_action = menu.addAction("Load Channels from This Link")
        copy_m3u = menu.addAction("Copy M3U URL")
        copy_creds = menu.addAction("Copy Credentials (server|user|pass)")
        menu.addSeparator()
        remove_action = menu.addAction("Remove from Backup")

        action = menu.exec_(self._table.viewport().mapToGlobal(pos))
        if action == check_action:
            item = self._table.item(row, 0)
            if item:
                new_state = Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
                item.setCheckState(new_state)
                self._update_selection_count()
        elif action == load_action and entry["m3u_url"]:
            self.play_link_requested.emit(entry["m3u_url"])
        elif action == copy_m3u:
            QApplication.clipboard().setText(entry["m3u_url"])
        elif action == copy_creds:
            creds = f"{entry['server']}|{entry['username']}|{entry.get('password', '')}"
            QApplication.clipboard().setText(creds)
        elif action == remove_action:
            self._entries.pop(row)
            self._rebuild_table()

    def _save_to_file(self):
        """Save all active links to a new .txt file."""
        if not self._entries:
            QMessageBox.warning(self, "Empty", "No active links to save.")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Active Links",
            "active_links.txt", "Text Files (*.txt);;All Files (*)"
        )
        if not filepath:
            return

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# IPTV Checker \u2014 Active Links Backup\n")
            f.write(f"# {len(self._entries)} active links\n\n")
            for entry in self._entries:
                f.write(f"{entry['server']}|{entry['username']}|{entry.get('password', '')}\n")

        QMessageBox.information(
            self, "Saved",
            f"Saved {len(self._entries)} active links to:\n{filepath}"
        )

    def _load_from_file(self):
        """Load previously saved active links from a .txt file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load Active Links",
            "", "Text Files (*.txt);;All Files (*)"
        )
        if not filepath:
            return

        loaded = 0
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Parse pipe-separated: server|username|password
                parts = line.split("|")
                if len(parts) >= 3:
                    server = parts[0].strip()
                    username = parts[1].strip()
                    password = parts[2].strip()
                elif "get.php" in line:
                    from urllib.parse import urlparse, parse_qs
                    parsed = urlparse(line)
                    params = parse_qs(parsed.query)
                    server = f"{parsed.scheme}://{parsed.hostname}"
                    if parsed.port:
                        server += f":{parsed.port}"
                    username = params.get("username", [""])[0]
                    password = params.get("password", [""])[0]
                else:
                    continue

                # Check for duplicate
                is_dup = any(
                    e["server"] == server and e["username"] == username
                    for e in self._entries
                )
                if is_dup:
                    continue

                m3u_url = f"{server}/get.php?username={username}&password={password}&type=m3u_plus"
                entry = {
                    "server": server,
                    "username": username,
                    "password": password,
                    "status": "Loaded",
                    "expiry": "\u2014",
                    "live_channels": 0,
                    "vod_count": 0,
                    "max_connections": 0,
                    "active_connections": 0,
                    "m3u_url": m3u_url,
                    "raw_line": line,
                }
                self._entries.append(entry)
                loaded += 1

        self._rebuild_table()
        QMessageBox.information(
            self, "Loaded",
            f"Loaded {loaded} links from file.\nTotal: {len(self._entries)} links in backup."
        )

    def _clear_all(self):
        """Clear all backup entries."""
        if self._entries:
            reply = QMessageBox.question(
                self, "Clear Backup",
                f"Remove all {len(self._entries)} active links from backup?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        self._entries.clear()
        self._rebuild_table()
