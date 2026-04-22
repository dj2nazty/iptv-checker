"""Results tab — sortable table, filters, progress bar, export buttons."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTableView, QProgressBar,
    QHeaderView, QAbstractItemView, QMenu, QFileDialog,
    QApplication
)
from PyQt5.QtCore import Qt, QSortFilterProxyModel, QModelIndex, pyqtSignal
from models.channel import ChannelTableModel


class ChannelFilterProxy(QSortFilterProxyModel):
    """Proxy model for filtering channels by status, group, and name."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._status_filter = "All"
        self._group_filter = "All"
        self._search_text = ""

    def set_status_filter(self, status: str):
        self._status_filter = status
        self.invalidateFilter()

    def set_group_filter(self, group: str):
        self._group_filter = group
        self.invalidateFilter()

    def set_search_text(self, text: str):
        self._search_text = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        if not model:
            return True

        channel = model.get_channel(source_row)

        # Status filter
        if self._status_filter != "All":
            if channel.status != self._status_filter.lower():
                return False

        # Group filter
        if self._group_filter != "All":
            if channel.group != self._group_filter:
                return False

        # Search filter
        if self._search_text:
            if self._search_text not in channel.name.lower():
                return False

        return True


class ResultsTab(QWidget):
    """Tab displaying scan results in a filterable, sortable table."""

    export_csv_requested = pyqtSignal()
    export_m3u_requested = pyqtSignal()
    play_requested = pyqtSignal(str, str)  # (name, url)
    add_to_backup_requested = pyqtSignal(object)  # Channel object
    stop_scan_requested = pyqtSignal()
    clear_results_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = ChannelTableModel()
        self._proxy = ChannelFilterProxy()
        self._proxy.setSourceModel(self._model)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # --- Filter Bar ---
        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel("Status:"))
        self._status_combo = QComboBox()
        self._status_combo.addItems(["All", "Live", "Dead", "Timeout", "Error", "Pending"])
        self._status_combo.currentTextChanged.connect(self._proxy.set_status_filter)
        filter_layout.addWidget(self._status_combo)

        filter_layout.addWidget(QLabel("Group:"))
        self._group_combo = QComboBox()
        self._group_combo.addItem("All")
        self._group_combo.currentTextChanged.connect(self._proxy.set_group_filter)
        filter_layout.addWidget(self._group_combo)

        filter_layout.addWidget(QLabel("Search:"))
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Filter by name...")
        self._search_input.textChanged.connect(self._proxy.set_search_text)
        filter_layout.addWidget(self._search_input, 1)

        export_csv_btn = QPushButton("Export CSV")
        export_csv_btn.setObjectName("exportCsvBtn")
        export_csv_btn.clicked.connect(self.export_csv_requested.emit)
        filter_layout.addWidget(export_csv_btn)

        export_m3u_btn = QPushButton("Export Working M3U")
        export_m3u_btn.setObjectName("exportM3uBtn")
        export_m3u_btn.clicked.connect(self.export_m3u_requested.emit)
        filter_layout.addWidget(export_m3u_btn)

        self._stop_scan_btn = QPushButton("Stop Scan")
        self._stop_scan_btn.setStyleSheet(
            "background-color: #f38ba8; color: #1e1e2e; font-weight: bold; padding: 6px 14px;"
        )
        self._stop_scan_btn.setEnabled(False)
        self._stop_scan_btn.clicked.connect(self.stop_scan_requested.emit)
        filter_layout.addWidget(self._stop_scan_btn)

        self._clear_btn = QPushButton("Clear Results")
        self._clear_btn.setStyleSheet(
            "background-color: #9399b2; color: #1e1e2e; font-weight: bold; padding: 6px 14px;"
        )
        self._clear_btn.clicked.connect(self.clear_results_requested.emit)
        filter_layout.addWidget(self._clear_btn)

        layout.addLayout(filter_layout)

        # --- Stats Bar ---
        self._stats_label = QLabel("Total: 0 | Live: 0 | Dead: 0")
        self._stats_label.setObjectName("statsLabel")
        layout.addWidget(self._stats_label)

        # --- Table View ---
        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSortingEnabled(True)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.verticalHeader().setVisible(False)

        # Column sizing
        header = self._table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setDefaultSectionSize(100)
        # Name column wider
        header.resizeSection(1, 250)
        # Group column
        header.resizeSection(2, 150)

        layout.addWidget(self._table, 1)

        # --- Progress Bar ---
        self._progress = QProgressBar()
        self._progress.setFormat("Checking %v/%m streams... (%p%)")
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

    @property
    def model(self) -> ChannelTableModel:
        return self._model

    def set_channels(self, channels):
        self._model.set_channels(channels)
        self._update_groups(channels)
        self._update_stats()

    def update_channel(self, row, channel):
        self._model.update_channel(row, channel)
        self._update_stats()

    def _update_groups(self, channels):
        """Populate group filter combo with unique groups."""
        groups = sorted(set(ch.group for ch in channels if ch.group))
        current = self._group_combo.currentText()
        self._group_combo.blockSignals(True)
        self._group_combo.clear()
        self._group_combo.addItem("All")
        self._group_combo.addItems(groups)
        # Restore selection if possible
        idx = self._group_combo.findText(current)
        if idx >= 0:
            self._group_combo.setCurrentIndex(idx)
        self._group_combo.blockSignals(False)

    def _update_stats(self):
        channels = self._model.get_all_channels()
        total = len(channels)
        live = sum(1 for c in channels if c.status == "live")
        dead = sum(1 for c in channels if c.status == "dead")
        timeout = sum(1 for c in channels if c.status == "timeout")
        error = sum(1 for c in channels if c.status == "error")
        pending = sum(1 for c in channels if c.status == "pending")
        self._stats_label.setText(
            f"Total: {total} | Live: {live} | Dead: {dead} | "
            f"Timeout: {timeout} | Error: {error} | Pending: {pending}"
        )

    def set_progress(self, current, total):
        self._progress.setVisible(True)
        self._progress.setMaximum(total)
        self._progress.setValue(current)

    def finish_progress(self):
        self._progress.setFormat("Scan complete! (%v/%m)")
        self._update_stats()

    def hide_progress(self):
        self._progress.setVisible(False)

    def set_scanning(self, is_scanning: bool):
        self._stop_scan_btn.setEnabled(is_scanning)

    def clear_all(self):
        """Clear all results and reset the table."""
        self._model.set_channels([])
        self._group_combo.blockSignals(True)
        self._group_combo.clear()
        self._group_combo.addItem("All")
        self._group_combo.blockSignals(False)
        self._status_combo.setCurrentIndex(0)
        self._search_input.clear()
        self._stats_label.setText("Total: 0 | Live: 0 | Dead: 0")
        self._progress.setVisible(False)

    def _show_context_menu(self, pos):
        index = self._table.indexAt(pos)
        if not index.isValid():
            return

        # Map proxy index to source
        source_index = self._proxy.mapToSource(index)
        channel = self._model.get_channel(source_index.row())

        menu = QMenu(self)
        play_action = menu.addAction("Play Channel")
        add_backup = menu.addAction("Add to Backup Playlist")
        menu.addSeparator()
        copy_url = menu.addAction("Copy Stream URL")

        action = menu.exec_(self._table.viewport().mapToGlobal(pos))
        if action == play_action and channel.stream_url:
            self.play_requested.emit(channel.name, channel.stream_url)
        elif action == add_backup:
            self.add_to_backup_requested.emit(channel)
        elif action == copy_url:
            QApplication.clipboard().setText(channel.stream_url)
