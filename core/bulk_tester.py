"""Bulk link tester — tests multiple M3U/Xtreme Codes links concurrently."""

import re
import threading
import queue
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import urlparse, parse_qs

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PyQt5.QtCore import QObject, pyqtSignal, QTimer

HEADERS = {
    "User-Agent": "VLC/3.0.18 LibVLC/3.0.18",
    "Accept": "*/*",
    "Connection": "keep-alive",
}


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


@dataclass
class LinkResult:
    """Result of testing a single link."""
    raw_line: str = ""
    link_type: str = ""  # "xtreme_codes", "m3u_url", "unknown"
    server: str = ""
    username: str = ""
    password: str = ""
    status: str = "pending"  # "active", "expired", "blocked", "dead", "error", "pending"
    account_status: str = ""
    expiry: str = ""
    max_connections: int = 0
    active_connections: int = 0
    live_channels: int = 0
    vod_count: int = 0
    series_count: int = 0
    error_message: str = ""
    m3u_url: str = ""  # resolved M3U URL for loading


class BulkTester(QObject):
    """Tests multiple IPTV links concurrently."""

    # (index, LinkResult)
    link_tested = pyqtSignal(int, object)
    # (current, total)
    progress = pyqtSignal(int, int)
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_event = threading.Event()
        self._result_queue = queue.Queue()
        self._session = _make_session()
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(200)
        self._poll_timer.timeout.connect(self._poll_results)

    def start(self, lines: list[str], max_workers: int = 5):
        """Start testing all links."""
        self._stop_event.clear()
        while not self._result_queue.empty():
            try:
                self._result_queue.get_nowait()
            except queue.Empty:
                break

        self._poll_timer.start()
        thread = threading.Thread(
            target=self._run, args=(lines, max_workers), daemon=True
        )
        thread.start()

    def stop(self):
        self._stop_event.set()

    def _poll_results(self):
        batch = 0
        while not self._result_queue.empty() and batch < 20:
            try:
                msg_type, data = self._result_queue.get_nowait()
            except queue.Empty:
                break
            if msg_type == "result":
                idx, result = data
                self.link_tested.emit(idx, result)
            elif msg_type == "progress":
                self.progress.emit(*data)
            elif msg_type == "finished":
                self._poll_timer.stop()
                self.finished.emit()
                return
            batch += 1

    def _run(self, lines: list[str], max_workers: int):
        total = len(lines)
        checked = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for idx, line in enumerate(lines):
                if self._stop_event.is_set():
                    break
                future = executor.submit(self._test_single, line)
                futures[future] = idx

            for future in futures:
                if self._stop_event.is_set():
                    break
                idx = futures[future]
                try:
                    result = future.result(timeout=60)
                except Exception as e:
                    result = LinkResult(raw_line=lines[idx], status="error", error_message=str(e))
                self._result_queue.put(("result", (idx, result)))
                checked += 1
                self._result_queue.put(("progress", (checked, total)))

        self._result_queue.put(("finished", None))

    def _test_single(self, line: str) -> LinkResult:
        """Test a single link line."""
        line = line.strip()
        result = LinkResult(raw_line=line)

        # Parse the line format
        parsed = self._parse_line(line)
        result.link_type = parsed["type"]
        result.server = parsed.get("server", "")
        result.username = parsed.get("username", "")
        result.password = parsed.get("password", "")

        if parsed["type"] == "xtreme_codes":
            self._test_xtreme(result, parsed)
        elif parsed["type"] == "m3u_url":
            self._test_m3u_url(result, line)
        else:
            result.status = "error"
            result.error_message = "Unrecognized format"

        return result

    def _parse_line(self, line: str) -> dict:
        """Parse a line into a link type and credentials."""
        # Format: server:port|username|password
        pipe_match = re.match(r'^(https?://[^|]+)\|([^|]+)\|(.+)$', line)
        if pipe_match:
            return {
                "type": "xtreme_codes",
                "server": pipe_match.group(1).rstrip("/"),
                "username": pipe_match.group(2).strip(),
                "password": pipe_match.group(3).strip(),
            }

        # Format: server:port username password (space separated)
        space_match = re.match(r'^(https?://\S+)\s+(\S+)\s+(\S+)$', line)
        if space_match:
            return {
                "type": "xtreme_codes",
                "server": space_match.group(1).rstrip("/"),
                "username": space_match.group(2),
                "password": space_match.group(3),
            }

        # URL with player_api.php or get.php
        if "player_api.php" in line or "get.php" in line:
            parsed = urlparse(line)
            params = parse_qs(parsed.query)
            server = f"{parsed.scheme}://{parsed.hostname}"
            if parsed.port:
                server += f":{parsed.port}"
            return {
                "type": "xtreme_codes",
                "server": server,
                "username": params.get("username", [""])[0],
                "password": params.get("password", [""])[0],
            }

        # Direct stream URL pattern: http://host:port/user/pass/stream.ts
        direct_match = re.match(r'^(https?://[^/]+)/([^/]+)/([^/]+)/\d+', line)
        if direct_match:
            return {
                "type": "xtreme_codes",
                "server": direct_match.group(1),
                "username": direct_match.group(2),
                "password": direct_match.group(3),
            }

        # Plain URL (M3U file)
        if line.startswith(("http://", "https://")):
            return {"type": "m3u_url"}

        return {"type": "unknown"}

    def _test_xtreme(self, result: LinkResult, parsed: dict):
        """Test an Xtreme Codes account."""
        server = parsed["server"]
        user = parsed["username"]
        passw = parsed["password"]
        result.m3u_url = f"{server}/get.php?username={user}&password={passw}&type=m3u_plus"

        try:
            api_url = f"{server}/player_api.php?username={user}&password={passw}"
            resp = self._session.get(api_url, timeout=15)

            if resp.status_code == 403:
                result.status = "blocked"
                result.error_message = "403 Forbidden"
                return
            if resp.status_code == 404:
                result.status = "dead"
                result.error_message = "Server not found (404)"
                return
            if resp.status_code != 200:
                result.status = "error"
                result.error_message = f"HTTP {resp.status_code}"
                return

            # Try to parse as JSON
            try:
                data = resp.json()
            except ValueError:
                # Server returned M3U instead of JSON — still active
                # Count channels from M3U response
                from core.m3u_parser import parse_m3u
                channels = parse_m3u(resp.text)
                result.live_channels = len(channels)
                result.status = "active" if channels else "dead"
                result.account_status = "Active (M3U)"
                return

            user_info = data.get("user_info", {})
            server_info = data.get("server_info", {})

            result.account_status = user_info.get("status", "Unknown")
            result.max_connections = int(user_info.get("max_connections", 0))
            result.active_connections = int(user_info.get("active_cons", 0))

            # Check auth
            auth = user_info.get("auth", 0)
            if not auth:
                result.status = "blocked"
                result.error_message = "Authentication failed"
                return

            # Check status
            status = user_info.get("status", "").lower()
            if status == "expired":
                result.status = "expired"
                return
            elif status == "banned":
                result.status = "blocked"
                return
            elif status == "disabled":
                result.status = "blocked"
                result.error_message = "Account disabled"
                return

            # Parse expiry
            exp_ts = user_info.get("exp_date")
            if exp_ts and exp_ts != "None":
                try:
                    from datetime import datetime
                    exp_dt = datetime.fromtimestamp(int(exp_ts))
                    days = (exp_dt - datetime.now()).days
                    result.expiry = f"{exp_dt.strftime('%Y-%m-%d')} ({days}d)"
                except (ValueError, OSError):
                    result.expiry = str(exp_ts)
            else:
                result.expiry = "No expiry"

            # Get live channel count
            try:
                live_resp = self._session.get(
                    f"{server}/player_api.php?username={user}&password={passw}&action=get_live_streams",
                    timeout=20
                )
                live_data = live_resp.json()
                if isinstance(live_data, list):
                    result.live_channels = len(live_data)
            except Exception:
                pass

            # Get VOD count
            try:
                vod_resp = self._session.get(
                    f"{server}/player_api.php?username={user}&password={passw}&action=get_vod_streams",
                    timeout=15
                )
                vod_data = vod_resp.json()
                if isinstance(vod_data, list):
                    result.vod_count = len(vod_data)
            except Exception:
                pass

            # Get series count
            try:
                ser_resp = self._session.get(
                    f"{server}/player_api.php?username={user}&password={passw}&action=get_series",
                    timeout=15
                )
                ser_data = ser_resp.json()
                if isinstance(ser_data, list):
                    result.series_count = len(ser_data)
            except Exception:
                pass

            result.status = "active"

        except requests.exceptions.ConnectTimeout:
            result.status = "dead"
            result.error_message = "Connection timeout"
        except requests.exceptions.ConnectionError:
            result.status = "dead"
            result.error_message = "Cannot connect to server"
        except Exception as e:
            result.status = "error"
            result.error_message = str(e)[:100]

    def _test_m3u_url(self, result: LinkResult, url: str):
        """Test a plain M3U URL."""
        result.m3u_url = url
        try:
            resp = self._session.get(url, timeout=20, stream=True)
            if resp.status_code == 403:
                result.status = "blocked"
                result.error_message = "403 Forbidden"
                resp.close()
                return
            if resp.status_code != 200:
                result.status = "dead"
                result.error_message = f"HTTP {resp.status_code}"
                resp.close()
                return

            # Read content and count channels
            content = resp.text
            from core.m3u_parser import parse_m3u
            channels = parse_m3u(content)
            result.live_channels = len(channels)
            result.status = "active" if channels else "dead"
            result.account_status = "M3U Playlist"

        except requests.exceptions.Timeout:
            result.status = "dead"
            result.error_message = "Timeout"
        except Exception as e:
            result.status = "error"
            result.error_message = str(e)[:100]
