"""Input tab — M3U file picker, URL paste, Xtreme Codes credentials, bulk upload."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QGroupBox, QFormLayout, QFileDialog,
    QMessageBox, QTextEdit, QSplitter
)
from PyQt5.QtCore import pyqtSignal, Qt
from utils.constants import DEFAULT_CONCURRENCY, DEFAULT_TIMEOUT, MAX_CONCURRENCY, MAX_TIMEOUT


class InputTab(QWidget):
    """Tab for entering M3U files, URLs, Xtreme Codes credentials, or bulk uploads."""

    load_requested = pyqtSignal(str, dict)
    scan_requested = pyqtSignal(int, int)
    stop_requested = pyqtSignal()
    bulk_requested = pyqtSignal(list)  # list of raw lines
    bulk_stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # --- M3U File Section ---
        file_group = QGroupBox("Load M3U File")
        file_layout = QHBoxLayout()
        self._file_path_label = QLineEdit()
        self._file_path_label.setReadOnly(True)
        self._file_path_label.setPlaceholderText("No file selected...")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_file)
        load_file_btn = QPushButton("Load File")
        load_file_btn.clicked.connect(self._load_file)
        clear_file_btn = QPushButton("Clear")
        clear_file_btn.clicked.connect(lambda: self._file_path_label.clear())
        file_layout.addWidget(self._file_path_label, 1)
        file_layout.addWidget(browse_btn)
        file_layout.addWidget(load_file_btn)
        file_layout.addWidget(clear_file_btn)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # --- URL Section ---
        url_group = QGroupBox("Load from URL")
        url_layout = QHBoxLayout()
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("Paste M3U URL or Xtreme Codes API link...")
        load_url_btn = QPushButton("Load URL")
        load_url_btn.clicked.connect(self._load_url)
        clear_url_btn = QPushButton("Clear")
        clear_url_btn.clicked.connect(lambda: self._url_input.clear())
        url_layout.addWidget(self._url_input, 1)
        url_layout.addWidget(load_url_btn)
        url_layout.addWidget(clear_url_btn)
        url_group.setLayout(url_layout)
        layout.addWidget(url_group)

        # --- Xtreme Codes Section ---
        xtreme_group = QGroupBox("Xtreme Codes API Credentials")
        xtreme_layout = QFormLayout()
        self._server_input = QLineEdit()
        self._server_input.setPlaceholderText("http://server.com:port")
        self._user_input = QLineEdit()
        self._user_input.setPlaceholderText("Username")
        self._pass_input = QLineEdit()
        self._pass_input.setPlaceholderText("Password")
        self._pass_input.setEchoMode(QLineEdit.Password)
        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(self._connect_xtreme)
        clear_xtreme_btn = QPushButton("Clear")
        clear_xtreme_btn.clicked.connect(self._clear_xtreme)
        xtreme_btn_layout = QHBoxLayout()
        xtreme_btn_layout.addWidget(connect_btn)
        xtreme_btn_layout.addWidget(clear_xtreme_btn)
        xtreme_layout.addRow("Server:", self._server_input)
        xtreme_layout.addRow("Username:", self._user_input)
        xtreme_layout.addRow("Password:", self._pass_input)
        xtreme_layout.addRow("", xtreme_btn_layout)
        xtreme_group.setLayout(xtreme_layout)
        layout.addWidget(xtreme_group)

        # --- Portal Quick Connect (paste text blob) ---
        portal_group = QGroupBox("Portal Quick Connect — Paste portal info as text")
        portal_layout = QVBoxLayout()

        portal_help = QLabel(
            "Paste text like:\n"
            "  Portal: http://server.com:8080\n"
            "  Username: myuser | Password: mypass\n"
            "(also accepts 'Host:', separate lines, or http://user@host:port format)"
        )
        portal_help.setObjectName("statsLabel")
        portal_help.setStyleSheet("color: #a6adc8; font-size: 11px;")
        portal_help.setWordWrap(True)
        portal_layout.addWidget(portal_help)

        self._portal_text = QTextEdit()
        self._portal_text.setPlaceholderText(
            "Portal: http://example.com:8080\n"
            "Username: myuser | Password: mypass"
        )
        self._portal_text.setMaximumHeight(80)
        portal_layout.addWidget(self._portal_text)

        portal_btn_row = QHBoxLayout()
        portal_parse_btn = QPushButton("Parse & Fill")
        portal_parse_btn.clicked.connect(self._parse_portal_text)
        portal_btn_row.addWidget(portal_parse_btn)

        portal_connect_btn = QPushButton("Parse & Connect")
        portal_connect_btn.setStyleSheet(
            "background-color: #a6e3a1; color: #1e1e2e; font-weight: bold; padding: 6px 14px;"
        )
        portal_connect_btn.clicked.connect(self._parse_and_connect_portal)
        portal_btn_row.addWidget(portal_connect_btn)

        portal_clear_btn = QPushButton("Clear")
        portal_clear_btn.clicked.connect(lambda: self._portal_text.clear())
        portal_btn_row.addWidget(portal_clear_btn)
        portal_btn_row.addStretch()

        portal_layout.addLayout(portal_btn_row)
        portal_group.setLayout(portal_layout)
        layout.addWidget(portal_group)

        # --- Bulk Upload Section ---
        bulk_group = QGroupBox("Bulk Upload — Paste or load multiple links")
        bulk_layout = QVBoxLayout()

        bulk_help = QLabel(
            "Paste any of these (mix freely):\n"
            "  • One link per line: M3U URLs, get.php URLs, or server|user|pass\n"
            "  • Multi-line Portal blocks (separate each block with a blank line):\n"
            "      Portal: http://host:port\n"
            "      Username: xxx | Password: yyy"
        )
        bulk_help.setObjectName("statsLabel")
        bulk_help.setWordWrap(True)
        bulk_layout.addWidget(bulk_help)

        self._bulk_text = QTextEdit()
        self._bulk_text.setPlaceholderText(
            "http://server.com:8080/get.php?username=user&password=pass&type=m3u_plus\n"
            "http://other.com:25461/get.php?username=test&password=test123&type=m3u_plus\n"
            "http://iptv.example.com:8080|myuser|mypass\n"
            "http://example.com/playlist.m3u\n"
            "..."
        )
        self._bulk_text.setMaximumHeight(120)
        bulk_layout.addWidget(self._bulk_text)

        bulk_btn_layout = QHBoxLayout()
        bulk_browse_btn = QPushButton("Load from .txt File")
        bulk_browse_btn.clicked.connect(self._browse_bulk_file)
        bulk_btn_layout.addWidget(bulk_browse_btn)

        bulk_clear_btn = QPushButton("Clear")
        bulk_clear_btn.clicked.connect(self._clear_bulk)
        bulk_btn_layout.addWidget(bulk_clear_btn)

        self._bulk_count_label = QLabel("")
        bulk_btn_layout.addWidget(self._bulk_count_label)

        bulk_btn_layout.addStretch()

        self._bulk_start_btn = QPushButton("Test All Links")
        self._bulk_start_btn.setStyleSheet(
            "background-color: #cba6f7; color: #1e1e2e; font-weight: bold; padding: 8px 20px;"
        )
        self._bulk_start_btn.clicked.connect(self._start_bulk)
        bulk_btn_layout.addWidget(self._bulk_start_btn)

        self._bulk_stop_btn = QPushButton("Stop Test")
        self._bulk_stop_btn.setStyleSheet(
            "background-color: #f38ba8; color: #1e1e2e; font-weight: bold; padding: 8px 20px;"
        )
        self._bulk_stop_btn.setEnabled(False)
        self._bulk_stop_btn.clicked.connect(self._stop_bulk)
        bulk_btn_layout.addWidget(self._bulk_stop_btn)

        bulk_layout.addLayout(bulk_btn_layout)
        bulk_group.setLayout(bulk_layout)
        layout.addWidget(bulk_group)

        # --- Scan Settings ---
        scan_group = QGroupBox("Scan Settings")
        scan_layout = QHBoxLayout()

        scan_layout.addWidget(QLabel("Concurrent Workers:"))
        self._workers_spin = QSpinBox()
        self._workers_spin.setRange(1, MAX_CONCURRENCY)
        self._workers_spin.setValue(DEFAULT_CONCURRENCY)
        scan_layout.addWidget(self._workers_spin)

        scan_layout.addWidget(QLabel("Timeout (sec):"))
        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(1, MAX_TIMEOUT)
        self._timeout_spin.setValue(DEFAULT_TIMEOUT)
        scan_layout.addWidget(self._timeout_spin)

        scan_layout.addStretch()

        self._start_btn = QPushButton("Start Scan")
        self._start_btn.setObjectName("startScanBtn")
        self._start_btn.clicked.connect(self._start_scan)
        scan_layout.addWidget(self._start_btn)

        self._stop_btn = QPushButton("Stop Scan")
        self._stop_btn.setObjectName("stopScanBtn")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_scan)
        scan_layout.addWidget(self._stop_btn)

        scan_group.setLayout(scan_layout)
        layout.addWidget(scan_group)

    def _browse_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open M3U Playlist",
            "", "M3U Files (*.m3u *.m3u8);;All Files (*)"
        )
        if filepath:
            self._file_path_label.setText(filepath)

    def _load_file(self):
        filepath = self._file_path_label.text().strip()
        if not filepath:
            QMessageBox.warning(self, "No File", "Please select an M3U file first.")
            return
        self.load_requested.emit("m3u_file", {"filepath": filepath})

    def _load_url(self):
        url = self._url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL", "Please enter a URL.")
            return
        self.load_requested.emit("url", {"url": url})

    def _parse_portal_blob(self, text: str) -> dict:
        """Parse a pasted portal info blob into server/username/password.

        Accepts flexible formats:
          Portal: http://host:port
          Host: host:port
          Username: xxx | Password: yyy
          Username: xxx
          Password: yyy
          http://user@host:port  (strips the user@ prefix which some panels prepend)
        """
        import re
        result = {"server": "", "username": "", "password": ""}
        if not text:
            return result

        # Normalize the blob
        t = text.replace("\r", "\n")

        # Portal / Host / Server / URL — accept any label
        portal_match = re.search(
            r'(?i)(?:portal|host|server|url)\s*[:=]\s*(\S+)', t
        )
        if portal_match:
            portal = portal_match.group(1).strip().rstrip("|,;")
            # Add http:// if missing
            if not re.match(r'^https?://', portal):
                portal = "http://" + portal
            # Strip any "user@" prefix that some panels include before the host
            portal = re.sub(r'(https?://)([^/@\s]+)@', r'\1', portal)
            result["server"] = portal.rstrip("/")
        else:
            # Fall back: any http(s) URL in the text
            url_match = re.search(r'(https?://\S+)', t)
            if url_match:
                portal = url_match.group(1).rstrip("/|,;")
                portal = re.sub(r'(https?://)([^/@\s]+)@', r'\1', portal)
                result["server"] = portal

        # Username
        user_match = re.search(
            r'(?i)(?:user(?:name)?|login)\s*[:=]\s*([^\s|,;\n]+)', t
        )
        if user_match:
            result["username"] = user_match.group(1).strip()

        # Password
        pass_match = re.search(
            r'(?i)(?:pass(?:word)?|pwd)\s*[:=]\s*([^\s|,;\n]+)', t
        )
        if pass_match:
            result["password"] = pass_match.group(1).strip()

        return result

    def _parse_portal_text(self):
        """Parse the pasted portal blob and fill the Xtreme Codes fields."""
        text = self._portal_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Empty", "Paste portal info first.")
            return

        parsed = self._parse_portal_blob(text)
        missing = [k for k in ("server", "username", "password") if not parsed[k]]
        if missing:
            QMessageBox.warning(
                self, "Could Not Parse",
                f"Missing from text: {', '.join(missing)}\n\n"
                "Expected format:\n"
                "  Portal: http://host:port\n"
                "  Username: xxx | Password: yyy"
            )
            return

        self._server_input.setText(parsed["server"])
        self._user_input.setText(parsed["username"])
        self._pass_input.setText(parsed["password"])
        QMessageBox.information(
            self, "Parsed",
            f"Filled credentials:\n\n"
            f"Server: {parsed['server']}\n"
            f"Username: {parsed['username']}\n"
            f"Password: {'*' * len(parsed['password'])}\n\n"
            "Click 'Connect' to load channels, or use 'Parse & Connect' next time."
        )

    def _parse_and_connect_portal(self):
        """Parse the blob, fill fields, and immediately connect."""
        text = self._portal_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Empty", "Paste portal info first.")
            return

        parsed = self._parse_portal_blob(text)
        missing = [k for k in ("server", "username", "password") if not parsed[k]]
        if missing:
            QMessageBox.warning(
                self, "Could Not Parse",
                f"Missing from text: {', '.join(missing)}\n\n"
                "Expected format:\n"
                "  Portal: http://host:port\n"
                "  Username: xxx | Password: yyy"
            )
            return

        self._server_input.setText(parsed["server"])
        self._user_input.setText(parsed["username"])
        self._pass_input.setText(parsed["password"])
        self.load_requested.emit("xtreme_codes", {
            "server": parsed["server"],
            "username": parsed["username"],
            "password": parsed["password"],
        })

    def _connect_xtreme(self):
        server = self._server_input.text().strip()
        username = self._user_input.text().strip()
        password = self._pass_input.text().strip()
        if not server or not username or not password:
            QMessageBox.warning(self, "Missing Fields", "Please fill in all Xtreme Codes fields.")
            return
        self.load_requested.emit("xtreme_codes", {
            "server": server,
            "username": username,
            "password": password,
        })

    def _browse_bulk_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open Bulk Links File",
            "", "Text Files (*.txt);;M3U Files (*.m3u *.m3u8);;All Files (*)"
        )
        if filepath:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            self._bulk_text.setPlainText(content)
            lines = [l.strip() for l in content.split("\n") if l.strip()]
            self._bulk_count_label.setText(f"{len(lines)} links loaded")

    def _clear_xtreme(self):
        self._server_input.clear()
        self._user_input.clear()
        self._pass_input.clear()

    def _clear_bulk(self):
        self._bulk_text.clear()
        self._bulk_count_label.setText("")

    def _stop_bulk(self):
        self.bulk_stop_requested.emit()

    def _start_bulk(self):
        text = self._bulk_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Empty", "Paste or load links first.")
            return

        lines = self._preprocess_bulk_text(text)
        if not lines:
            QMessageBox.warning(self, "No Links", "No valid links found.")
            return
        self.bulk_requested.emit(lines)

    def _preprocess_bulk_text(self, text: str) -> list:
        """Convert pasted text to a flat list of testable lines.

        Handles:
          - Normal single-line entries (URL, pipe-separated, etc.)
          - Multi-line Portal/Username/Password blocks (separated by blank lines)
          - Mixed content
        Converts portal blocks into 'server|username|password' format.
        """
        import re

        # Split text into blocks separated by blank lines
        raw_blocks = re.split(r'\n\s*\n', text)

        result_lines: list[str] = []
        for block in raw_blocks:
            block = block.strip()
            if not block:
                continue

            # If the block contains a "Portal:" / "Host:" / "Server:" label
            # AND has a Username/Password label, treat it as a multi-line portal entry
            has_portal_label = bool(re.search(r'(?im)^\s*(?:portal|host|server|url)\s*[:=]', block))
            has_user_label = bool(re.search(r'(?i)(?:user(?:name)?|login)\s*[:=]', block))
            has_pass_label = bool(re.search(r'(?i)(?:pass(?:word)?|pwd)\s*[:=]', block))

            if has_portal_label and has_user_label and has_pass_label:
                parsed = self._parse_portal_blob(block)
                if parsed["server"] and parsed["username"] and parsed["password"]:
                    result_lines.append(
                        f'{parsed["server"]}|{parsed["username"]}|{parsed["password"]}'
                    )
                    continue
                # If parse failed, fall through and treat line-by-line

            # Otherwise split into lines and pass each through
            for line in block.split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    result_lines.append(line)

        return result_lines

    def _start_scan(self):
        self.scan_requested.emit(
            self._workers_spin.value(),
            self._timeout_spin.value(),
        )

    def _stop_scan(self):
        self.stop_requested.emit()

    def set_scanning(self, is_scanning: bool):
        self._start_btn.setEnabled(not is_scanning)
        self._stop_btn.setEnabled(is_scanning)

    def set_bulk_testing(self, is_testing: bool):
        self._bulk_start_btn.setEnabled(not is_testing)
        self._bulk_stop_btn.setEnabled(is_testing)

    def fill_xtreme_credentials(self, server: str, username: str, password: str):
        self._server_input.setText(server)
        self._user_input.setText(username)
        self._pass_input.setText(password)
