"""Account info tab — displays Xtreme Codes account details."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout, QHBoxLayout, QPushButton
)
from PyQt5.QtCore import pyqtSignal
from models.channel import AccountInfo


class AccountTab(QWidget):
    """Tab showing Xtreme Codes account info, connections, and content counts."""

    clear_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # --- Account Details ---
        acct_group = QGroupBox("Account Details")
        acct_layout = QFormLayout()
        acct_layout.setSpacing(12)

        self._server_label = self._make_value_label()
        self._user_label = self._make_value_label()
        self._status_label = self._make_value_label()
        self._expiry_label = self._make_value_label()
        self._created_label = self._make_value_label()
        self._trial_label = self._make_value_label()

        acct_layout.addRow("Server:", self._server_label)
        acct_layout.addRow("Username:", self._user_label)
        acct_layout.addRow("Status:", self._status_label)
        acct_layout.addRow("Expiration:", self._expiry_label)
        acct_layout.addRow("Created:", self._created_label)
        acct_layout.addRow("Trial Account:", self._trial_label)

        acct_group.setLayout(acct_layout)
        layout.addWidget(acct_group)

        # --- Connections ---
        conn_group = QGroupBox("Connections")
        conn_layout = QFormLayout()
        conn_layout.setSpacing(12)

        self._max_conn_label = self._make_value_label()
        self._active_conn_label = self._make_value_label()

        conn_layout.addRow("Max Connections:", self._max_conn_label)
        conn_layout.addRow("Active Connections:", self._active_conn_label)

        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        # --- Content Summary ---
        content_group = QGroupBox("Content Summary")
        content_layout = QFormLayout()
        content_layout.setSpacing(12)

        self._live_count_label = self._make_value_label()
        self._vod_count_label = self._make_value_label()
        self._series_count_label = self._make_value_label()

        content_layout.addRow("Live Channels:", self._live_count_label)
        content_layout.addRow("VOD:", self._vod_count_label)
        content_layout.addRow("Series:", self._series_count_label)

        content_group.setLayout(content_layout)
        layout.addWidget(content_group)

        # Clear button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        clear_btn = QPushButton("Clear Account Info")
        clear_btn.setStyleSheet(
            "background-color: #9399b2; color: #1e1e2e; font-weight: bold; padding: 6px 14px;"
        )
        clear_btn.clicked.connect(self._clear_all)
        btn_layout.addWidget(clear_btn)
        layout.addLayout(btn_layout)

        layout.addStretch()

        # Show placeholder
        self._set_placeholder()

    def _make_value_label(self) -> QLabel:
        label = QLabel("—")
        label.setObjectName("accountValue")
        return label

    def _set_placeholder(self):
        """Show placeholder text when no account is loaded."""
        for label in [
            self._server_label, self._user_label, self._status_label,
            self._expiry_label, self._created_label, self._trial_label,
            self._max_conn_label, self._active_conn_label,
            self._live_count_label, self._vod_count_label, self._series_count_label,
        ]:
            label.setText("—")

    def set_account_info(self, info: AccountInfo):
        """Populate all fields from an AccountInfo object."""
        self._server_label.setText(f"{info.server_url}:{info.server_port}")
        self._user_label.setText(info.username)

        # Status with color
        status_text = info.status.capitalize() if info.status else "Unknown"
        if info.status.lower() == "active":
            self._status_label.setObjectName("statusActive")
        else:
            self._status_label.setObjectName("statusExpired")
        self._status_label.setText(status_text)
        # Force style refresh
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)

        self._expiry_label.setText(info.expiry_date or "N/A")
        self._created_label.setText(info.created_at or "N/A")
        self._trial_label.setText("Yes" if info.is_trial else "No")
        self._max_conn_label.setText(str(info.max_connections))
        self._active_conn_label.setText(str(info.active_connections))

    def set_content_counts(self, live: int = 0, vod: int = 0, series: int = 0):
        """Update the content summary counts."""
        self._live_count_label.setText(str(live))
        self._vod_count_label.setText(str(vod))
        self._series_count_label.setText(str(series))

    def _clear_all(self):
        """Clear all account info back to defaults."""
        self._set_placeholder()
        self.clear_requested.emit()
