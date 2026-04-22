"""Main application window — tabs, menu bar, scan orchestration, and player."""

import os
import sys
import threading
import requests

from PyQt5.QtWidgets import (
    QMainWindow, QTabWidget, QMessageBox, QFileDialog, QApplication
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QObject

from ui.input_tab import InputTab
from ui.results_tab import ResultsTab
from ui.account_tab import AccountTab
from ui.player_tab import PlayerTab
from ui.bulk_tab import BulkTab
from ui.active_backup_tab import ActiveBackupTab
from ui.reddit_tab import RedditTab
from ui.settings_tab import SettingsTab
from core.updater import check_for_updates
from ui.widgets import StatusDelegate
from core.m3u_parser import parse_m3u, parse_m3u_file
from core.xtreme_api import XtremeAPI
from core.stream_checker import StreamChecker
from core.bulk_tester import BulkTester
from core.exporter import export_csv, export_working_m3u
from utils.url_detector import detect_url_type
from utils.constants import APP_NAME, APP_VERSION, WINDOW_WIDTH, WINDOW_HEIGHT


class _LoadWorker(QObject):
    """Worker that runs loading operations in a background thread."""
    channels_loaded = pyqtSignal(list)
    account_loaded = pyqtSignal(object)  # AccountInfo
    content_counts = pyqtSignal(int, int, int)  # live, vod, series
    error = pyqtSignal(str)
    status = pyqtSignal(str)
    finished = pyqtSignal()
    fill_creds = pyqtSignal(str, str, str)

    def __init__(self, source_type, data):
        super().__init__()
        self.source_type = source_type
        self.data = data
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            if self.source_type == "m3u_file":
                self._load_m3u_file(self.data["filepath"])
            elif self.source_type == "url":
                self._load_url(self.data["url"])
            elif self.source_type == "xtreme_codes":
                self._load_xtreme(self.data["server"], self.data["username"], self.data["password"])
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

    def _load_m3u_file(self, filepath):
        channels = parse_m3u_file(filepath)
        if not channels:
            self.error.emit("No channels found in the M3U file.")
            return
        self.channels_loaded.emit(channels)
        self.status.emit(f"Loaded {len(channels)} channels from file")

    def _load_url(self, url):
        detected = detect_url_type(url)
        if detected["type"] == "xtreme_codes":
            server = detected.get("server", "")
            username = detected.get("username", "")
            password = detected.get("password", "")
            self.fill_creds.emit(server, username, password)
            self._load_xtreme(server, username, password)
        else:
            self._download_and_parse_m3u(url)

    def _download_and_parse_m3u(self, url):
        self.status.emit("Downloading M3U...")
        resp = requests.get(url, timeout=30, headers={"User-Agent": "VLC/3.0.18 LibVLC/3.0.18"})
        resp.raise_for_status()
        channels = parse_m3u(resp.text)
        if not channels:
            self.error.emit("No channels found at this URL.")
            return
        self.channels_loaded.emit(channels)
        self.status.emit(f"Loaded {len(channels)} channels from URL")

    def _load_xtreme(self, server, username, password):
        self.status.emit("Connecting to Xtreme Codes API...")
        api = XtremeAPI(server, username, password)

        # Fetch account info
        try:
            account = api.get_account_info()
            self.account_loaded.emit(account)
        except ValueError:
            m3u_url = f"{server}/get.php?username={username}&password={password}&type=m3u_plus"
            self.status.emit("Server returned M3U format, downloading playlist...")
            self._download_and_parse_m3u(m3u_url)
            return
        except Exception as e:
            self.error.emit(f"Could not fetch account info:\n{e}")

        if self._stop:
            return

        # Fetch live streams
        self.status.emit("Fetching live streams...")
        channels = api.get_live_streams()

        if self._stop:
            return

        # Fetch VOD and series counts
        vod_count = 0
        series_count = 0
        try:
            self.status.emit("Fetching VOD streams...")
            vod = api.get_vod_streams()
            vod_count = len(vod)
        except Exception:
            pass
        if self._stop:
            return
        try:
            self.status.emit("Fetching series...")
            series = api.get_series()
            series_count = len(series)
        except Exception:
            pass

        self.content_counts.emit(len(channels), vod_count, series_count)

        if not channels:
            self.error.emit("No live channels found on this server.")
            return

        self.channels_loaded.emit(channels)
        self.status.emit(
            f"Loaded {len(channels)} live channels | VOD: {vod_count} | Series: {series_count}"
        )


class MainWindow(QMainWindow):
    """Main application window with Input, Results, Account, and Player tabs."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self._channels = []
        self._checker = StreamChecker()
        self._bulk_tester = BulkTester()
        self._xtreme_api = None
        self._backup_path = ""
        self._load_thread = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        # Tab widget
        self._tabs = QTabWidget()

        self._input_tab = InputTab()
        self._results_tab = ResultsTab()
        self._account_tab = AccountTab()
        self._player_tab = PlayerTab()
        self._bulk_tab = BulkTab()
        self._active_backup_tab = ActiveBackupTab()
        self._reddit_tab = RedditTab()
        self._settings_tab = SettingsTab()

        self._tabs.addTab(self._input_tab, "Input")
        self._tabs.addTab(self._results_tab, "Results")
        self._tabs.addTab(self._player_tab, "Player")
        self._tabs.addTab(self._bulk_tab, "Bulk Results")
        self._tabs.addTab(self._active_backup_tab, "Active Backup")
        self._tabs.addTab(self._reddit_tab, "🔴 Reddit IPTV")
        self._tabs.addTab(self._account_tab, "Account Info")
        self._tabs.addTab(self._settings_tab, "⚙ Settings")

        self.setCentralWidget(self._tabs)

        # Apply status delegate to the Status column (index 3)
        self._results_tab._table.setItemDelegateForColumn(3, StatusDelegate(self))

        # Double-click on a channel row to play it
        self._results_tab._table.doubleClicked.connect(self._on_channel_double_click)

        # Menu bar
        menu = self.menuBar()

        # File menu
        file_menu = menu.addMenu("File")
        file_menu.addAction("Open M3U...", self._menu_open_m3u)
        file_menu.addSeparator()
        file_menu.addAction("Export CSV...", self._export_csv)
        file_menu.addAction("Export Working M3U...", self._export_m3u)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        # Settings menu
        settings_menu = menu.addMenu("⚙ Settings")
        settings_menu.addAction("Open Settings", self._open_settings_tab)
        settings_menu.addSeparator()
        settings_menu.addAction("🔄 Check for Updates", self._check_for_updates)
        settings_menu.addSeparator()
        settings_menu.addAction("ℹ About", self._show_about)

        # Status bar
        self.statusBar().showMessage("Ready — Double-click a channel to play it")

        # Silent update check on startup
        check_for_updates(self, silent=True)

    def _connect_signals(self):
        # Input tab signals
        self._input_tab.load_requested.connect(self._handle_load)
        self._input_tab.scan_requested.connect(self._start_scan)
        self._input_tab.stop_requested.connect(self._stop_scan)

        # Stream checker signals
        self._checker.channel_checked.connect(self._on_channel_checked)
        self._checker.scan_progress.connect(self._on_scan_progress)
        self._checker.scan_finished.connect(self._on_scan_finished)
        self._checker.scan_error.connect(self._on_scan_error)

        # Results tab export signals
        self._results_tab.export_csv_requested.connect(self._export_csv)
        self._results_tab.export_m3u_requested.connect(self._export_m3u)

        # Results tab play signal
        self._results_tab.play_requested.connect(self._play_channel)

        # Backup playlist signals
        self._results_tab.add_to_backup_requested.connect(self._add_channel_to_backup)
        self._player_tab.add_to_backup_requested.connect(self._add_current_to_backup)

        # Bulk tester signals
        self._input_tab.bulk_requested.connect(self._start_bulk_test)
        self._input_tab.bulk_stop_requested.connect(self._stop_bulk_test)
        self._bulk_tester.link_tested.connect(self._on_bulk_result)
        self._bulk_tester.progress.connect(self._on_bulk_progress)
        self._bulk_tester.finished.connect(self._on_bulk_finished)
        self._bulk_tab.load_link_requested.connect(self._load_bulk_link)

        # Results tab stop/clear
        self._results_tab.stop_scan_requested.connect(self._stop_scan)
        self._results_tab.clear_results_requested.connect(self._clear_results)

        # Bulk tab stop/clear
        self._bulk_tab.stop_bulk_requested.connect(self._stop_bulk_test)
        self._bulk_tab.clear_bulk_requested.connect(self._clear_bulk_results)

        # Active backup tab
        self._active_backup_tab.play_link_requested.connect(self._load_bulk_link)

        # Reddit tab — load M3U link into Results tab
        self._reddit_tab.load_link_requested.connect(self._load_bulk_link)

        # Settings tab — notify Reddit tab when URLs change
        self._settings_tab.settings_saved.connect(self._reddit_tab.on_settings_changed)

    # ---- Bulk Testing ----

    def _start_bulk_test(self, lines: list):
        """Start testing multiple links."""
        self._bulk_tab.clear()
        self._bulk_tab.set_row_count(len(lines))
        self._bulk_tab.set_testing(True)
        self._input_tab.set_bulk_testing(True)
        self._tabs.setCurrentWidget(self._bulk_tab)
        self.statusBar().showMessage(f"Bulk testing {len(lines)} links...")
        self._bulk_tester.start(lines, max_workers=5)

    def _stop_bulk_test(self):
        """Stop the bulk test."""
        self._bulk_tester.stop()
        self._bulk_tab.set_testing(False)
        self._input_tab.set_bulk_testing(False)
        self.statusBar().showMessage("Bulk test stopped.")

    def _on_bulk_result(self, index: int, result):
        self._bulk_tab.update_result(index, result)
        # Auto-save active links to the Active Backup tab
        if result.status == "active":
            self._active_backup_tab.add_active_link(result)

    def _on_bulk_progress(self, current: int, total: int):
        self._bulk_tab.set_progress(current, total)
        self.statusBar().showMessage(f"Bulk testing... {current}/{total}")

    def _on_bulk_finished(self):
        self._bulk_tab.finish_progress()
        self._bulk_tab.set_testing(False)
        self._input_tab.set_bulk_testing(False)
        self.statusBar().showMessage("Bulk test complete!")

    def _clear_bulk_results(self):
        """Clear all bulk test results."""
        self._bulk_tab.clear_all()
        self.statusBar().showMessage("Bulk results cleared.")

    def _load_bulk_link(self, m3u_url: str):
        """Load channels from a bulk-tested link into the Results tab."""
        self._download_and_parse_m3u(m3u_url)

    # ---- Backup Playlist ----

    def _get_backup_path(self) -> str:
        """Get or create the backup playlist path."""
        if not hasattr(self, '_backup_path') or not self._backup_path:
            filepath, _ = QFileDialog.getSaveFileName(
                self, "Choose Backup Playlist File",
                "backup_playlist.m3u", "M3U Files (*.m3u)"
            )
            if filepath:
                self._backup_path = filepath
                # Create file with header if it doesn't exist
                if not os.path.exists(filepath):
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write("#EXTM3U\n")
            else:
                return ""
        return self._backup_path

    def _add_channel_to_backup(self, channel):
        """Add a channel from the results table to the backup playlist."""
        path = self._get_backup_path()
        if not path:
            return
        self._append_to_backup(channel.name, channel.group, channel.logo_url, channel.stream_url)

    def _add_current_to_backup(self):
        """Add the currently playing channel to the backup playlist."""
        if not self._player_tab._current_url:
            QMessageBox.warning(self, "No Channel", "No channel is currently playing.")
            return
        path = self._get_backup_path()
        if not path:
            return
        # Find the channel object by URL
        name = self._player_tab._current_name
        url = self._player_tab._current_url
        group = ""
        logo = ""
        for ch in self._channels:
            if ch.stream_url == url:
                group = ch.group
                logo = ch.logo_url
                break
        self._append_to_backup(name, group, logo, url)

    def _append_to_backup(self, name: str, group: str, logo: str, url: str):
        """Append a single channel to the backup M3U file."""
        path = self._backup_path
        # Check if already in the file
        try:
            with open(path, "r", encoding="utf-8") as f:
                if url in f.read():
                    self.statusBar().showMessage(f"Already in backup: {name}")
                    return
        except FileNotFoundError:
            pass

        with open(path, "a", encoding="utf-8") as f:
            logo_attr = f' tvg-logo="{logo}"' if logo else ""
            group_attr = f' group-title="{group}"' if group else ""
            f.write(f'#EXTINF:-1 tvg-name="{name}"{logo_attr}{group_attr},{name}\n')
            f.write(f"{url}\n")

        # Count entries
        with open(path, "r", encoding="utf-8") as f:
            count = sum(1 for line in f if line.startswith("#EXTINF"))

        self.statusBar().showMessage(f"Added to backup: {name} ({count} channels saved)")

    # ---- Playback ----

    def _on_channel_double_click(self, proxy_index):
        """Handle double-click on a channel row in the results table."""
        source_index = self._results_tab._proxy.mapToSource(proxy_index)
        channel = self._results_tab.model.get_channel(source_index.row())
        if channel.stream_url:
            self._play_channel(channel.name, channel.stream_url)

    def _play_channel(self, name: str, url: str):
        """Play a channel in the Player tab."""
        self._player_tab.play(name, url)
        self._tabs.setCurrentWidget(self._player_tab)
        self.statusBar().showMessage(f"Playing: {name}")

    # ---- Loading ----

    def _handle_load(self, source_type: str, data: dict):
        """Handle load requests from the input tab — runs in background thread."""
        if self._load_thread and self._load_thread.isRunning():
            QMessageBox.warning(self, "Busy", "Already loading, please wait...")
            return

        self.statusBar().showMessage("Loading...")

        worker = _LoadWorker(source_type, data)
        thread = QThread()
        worker.moveToThread(thread)

        # Connect signals
        thread.started.connect(worker.run)
        worker.channels_loaded.connect(self._on_channels_loaded)
        worker.account_loaded.connect(self._account_tab.set_account_info)
        worker.content_counts.connect(self._account_tab.set_content_counts)
        worker.error.connect(self._on_load_error)
        worker.status.connect(lambda msg: self.statusBar().showMessage(msg))
        worker.fill_creds.connect(self._input_tab.fill_xtreme_credentials)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._load_thread = thread
        self._load_worker = worker  # prevent GC
        thread.start()

    def _on_channels_loaded(self, channels):
        """Handle channels loaded from background thread."""
        self._set_channels(channels)

    def _on_load_error(self, msg):
        """Handle load error from background thread."""
        QMessageBox.warning(self, "Load Error", msg)
        self.statusBar().showMessage("Load failed")

    def _download_and_parse_m3u(self, url: str):
        """Download an M3U URL and parse the channels (used by bulk link loader)."""
        self._handle_load("url", {"url": url})

    def _set_channels(self, channels):
        self._channels = channels
        self._results_tab.set_channels(channels)
        self._tabs.setCurrentIndex(1)  # Switch to Results tab

    # ---- Scanning ----

    def _clear_results(self):
        """Clear all scan results and channels."""
        self._checker.stop_scan()
        self._channels = []
        self._results_tab.clear_all()
        self._input_tab.set_scanning(False)
        self._results_tab.set_scanning(False)
        self.statusBar().showMessage("Results cleared.")

    def _start_scan(self, concurrency: int, timeout: int):
        if not self._channels:
            QMessageBox.warning(self, "No Channels", "Load channels first before scanning.")
            return

        # Reset all channels to pending
        for ch in self._channels:
            ch.status = "pending"
            ch.video_codec = ""
            ch.audio_codec = ""
            ch.resolution = ""
            ch.video_bitrate = ""
            ch.audio_bitrate = ""
            ch.fps = ""
            ch.container = ""
            ch.error_message = ""

        self._results_tab.set_channels(self._channels)
        self._input_tab.set_scanning(True)
        self._results_tab.set_scanning(True)
        self._results_tab.set_progress(0, len(self._channels))
        self.statusBar().showMessage(f"Scanning {len(self._channels)} channels...")

        self._checker.start_scan(self._channels, concurrency, timeout)

    def _stop_scan(self):
        self._checker.stop_scan()
        self._input_tab.set_scanning(False)
        self._results_tab.set_scanning(False)
        self.statusBar().showMessage("Scan stopped.")

    def _on_channel_checked(self, index: int, channel):
        self._channels[index] = channel
        self._results_tab.update_channel(index, channel)

    def _on_scan_progress(self, current: int, total: int):
        self._results_tab.set_progress(current, total)
        self.statusBar().showMessage(f"Scanning... {current}/{total}")

    def _on_scan_finished(self):
        self._input_tab.set_scanning(False)
        self._results_tab.set_scanning(False)
        self._results_tab.finish_progress()
        live = sum(1 for c in self._channels if c.status == "live")
        dead = sum(1 for c in self._channels if c.status == "dead")
        self.statusBar().showMessage(
            f"Scan complete! {live} live, {dead} dead out of {len(self._channels)} channels"
        )

    def _on_scan_error(self, error: str):
        QMessageBox.critical(self, "Scan Error", error)

    # ---- Export ----

    def _menu_open_m3u(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open M3U Playlist",
            "", "M3U Files (*.m3u *.m3u8);;All Files (*)"
        )
        if filepath:
            self._handle_load("m3u_file", {"filepath": filepath})

    def _export_csv(self):
        if not self._channels:
            QMessageBox.warning(self, "No Data", "No channels to export.")
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "channels.csv", "CSV Files (*.csv)"
        )
        if filepath:
            try:
                export_csv(self._channels, filepath)
                self.statusBar().showMessage(f"Exported CSV to {filepath}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))

    def _export_m3u(self):
        if not self._channels:
            QMessageBox.warning(self, "No Data", "No channels to export.")
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Working M3U", "working_channels.m3u", "M3U Files (*.m3u)"
        )
        if filepath:
            try:
                export_working_m3u(self._channels, filepath)
                live = sum(1 for c in self._channels if c.status == "live")
                self.statusBar().showMessage(f"Exported {live} working channels to {filepath}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))

    # ---- Settings menu handlers ----

    def _open_settings_tab(self):
        """Switch to the Settings tab."""
        self._tabs.setCurrentWidget(self._settings_tab)

    def _check_for_updates(self):
        """Manually trigger an update check (always shows result)."""
        check_for_updates(self, silent=False)

    def _show_about(self):
        from utils.constants import APP_NAME, APP_VERSION
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> v{APP_VERSION}<br><br>"
            "Stream checker, bulk tester, Reddit IPTV scanner.<br><br>"
            '<a href="https://github.com/dj2nazty/iptv-checker">'
            "github.com/dj2nazty/iptv-checker</a>"
        )

    def closeEvent(self, event):
        """Clean up VLC and stop all background work on close."""
        try:
            self._checker.stop_scan()
        except Exception:
            pass
        try:
            self._bulk_tester.stop()
        except Exception:
            pass
        try:
            self._player_tab.cleanup()
        except Exception:
            pass
        super().closeEvent(event)
