"""Xtreme Codes API client."""

import time
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from models.channel import Channel, AccountInfo
from utils.constants import XTREME_API_TIMEOUT

HEADERS = {
    "User-Agent": "VLC/3.0.18 LibVLC/3.0.18",
    "Accept": "*/*",
    "Connection": "keep-alive",
}


def _make_session() -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class XtremeAPI:
    """Client for interacting with an Xtreme Codes IPTV panel API."""

    def __init__(self, server: str, username: str, password: str):
        self.server = server.rstrip("/")
        self.username = username
        self.password = password
        self._base_url = f"{self.server}/player_api.php"
        self._base_params = {"username": username, "password": password}
        self._categories = {}  # id -> name cache
        self._session = _make_session()

    def _get(self, extra_params: dict = None) -> dict:
        """Make a GET request to the API."""
        params = dict(self._base_params)
        if extra_params:
            params.update(extra_params)
        resp = self._session.get(
            self._base_url, params=params, timeout=XTREME_API_TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()

    def get_account_info(self) -> AccountInfo:
        """Fetch account/server info."""
        data = self._get()
        user_info = data.get("user_info", {})
        server_info = data.get("server_info", {})

        # Parse expiry
        exp_ts = user_info.get("exp_date")
        expiry_str = ""
        if exp_ts:
            try:
                expiry_dt = datetime.fromtimestamp(int(exp_ts))
                days_left = (expiry_dt - datetime.now()).days
                expiry_str = f"{expiry_dt.strftime('%Y-%m-%d %H:%M')} ({days_left} days left)"
            except (ValueError, OSError):
                expiry_str = str(exp_ts)

        # Parse created_at
        created_ts = user_info.get("created_at")
        created_str = ""
        if created_ts:
            try:
                created_str = datetime.fromtimestamp(int(created_ts)).strftime("%Y-%m-%d %H:%M")
            except (ValueError, OSError):
                created_str = str(created_ts)

        return AccountInfo(
            username=user_info.get("username", self.username),
            password=user_info.get("password", self.password),
            status=user_info.get("status", "Unknown"),
            expiry_date=expiry_str,
            max_connections=int(user_info.get("max_connections", 0)),
            active_connections=int(user_info.get("active_cons", 0)),
            server_url=server_info.get("url", self.server),
            server_port=str(server_info.get("port", "")),
            server_protocol=server_info.get("server_protocol", "http"),
            created_at=created_str,
            is_trial=user_info.get("is_trial", "0") == "1",
        )

    def get_live_categories(self) -> list[dict]:
        """Fetch live stream categories."""
        data = self._get({"action": "get_live_categories"})
        if isinstance(data, list):
            self._categories = {
                str(c.get("category_id", "")): c.get("category_name", "")
                for c in data
            }
            return data
        return []

    def get_live_streams(self) -> list[Channel]:
        """Fetch all live stream channels."""
        # Ensure categories are loaded for group mapping
        if not self._categories:
            self.get_live_categories()

        data = self._get({"action": "get_live_streams"})
        channels = []
        if isinstance(data, list):
            for item in data:
                stream_id = item.get("stream_id", "")
                cat_id = str(item.get("category_id", ""))
                channels.append(Channel(
                    name=item.get("name", "Unknown"),
                    group=self._categories.get(cat_id, "Uncategorized"),
                    logo_url=item.get("stream_icon", ""),
                    stream_url=f"{self.server}/{self.username}/{self.password}/{stream_id}.ts",
                    stream_type="live",
                ))
        return channels

    def get_vod_streams(self) -> list[Channel]:
        """Fetch all VOD streams."""
        data = self._get({"action": "get_vod_streams"})
        channels = []
        if isinstance(data, list):
            for item in data:
                stream_id = item.get("stream_id", "")
                ext = item.get("container_extension", "mp4")
                channels.append(Channel(
                    name=item.get("name", "Unknown"),
                    group=item.get("category_id", "VOD"),
                    logo_url=item.get("stream_icon", ""),
                    stream_url=f"{self.server}/movie/{self.username}/{self.password}/{stream_id}.{ext}",
                    stream_type="vod",
                ))
        return channels

    def get_series(self) -> list[Channel]:
        """Fetch all series."""
        data = self._get({"action": "get_series"})
        channels = []
        if isinstance(data, list):
            for item in data:
                channels.append(Channel(
                    name=item.get("name", "Unknown"),
                    group=item.get("category_id", "Series"),
                    logo_url=item.get("cover", ""),
                    stream_url="",  # Series need episode-level URLs
                    stream_type="series",
                ))
        return channels
