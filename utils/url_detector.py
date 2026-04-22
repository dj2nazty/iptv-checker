"""Detect whether a URL is an Xtreme Codes API link or a plain M3U URL."""
from __future__ import annotations

import re
from urllib.parse import urlparse, parse_qs


def detect_url_type(url: str) -> dict:
    """Analyze a URL and return its type and extracted credentials.

    Returns dict with:
        type: "xtreme_codes" | "m3u_url" | "unknown"
        server: (for xtreme_codes) base server URL
        username: (for xtreme_codes)
        password: (for xtreme_codes)
    """
    url = url.strip()
    result = {"type": "unknown"}

    # Check for player_api.php — definitive Xtreme Codes
    if "player_api.php" in url:
        return _parse_xtreme_api_url(url)

    # Check for get.php (Xtreme Codes M3U export endpoint)
    if "get.php" in url:
        return _parse_xtreme_get_url(url)

    # Check for /username/password/ direct stream pattern
    # Pattern: http://host:port/username/password/stream_id
    xtreme_direct = _parse_xtreme_direct_url(url)
    if xtreme_direct:
        return xtreme_direct

    # Check for M3U URL (by extension or content-type hint)
    if url.lower().endswith((".m3u", ".m3u8")):
        result["type"] = "m3u_url"
        return result

    # Could be M3U URL without extension — treat as M3U
    if url.startswith(("http://", "https://")):
        result["type"] = "m3u_url"

    return result


def _parse_xtreme_api_url(url: str) -> dict:
    """Parse an Xtreme Codes player_api.php URL."""
    parsed = urlparse(url)
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


def _parse_xtreme_get_url(url: str) -> dict:
    """Parse an Xtreme Codes get.php M3U export URL."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        server += f":{parsed.port}"
    username = params.get("username", [""])[0]
    password = params.get("password", [""])[0]
    if username and password:
        return {
            "type": "xtreme_codes",
            "server": server,
            "username": username,
            "password": password,
        }
    return {"type": "m3u_url"}


def _parse_xtreme_direct_url(url: str) -> dict | None:
    """Try to parse a direct Xtreme Codes stream URL.

    Pattern: http://host:port/username/password/stream_id.ext
    """
    match = re.match(
        r'^(https?://[^/]+)/([^/]+)/([^/]+)/\d+\.\w+$',
        url,
    )
    if match:
        return {
            "type": "xtreme_codes",
            "server": match.group(1),
            "username": match.group(2),
            "password": match.group(3),
        }
    return None
