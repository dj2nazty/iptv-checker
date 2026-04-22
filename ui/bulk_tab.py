"""Bulk results tab — shows test results for multiple links."""
from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QProgressBar, QPushButton, QHeaderView,
    QAbstractItemView, QMenu, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor

from core.bulk_tester import LinkResult


class BulkTab(QWidget):
    """Tab showing bulk link test results."""

    load_link_requested = pyqtSignal(str)  # m3u_url to load into main results
    stop_bulk_requested = pyqtSignal()
    clear_bulk_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._results: list[LinkResult] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Top bar with stats + buttons
        top_bar = QHBoxLayout()

        self._stats_label = QLabel("No bulk test run yet")
        self._stats_label.setObjectName("statsLabel")
        top_bar.addWidget(self._stats_label, 1)

        self._stop_btn = QPushButton("Stop Test")
        self._stop_btn.setStyleSheet(
            "background-color: #f38ba8; color: #1e1e2e; font-weight: bold; padding: 6px 14px;"
        )
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.stop_bulk_requested.emit)
        top_bar.addWidget(self._stop_btn)

        self._clear_btn = QPushButton("Clear Results")
        self._clear_btn.setStyleSheet(
            "background-color: #9399b2; color: #1e1e2e; font-weight: bold; padding: 6px 14px;"
        )
        self._clear_btn.clicked.connect(self.clear_bulk_requested.emit)
        top_bar.addWidget(self._clear_btn)

        layout.addLayout(top_bar)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(10)
        self._table.setHorizontalHeaderLabels([
            "#", "Server", "Username", "Status", "Account",
            "Expiry", "Live Ch", "VOD", "Connections", "Error"
        ])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)

        header = self._table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.resizeSection(0, 40)   # #
        header.resizeSection(1, 200)  # Server
        header.resizeSection(2, 150)  # Username
        header.resizeSection(3, 80)   # Status
        header.resizeSection(4, 80)   # Account
        header.resizeSection(5, 140)  # Expiry
        header.resizeSection(6, 70)   # Live Ch
        header.resizeSection(7, 50)   # VOD
        header.resizeSection(8, 100)  # Connections

        layout.addWidget(self._table, 1)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setFormat("Testing %v/%m links... (%p%)")
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

    def clear(self):
        self._table.setRowCount(0)
        self._results.clear()

    def set_row_count(self, count: int):
        self._table.setRowCount(count)
        self._results = [None] * count
        # Fill with pending
        for i in range(count):
            self._set_row(i, None)

    def update_result(self, index: int, result: LinkResult):
        if index < len(self._results):
            self._results[index] = result
            self._set_row(index, result)
            self._update_stats()

    def _set_row(self, row: int, result: LinkResult | None):
        if result is None:
            for col in range(self._table.columnCount()):
                item = QTableWidgetItem("..." if col > 0 else str(row + 1))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(row, col, item)
            return

        STATUS_COLORS = {
            "active": QColor("#a6e3a1"),
            "expired": QColor("#fab387"),
            "blocked": QColor("#f38ba8"),
            "dead": QColor("#9399b2"),
            "error": QColor("#f38ba8"),
            "pending": QColor("#f9e2af"),
        }

        data = [
            str(row + 1),
            result.server,
            result.username,
            result.status.upper(),
            result.account_status,
            result.expiry,
            str(result.live_channels) if result.live_channels else "—",
            str(result.vod_count) if result.vod_count else "—",
            f"{result.active_connections}/{result.max_connections}" if result.max_connections else "—",
            result.error_message,
        ]

        for col, text in enumerate(data):
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            if col == 3:  # Status column
                color = STATUS_COLORS.get(result.status, QColor("#cdd6f4"))
                item.setForeground(color)
            self._table.setItem(row, col, item)

    def _update_stats(self):
        total = len(self._results)
        active = sum(1 for r in self._results if r and r.status == "active")
        expired = sum(1 for r in self._results if r and r.status == "expired")
        blocked = sum(1 for r in self._results if r and r.status == "blocked")
        dead = sum(1 for r in self._results if r and r.status == "dead")
        error = sum(1 for r in self._results if r and r.status == "error")
        pending = sum(1 for r in self._results if r is None or r.status == "pending")
        self._stats_label.setText(
            f"Total: {total} | Active: {active} | Expired: {expired} | "
            f"Blocked: {blocked} | Dead: {dead} | Error: {error} | Pending: {pending}"
        )

    def set_progress(self, current, total):
        self._progress.setVisible(True)
        self._progress.setMaximum(total)
        self._progress.setValue(current)

    def set_testing(self, is_testing: bool):
        self._stop_btn.setEnabled(is_testing)

    def finish_progress(self):
        self._progress.setFormat("Bulk test complete! (%v/%m)")
        self._stop_btn.setEnabled(False)
        self._update_stats()

    def clear_all(self):
        """Clear all bulk results."""
        self._table.setRowCount(0)
        self._results.clear()
        self._stats_label.setText("No bulk test run yet")
        self._progress.setVisible(False)

    def _show_context_menu(self, pos):
        row = self._table.rowAt(pos.y())
        if row < 0 or row >= len(self._results) or not self._results[row]:
            return

        result = self._results[row]
        menu = QMenu(self)

        if result.status == "active" and result.m3u_url:
            load_action = menu.addAction("Load Channels from This Link")
        else:
            load_action = None

        copy_url = menu.addAction("Copy M3U URL")
        copy_line = menu.addAction("Copy Raw Line")

        action = menu.exec_(self._table.viewport().mapToGlobal(pos))
        if action == load_action and result.m3u_url:
            self.load_link_requested.emit(result.m3u_url)
        elif action == copy_url and result.m3u_url:
            QApplication.clipboard().setText(result.m3u_url)
        elif action == copy_line:
            QApplication.clipboard().setText(result.raw_line)
