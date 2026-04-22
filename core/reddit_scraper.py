"""Reddit IPTV Scraper — fetches posts from r/IPTV_ZONENEW, finds and decodes
base64-encoded IPTV credentials, and optionally tests them via the Xtreme Codes API."""
from __future__ import annotations

import re
import base64
import hashlib
import time
import threading
import queue
from dataclasses import dataclass, asdict, field
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PyQt5.QtCore import QObject, pyqtSignal, QTimer

# Optional: pycryptodome for paste.sh AES decryption
try:
    from Crypto.Cipher import AES as _AES
    from Crypto.Protocol.KDF import PBKDF2 as _PBKDF2
    from Crypto.Hash import SHA512 as _SHA512
    _HAS_AES = True
except ImportError:
    _HAS_AES = False

# ── Reddit settings ────────────────────────────────────────────────────────────
SUBREDDIT = "IPTV_ZONENEW"
REDDIT_JSON_URL = f"https://www.reddit.com/r/{SUBREDDIT}/.json"
POSTS_PER_PAGE = 100

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

# ── Paste-site raw URL resolver ────────────────────────────────────────────────
def _to_raw_url(url: str) -> str:
    """Convert a paste-site URL to its raw-text equivalent, or return url unchanged."""
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        path = p.path

        if "pastebin.com" in host:
            if not path.startswith("/raw/"):
                return f"https://pastebin.com/raw{path}"
        elif "paste.ee" in host:
            return f"https://paste.ee/r{path.replace('/p/', '/', 1)}"
        elif "hastebin.com" in host:
            if "/raw/" not in path:
                return f"https://hastebin.com/raw{path}"
        elif "toptal.com" in host and "hastebin" in url:
            return url.replace("/developers/hastebin/", "/developers/hastebin/raw/", 1)
        elif "ghostbin.co" in host or "ghostbin.com" in host:
            if not path.rstrip("/").endswith("raw"):
                return url.rstrip("/") + "/raw"
        elif "rentry.co" in host or "rentry.org" in host:
            if not path.rstrip("/").endswith("raw"):
                return f"https://rentry.co{path.rstrip('/')}/raw"
        elif "dpaste.com" in host:
            if not path.endswith(".txt"):
                return f"https://dpaste.com{path}.txt"
        elif "paste.fo" in host or "pasteio.com" in host:
            if "/raw/" not in path:
                return url.rstrip("/") + "/raw"
    except Exception:
        pass
    return url


# ── Patterns ──────────────────────────────────────────────────────────────────
# Base64 blocks — at least 40 chars
_B64 = re.compile(r'(?<![A-Za-z0-9+/=])([A-Za-z0-9+/]{40,}={0,2})(?![A-Za-z0-9+/=])')

# Paste-site URLs inside post bodies
_PASTE_URL = re.compile(
    r'https?://(?:'
    r'paste\.sh|'
    r'pastebin\.com|paste\.ee|hastebin\.com|ghostbin\.co|ghostbin\.com|'
    r'rentry\.co|rentry\.org|dpaste\.com|pasteio\.com|paste\.fo|'
    r'toptal\.com/developers/hastebin'
    r')/\S+'
)

# Paste-site hostnames for Source 3/4 checks
_PASTE_HOSTS = [
    "paste.sh", "pastebin.com", "paste.ee", "hastebin", "ghostbin",
    "rentry", "dpaste", "paste.fo", "pasteio",
]

# ── Credential patterns ────────────────────────────────────────────────────────
# FIX: expanded character classes, more formats, broader API coverage.

# Format 1: pipe-separated  http://server|user|pass
_CRED_PIPE = re.compile(
    r'(https?://[^\s|<>\'"]{6,})\s*\|\s*([^\s|<>\'"]{3,60})\s*\|\s*([^\s|<>\'"]{3,60})'
)

# Format 2: space/newline-separated  http://server user pass
# FIX: allow @, !, # in username/password — many providers use them
_CRED_SPACE = re.compile(
    r'(https?://\S{6,})\s+([A-Za-z0-9_.@\-]{3,60})\s+([A-Za-z0-9_.@\-!#]{3,60})(?:\s|$)'
)

# Format 3: any URL with username= and password= query params
# FIX: was limited to /player_api.php and /get.php — now catches ANY endpoint
_CRED_API = re.compile(
    r'(https?://[^?\s]{6,})[^\s?]*\?[^\s]*?[?&]?username=([^&\s]{3,60})[^\s]*?&[^\s]*?password=([^\s&]{3,60})'
)

# Format 4: labeled block  (Server: URL / Username: user / Password: pass)
# FIX: this entire format was missing — very common in human-written posts
# Allows up to 4 intervening lines between each label
_CRED_LABELED = re.compile(
    r'(?:server[_ ]?(?:url)?|url|host|link|m3u|portal)\s*[:=]\s*(https?://[^\s\r\n]+)'
    r'(?:[^\r\n]*[\r\n]+){0,4}'
    r'(?:user(?:name)?|login|usr)\s*[:=]\s*([^\s\r\n]{3,60})'
    r'(?:[^\r\n]*[\r\n]+){0,4}'
    r'(?:pass(?:word)?|pwd|pw)\s*[:=]\s*([^\s\r\n]{3,60})',
    re.IGNORECASE
)


# ── Data model ────────────────────────────────────────────────────────────────
@dataclass
class RedditEntry:
    """One IPTV credential set extracted from a Reddit post."""
    post_id:           str   = ""
    post_title:        str   = ""
    post_url:          str   = ""
    post_date:         str   = ""
    post_timestamp:    float = 0.0
    server:            str   = ""
    username:          str   = ""
    password:          str   = ""
    source_type:       str   = "post"  # post | post_b64 | comment | paste | paste_b64
    source_url:        str   = ""

    # Filled in after API test
    status:            str   = "untested"
    account_status:    str   = ""
    active_connections: int  = 0
    max_connections:   int   = 0
    expiry:            str   = ""
    live_channels:     int   = 0
    vod_count:         int   = 0
    m3u_url:           str   = ""
    error_message:     str   = ""
    last_tested:       str   = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RedditEntry":
        valid = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**valid)

    def unique_key(self) -> str:
        return f"{self.server}|{self.username}|{self.password}"


# ── Scraper ───────────────────────────────────────────────────────────────────
class RedditScraper(QObject):
    """Background worker that scrapes Reddit posts and emits RedditEntry objects."""

    entry_found      = pyqtSignal(object)        # RedditEntry
    progress         = pyqtSignal(int, int, str)  # current, total, message
    finished         = pyqtSignal(str)            # summary message
    scrape_error     = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_event = threading.Event()
        self._queue: queue.Queue = queue.Queue()
        self._session = self._make_session()
        self._scan_comments = True
        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._drain_queue)

    # ── public API ──────────────────────────────────────────────────────────
    def start(self, max_pages: int = 5, reddit_json_urls: list = None,
              scan_comments: bool = True):
        """Start scraping.

        Args:
            max_pages:        Reddit pages to fetch (100 posts each).
            reddit_json_urls: Reddit .json API URLs to scan.
            scan_comments:    Also fetch and scan each post's top comments.
                              Finds far more credentials (esp. when the OP
                              puts creds in the first comment to dodge automod)
                              but makes the scan 2–3× slower.
        """
        self._stop_event.clear()
        self._json_urls = reddit_json_urls or [REDDIT_JSON_URL]
        self._scan_comments = scan_comments
        self._timer.start()
        t = threading.Thread(target=self._run, args=(max_pages,), daemon=True)
        t.start()

    def stop(self):
        self._stop_event.set()

    # ── internal ────────────────────────────────────────────────────────────
    def _make_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update(HEADERS)
        retry = Retry(total=3, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        return s

    def _drain_queue(self):
        count = 0
        while not self._queue.empty() and count < 15:
            try:
                kind, data = self._queue.get_nowait()
            except queue.Empty:
                break
            if kind == "entry":
                self.entry_found.emit(data)
            elif kind == "progress":
                self.progress.emit(*data)
            elif kind == "finished":
                self._timer.stop()
                self.finished.emit(data)
                return
            elif kind == "error":
                self.scrape_error.emit(data)
            count += 1

    def _run(self, max_pages: int):
        try:
            all_posts = []
            for json_url in self._json_urls:
                if self._stop_event.is_set():
                    break
                sub_posts = self._fetch_posts(max_pages, json_url)
                all_posts.extend(sub_posts)

            if not all_posts:
                self._queue.put(("finished", "No posts fetched from Reddit."))
                return

            seen: set = set()
            found = 0
            total = len(all_posts)

            for i, post in enumerate(all_posts):
                if self._stop_event.is_set():
                    break
                self._queue.put(("progress", (
                    i + 1, total,
                    f"Scanning post {i + 1}/{total}: {post['title'][:55]}…"
                )))
                for entry in self._process_post(post):
                    k = entry.unique_key()
                    if k not in seen:
                        seen.add(k)
                        found += 1
                        self._queue.put(("entry", entry))
                if i < total - 1:
                    time.sleep(0.3)

            self._queue.put(("finished",
                f"Done! {found} unique credential(s) from {total} post(s)."))
        except Exception as exc:
            self._queue.put(("error", str(exc)))
            self._queue.put(("finished", "Scan encountered an error."))

    # ── Reddit fetch ─────────────────────────────────────────────────────────
    def _fetch_posts(self, max_pages: int, json_url: str = None) -> list:
        target_url = json_url or REDDIT_JSON_URL
        sub_name = target_url.split("/r/")[-1].split("/")[0] if "/r/" in target_url else target_url

        posts = []
        after = None

        for page in range(max_pages):
            if self._stop_event.is_set():
                break
            self._queue.put(("progress", (
                page, max_pages,
                f"Fetching r/{sub_name} page {page + 1}/{max_pages}…"
            )))

            params = {"limit": POSTS_PER_PAGE, "raw_json": 1}
            if after:
                params["after"] = after

            try:
                resp = self._session.get(target_url, params=params, timeout=20)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                self._queue.put(("error", f"Reddit page {page + 1} failed: {exc}"))
                break

            children = data.get("data", {}).get("children", [])
            if not children:
                break

            for child in children:
                p = child.get("data", {})
                ts = float(p.get("created_utc", 0) or 0)
                posts.append({
                    "id":        p.get("id", ""),
                    "title":     p.get("title", "(no title)"),
                    "url":       "https://www.reddit.com" + p.get("permalink", ""),
                    "link_url":  p.get("url", ""),
                    "selftext":  p.get("selftext", "") or "",
                    "timestamp": ts,
                    "date":      datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "",
                })

            after = data.get("data", {}).get("after")
            if not after:
                break
            time.sleep(1.2)

        return posts

    # ── Post processing ──────────────────────────────────────────────────────
    def _process_post(self, post: dict) -> list:
        entries = []
        selftext = post["selftext"]
        link_url = post.get("link_url", "")
        combined_text = f"{post['title']} {selftext} {link_url}"

        # --- Source 1: direct credentials in post body or link URL ---
        # FIX: was only checking selftext — now checks link_url too.
        # Catches direct API URLs posted as the submission link.
        for text_src in (selftext, link_url):
            if not text_src:
                continue
            for cred in self._extract_creds(text_src):
                entries.append(self._make_entry(
                    post, *cred, source_type="post", source_url=post["url"]))

        # --- Source 2: base64 in post body → may decode to a paste URL ---
        for decoded in self._decode_b64_from_text(selftext):
            decoded = decoded.strip()
            if decoded.startswith(("http://", "https://")):
                content = self._fetch_paste_content(decoded)
                if content:
                    for cred in self._extract_creds(content):
                        entries.append(self._make_entry(
                            post, *cred, source_type="paste", source_url=decoded))
                    for sub_decoded in self._decode_b64_from_text(content):
                        for cred in self._extract_creds(sub_decoded):
                            entries.append(self._make_entry(
                                post, *cred, source_type="paste_b64", source_url=decoded))
            else:
                for cred in self._extract_creds(decoded):
                    entries.append(self._make_entry(
                        post, *cred, source_type="post_b64", source_url=post["url"]))

        # --- Source 3: paste links anywhere in the combined post text ---
        paste_urls = list(dict.fromkeys(_PASTE_URL.findall(combined_text)))
        for purl in paste_urls:
            if self._stop_event.is_set():
                break
            content = self._fetch_paste_content(purl)
            if not content:
                continue
            for cred in self._extract_creds(content):
                entries.append(self._make_entry(
                    post, *cred, source_type="paste", source_url=purl))
            for decoded in self._decode_b64_from_text(content):
                for cred in self._extract_creds(decoded):
                    entries.append(self._make_entry(
                        post, *cred, source_type="paste_b64", source_url=purl))

        # --- Source 4: post link_url is itself a paste site ---
        if link_url and any(s in link_url for s in _PASTE_HOSTS) and link_url not in paste_urls:
            content = self._fetch_paste_content(link_url)
            if content:
                for cred in self._extract_creds(content):
                    entries.append(self._make_entry(
                        post, *cred, source_type="paste", source_url=link_url))
                for decoded in self._decode_b64_from_text(content):
                    for cred in self._extract_creds(decoded):
                        entries.append(self._make_entry(
                            post, *cred, source_type="paste_b64", source_url=link_url))

        # --- Source 5: top-level comments ---
        # FIX: many IPTV posts put credentials in the first comment to dodge
        # automod. Without this, those credentials are completely invisible.
        if self._scan_comments and not self._stop_event.is_set():
            for comment_body in self._fetch_comments(post):
                if self._stop_event.is_set():
                    break
                if not comment_body:
                    continue

                # Direct credentials in comment
                for cred in self._extract_creds(comment_body):
                    entries.append(self._make_entry(
                        post, *cred, source_type="comment", source_url=post["url"]))

                # Base64 in comment
                for decoded in self._decode_b64_from_text(comment_body):
                    decoded = decoded.strip()
                    if decoded.startswith(("http://", "https://")):
                        content = self._fetch_paste_content(decoded)
                        if content:
                            for cred in self._extract_creds(content):
                                entries.append(self._make_entry(
                                    post, *cred, source_type="paste", source_url=decoded))
                    else:
                        for cred in self._extract_creds(decoded):
                            entries.append(self._make_entry(
                                post, *cred, source_type="comment_b64", source_url=post["url"]))

                # Paste links inside comments
                for purl in _PASTE_URL.findall(comment_body):
                    if self._stop_event.is_set():
                        break
                    if purl in paste_urls:
                        continue   # already processed above
                    content = self._fetch_paste_content(purl)
                    if content:
                        for cred in self._extract_creds(content):
                            entries.append(self._make_entry(
                                post, *cred, source_type="paste", source_url=purl))

        return entries

    def _make_entry(self, post: dict, server: str, username: str, password: str,
                    source_type: str, source_url: str) -> RedditEntry:
        return RedditEntry(
            post_id=post["id"],
            post_title=post["title"],
            post_url=post["url"],
            post_date=post["date"],
            post_timestamp=post["timestamp"],
            server=server,
            username=username,
            password=password,
            source_type=source_type,
            source_url=source_url,
            m3u_url=f"{server}/get.php?username={username}&password={password}&type=m3u_plus",
        )

    # ── Comment fetching ─────────────────────────────────────────────────────
    def _fetch_comments(self, post: dict) -> list:
        """Fetch the body text of the top 10 root-level comments for a post.

        Reddit puts credentials in comments far more often than in post bodies
        because automod on many IPTV subreddits removes posts with raw URLs.
        """
        try:
            # post["url"] = https://www.reddit.com/r/sub/comments/id/title/
            comment_url = post["url"].rstrip("/") + ".json"
            resp = self._session.get(
                comment_url,
                params={"limit": 10, "depth": 1, "raw_json": 1},
                timeout=12,
            )
            resp.raise_for_status()
            data = resp.json()

            # Reddit returns [post_listing, comment_listing]
            if not isinstance(data, list) or len(data) < 2:
                return []

            children = data[1].get("data", {}).get("children", [])
            return [
                c.get("data", {}).get("body", "") or ""
                for c in children
                if c.get("kind") == "t1" and c.get("data", {}).get("body")
            ]
        except Exception:
            return []

    # ── Text fetching helpers ─────────────────────────────────────────────────
    def _fetch_text(self, url: str) -> str:
        try:
            resp = self._session.get(url, timeout=12)
            resp.raise_for_status()
            return resp.text
        except Exception:
            return ""

    def _fetch_paste_sh(self, url: str) -> str:
        """Fetch and AES-decrypt a paste.sh encrypted paste."""
        if not _HAS_AES:
            return ""
        try:
            parsed = urlparse(url)
            paste_id = parsed.path.strip("/")
            fragment_key = re.sub(r"[^A-Za-z0-9_\-]", "", parsed.fragment)

            page_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            resp = self._session.get(page_url, timeout=15)
            resp.raise_for_status()
            html = resp.text

            ct_match = re.search(r'"(U2FsdGVkX1[A-Za-z0-9+/\r\n]+=*)"', html)
            if not ct_match:
                return ""
            ciphertext_b64 = ct_match.group(1).replace("\r", "").replace("\n", "")

            sk_match = re.search(
                r'name=["\']serverkey["\'].*?value=["\']([^"\']*)["\']', html, re.DOTALL)
            tp_match = re.search(
                r'name=["\']type["\'].*?value=["\']([^"\']*)["\']', html, re.DOTALL)
            serverkey  = sk_match.group(1) if sk_match else ""
            paste_type = tp_match.group(1) if tp_match else ""

            passphrase = paste_id + serverkey + fragment_key + "https://paste.sh"
            decrypted  = _decrypt_paste_sh(ciphertext_b64, passphrase, paste_type)

            if paste_type == "v3" and decrypted and "\n\n" in decrypted:
                decrypted = decrypted.split("\n\n", 1)[1]

            return decrypted
        except Exception:
            return ""

    def _fetch_paste_content(self, url: str) -> str:
        """Fetch content from any paste URL, routing paste.sh through AES decryption."""
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            if "paste.sh" in host:
                return self._fetch_paste_sh(url)
            raw = _to_raw_url(url)
            return self._fetch_text(raw)
        except Exception:
            return ""

    # ── Base64 ───────────────────────────────────────────────────────────────
    def _decode_b64_from_text(self, text: str, depth: int = 0) -> list:
        """Find and decode all base64 blobs in text. Handles 3 levels of nesting."""
        if depth > 3 or not text:
            return []
        results = []
        for candidate in _B64.findall(text):
            decoded = _try_b64_decode(candidate)
            if decoded and _looks_like_iptv(decoded):
                results.append(decoded)
                results.extend(self._decode_b64_from_text(decoded, depth + 1))
        return results

    # ── Credential extraction ─────────────────────────────────────────────────
    def _extract_creds(self, text: str) -> list:
        """Return (server, username, password) tuples found in text.

        Applies all four patterns plus URL query-param parsing, then sanity-
        checks each match to filter out false positives.
        """
        found = []
        seen  = set()

        # ── Pattern-based extraction ──────────────────────────────────────────
        for pat in (_CRED_PIPE, _CRED_SPACE, _CRED_API, _CRED_LABELED):
            for m in pat.finditer(text):
                server   = m.group(1).rstrip("/").strip()
                username = m.group(2).strip()
                password = m.group(3).strip()
                self._add_cred(server, username, password, found, seen)

        # ── URL query-param parsing ───────────────────────────────────────────
        # FIX: catches any API endpoint with username= & password= params,
        # not just /player_api.php and /get.php.
        for url_m in re.finditer(r'https?://\S+', text):
            raw_url = url_m.group(0).rstrip(".,;)\"'")
            if "username=" not in raw_url or "password=" not in raw_url:
                continue
            try:
                parsed   = urlparse(raw_url)
                params   = parse_qs(parsed.query, keep_blank_values=False)
                username = (params.get("username") or [""])[0]
                password = (params.get("password") or [""])[0]
                server   = f"{parsed.scheme}://{parsed.netloc}"
                self._add_cred(server, username, password, found, seen)
            except Exception:
                pass

        return found

    def _add_cred(self, server: str, username: str, password: str,
                  found: list, seen: set) -> None:
        """Apply sanity checks and append to found if the credential looks real."""
        if not server.startswith("http"):
            return
        if len(username) < 3 or len(password) < 3:
            return
        if len(username) > 60 or len(password) > 60:
            return
        if username == password:
            return
        if " " in username or " " in password:
            return
        # usernames don't have slashes; allow slashes in passwords
        if "/" in username:
            return

        key = f"{server}|{username}|{password}"
        if key not in seen:
            seen.add(key)
            found.append((server, username, password))


# ── Tester ────────────────────────────────────────────────────────────────────
class RedditTester(QObject):
    """Tests a list of RedditEntry objects via the Xtreme Codes API."""

    entry_tested   = pyqtSignal(int, object)   # (original_index, updated RedditEntry)
    test_progress  = pyqtSignal(int, int)       # current, total
    test_finished  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_event = threading.Event()
        self._queue: queue.Queue = queue.Queue()
        self._session = _make_test_session()
        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._drain_queue)

    def start(self, entries: list, indices: list, max_workers: int = 6):
        """entries: list of RedditEntry; indices: their positions in the UI table."""
        self._stop_event.clear()
        self._timer.start()
        t = threading.Thread(
            target=self._run, args=(entries, indices, max_workers), daemon=True
        )
        t.start()

    def stop(self):
        self._stop_event.set()

    def _drain_queue(self):
        count = 0
        while not self._queue.empty() and count < 15:
            try:
                kind, data = self._queue.get_nowait()
            except queue.Empty:
                break
            if kind == "result":
                idx, entry = data
                self.entry_tested.emit(idx, entry)
            elif kind == "progress":
                self.test_progress.emit(*data)
            elif kind == "finished":
                self._timer.stop()
                self.test_finished.emit()
                return
            count += 1

    def _run(self, entries: list, indices: list, max_workers: int):
        total = len(entries)
        done  = 0

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(self._test_one, e): (idx, e)
                       for idx, e in zip(indices, entries)}
            for future in futures:
                if self._stop_event.is_set():
                    break
                idx, _ = futures[future]
                try:
                    result = future.result(timeout=60)
                except Exception as exc:
                    result = futures[future][1]
                    result.status = "error"
                    result.error_message = str(exc)[:80]
                self._queue.put(("result", (idx, result)))
                done += 1
                self._queue.put(("progress", (done, total)))

        self._queue.put(("finished", None))

    def _test_one(self, entry: RedditEntry) -> RedditEntry:
        entry.last_tested = datetime.now().strftime("%Y-%m-%d %H:%M")
        s = entry.server
        u = entry.username
        pw = entry.password

        try:
            api_url = f"{s}/player_api.php?username={u}&password={pw}"
            resp = self._session.get(api_url, timeout=15)

            if resp.status_code == 403:
                entry.status = "blocked"; entry.error_message = "403 Forbidden"; return entry
            if resp.status_code == 404:
                entry.status = "dead";    entry.error_message = "Server not found (404)"; return entry
            if resp.status_code != 200:
                entry.status = "error";   entry.error_message = f"HTTP {resp.status_code}"; return entry

            try:
                data = resp.json()
            except ValueError:
                from core.m3u_parser import parse_m3u
                chs = parse_m3u(resp.text)
                entry.live_channels = len(chs)
                entry.status = "active" if chs else "dead"
                entry.account_status = "M3U mode"
                return entry

            ui = data.get("user_info", {})

            if not ui.get("auth", 0):
                entry.status = "blocked"; entry.error_message = "Auth failed"; return entry

            entry.account_status   = ui.get("status", "")
            entry.max_connections  = int(ui.get("max_connections", 0) or 0)
            entry.active_connections = int(ui.get("active_cons", 0) or 0)

            st = entry.account_status.lower()
            if st == "expired":
                entry.status = "expired"
            elif st in ("banned", "disabled"):
                entry.status = "blocked"
            else:
                entry.status = "active"

            exp_ts = ui.get("exp_date")
            if exp_ts and str(exp_ts) not in ("None", "0", ""):
                try:
                    exp_dt = datetime.fromtimestamp(int(exp_ts))
                    days   = (exp_dt - datetime.now()).days
                    entry.expiry = f"{exp_dt.strftime('%Y-%m-%d')} ({days}d)"
                except Exception:
                    entry.expiry = str(exp_ts)
            else:
                entry.expiry = "No expiry"

            # Live channel count
            try:
                lr = self._session.get(
                    f"{s}/player_api.php?username={u}&password={pw}&action=get_live_streams",
                    timeout=15)
                ld = lr.json()
                if isinstance(ld, list):
                    entry.live_channels = len(ld)
            except Exception:
                pass

            # VOD count
            try:
                vr = self._session.get(
                    f"{s}/player_api.php?username={u}&password={pw}&action=get_vod_streams",
                    timeout=12)
                vd = vr.json()
                if isinstance(vd, list):
                    entry.vod_count = len(vd)
            except Exception:
                pass

        except requests.exceptions.ConnectTimeout:
            entry.status = "dead"; entry.error_message = "Connection timeout"
        except requests.exceptions.ConnectionError:
            entry.status = "dead"; entry.error_message = "Cannot connect"
        except Exception as exc:
            entry.status = "error"; entry.error_message = str(exc)[:80]

        return entry


# ── Helpers ───────────────────────────────────────────────────────────────────
def _try_b64_decode(candidate: str) -> str:
    """Try standard and URL-safe base64 decoding; return decoded str or ''."""
    for variant in [candidate, candidate + "=" * ((4 - len(candidate) % 4) % 4)]:
        for decode_fn in [base64.b64decode, base64.urlsafe_b64decode]:
            try:
                raw  = decode_fn(variant)
                text = raw.decode("utf-8", errors="replace")
                return text
            except Exception:
                pass
    return ""


def _looks_like_iptv(text: str) -> bool:
    """Heuristic: does decoded text resemble IPTV content?"""
    stripped = text.strip()
    if stripped.startswith(("http://", "https://")):
        return True
    keywords = ["player_api", ":8080", ":25461", ":8000", ":8181",
                "m3u", "username=", "password=", "get.php",
                "xtream", "iptv", "stream"]
    return any(kw in text.lower() for kw in keywords)


def _decrypt_paste_sh(ciphertext_b64: str, passphrase: str, paste_type: str) -> str:
    """Decrypt a paste.sh CryptoJS AES-256-CBC ciphertext."""
    if not _HAS_AES:
        return ""
    try:
        raw = base64.b64decode(ciphertext_b64)
        if raw[:8] != b"Salted__":
            return ""
        salt       = raw[8:16]
        ciphertext = raw[16:]
        pw_bytes   = passphrase.encode("utf-8")

        if paste_type == "v1":
            key, iv = _evp_bytes_to_key_sha512(pw_bytes, salt)
        else:
            dk  = _PBKDF2(pw_bytes, salt, dkLen=48, count=1, hmac_hash_module=_SHA512)
            key = dk[:32]
            iv  = dk[32:48]

        cipher    = _AES.new(key, _AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(ciphertext)
        pad = decrypted[-1]
        if isinstance(pad, int) and 1 <= pad <= 16:
            decrypted = decrypted[:-pad]
        return decrypted.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _evp_bytes_to_key_sha512(password: bytes, salt: bytes,
                              key_len: int = 32, iv_len: int = 16) -> tuple:
    """OpenSSL EVP_BytesToKey with SHA-512, 1 iteration (paste.sh v1 KDF)."""
    import hashlib as _hl
    d = b""
    d_i = b""
    while len(d) < key_len + iv_len:
        d_i = _hl.sha512(d_i + password + salt).digest()
        d += d_i
    return d[:key_len], d[key_len:key_len + iv_len]


def _make_test_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "VLC/3.0.18 LibVLC/3.0.18",
        "Accept": "*/*",
    })
    retry = Retry(total=2, backoff_factor=1, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s
