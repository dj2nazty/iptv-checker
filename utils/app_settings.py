"""App-wide persistent settings — loads/saves to settings.json next to the app."""
from __future__ import annotations

import json
import os

_HERE     = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_HERE)
SETTINGS_FILE = os.path.join(_APP_ROOT, "settings.json")

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULTS: dict = {
    "reddit_urls": [
        "https://www.reddit.com/r/IPTV_ZONENEW/"
    ],
    "reddit_max_pages": 5,
    "reddit_test_workers": 6,
}


class AppSettings:
    """Simple JSON-backed settings store. Use the module-level `settings` singleton."""

    def __init__(self):
        self._data: dict = {}
        self.load()

    # ── Persistence ───────────────────────────────────────────────────────────
    def load(self):
        """Load settings from disk; missing keys fall back to defaults."""
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            stored = {}

        # Merge stored values on top of defaults
        self._data = dict(DEFAULTS)
        self._data.update(stored)

    def save(self):
        """Persist current settings to disk."""
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as exc:
            print(f"[AppSettings] Save failed: {exc}")

    # ── Accessors ─────────────────────────────────────────────────────────────
    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value

    # ── Typed helpers ─────────────────────────────────────────────────────────
    @property
    def reddit_urls(self) -> list:
        val = self._data.get("reddit_urls", DEFAULTS["reddit_urls"])
        return val if isinstance(val, list) and val else DEFAULTS["reddit_urls"]

    @reddit_urls.setter
    def reddit_urls(self, value: list):
        self._data["reddit_urls"] = value

    @property
    def reddit_max_pages(self) -> int:
        return int(self._data.get("reddit_max_pages", DEFAULTS["reddit_max_pages"]))

    @reddit_max_pages.setter
    def reddit_max_pages(self, value: int):
        self._data["reddit_max_pages"] = int(value)

    @property
    def reddit_test_workers(self) -> int:
        return int(self._data.get("reddit_test_workers", DEFAULTS["reddit_test_workers"]))

    @reddit_test_workers.setter
    def reddit_test_workers(self, value: int):
        self._data["reddit_test_workers"] = int(value)


# ── Module-level singleton ────────────────────────────────────────────────────
settings = AppSettings()


# ── Helpers ───────────────────────────────────────────────────────────────────
def extract_subreddit_json_url(reddit_url: str) -> str:
    """Convert any Reddit subreddit URL or name into its .json API endpoint.

    Accepts any of:
      - https://www.reddit.com/r/IPTV_ZONENEW/
      - reddit.com/r/IPTV_ZONENEW
      - /r/IPTV_ZONENEW
      - IPTV_ZONENEW
    Returns:
      - https://www.reddit.com/r/IPTV_ZONENEW/.json
    """
    url = reddit_url.strip().rstrip("/")

    # Full URL with /r/  (handles https://reddit.com/r/X and reddit.com/r/X)
    if "/r/" in url:
        after_r = url.split("/r/", 1)[1].split("/")[0].strip()
        if after_r:
            return f"https://www.reddit.com/r/{after_r}/.json"

    # Starts with r/NAME  (no leading slash)
    if url.startswith("r/"):
        name = url[2:].split("/")[0].strip()
        if name:
            return f"https://www.reddit.com/r/{name}/.json"

    # Plain subreddit name — letters/digits/underscores only
    if url and "/" not in url and "." not in url:
        return f"https://www.reddit.com/r/{url}/.json"

    # Already a reddit.com URL missing /.json
    if "reddit.com" in url:
        return url + "/.json"

    # Give up and return default
    return DEFAULTS["reddit_urls"][0].rstrip("/") + "/.json"


def reddit_url_to_display(json_url: str) -> str:
    """Convert a .json API URL back to a clean display URL."""
    return json_url.replace("/.json", "/").replace(".json", "/")
