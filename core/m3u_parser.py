"""M3U/M3U8 playlist parser."""

import re
from models.channel import Channel


# Regex patterns for EXTINF attributes
RE_TVG_NAME = re.compile(r'tvg-name="([^"]*)"')
RE_TVG_LOGO = re.compile(r'tvg-logo="([^"]*)"')
RE_GROUP_TITLE = re.compile(r'group-title="([^"]*)"')
RE_TVG_ID = re.compile(r'tvg-id="([^"]*)"')


def parse_m3u(content: str) -> list[Channel]:
    """Parse M3U content string into a list of Channel objects.

    Handles both #EXTM3U playlists and simple URL lists.
    """
    channels = []
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    current_name = ""
    current_group = ""
    current_logo = ""
    in_extinf = False

    for line in lines:
        line = line.strip()
        if not line or line == "#EXTM3U" or line.startswith("#EXTM3U "):
            continue

        if line.startswith("#EXTINF:"):
            # Parse attributes
            name_match = RE_TVG_NAME.search(line)
            logo_match = RE_TVG_LOGO.search(line)
            group_match = RE_GROUP_TITLE.search(line)

            # Channel display name is after the last comma
            comma_idx = line.rfind(",")
            if comma_idx != -1:
                current_name = line[comma_idx + 1:].strip()
            elif name_match:
                current_name = name_match.group(1)

            # Override with tvg-name if display name is empty
            if not current_name and name_match:
                current_name = name_match.group(1)

            current_logo = logo_match.group(1) if logo_match else ""
            current_group = group_match.group(1) if group_match else ""
            in_extinf = True
            continue

        # Skip other comment/directive lines
        if line.startswith("#"):
            continue

        # This should be a URL line
        if line.startswith(("http://", "https://", "rtmp://", "rtsp://")):
            channels.append(Channel(
                name=current_name or _name_from_url(line),
                group=current_group,
                logo_url=current_logo,
                stream_url=line,
                stream_type="live",
            ))
            # Reset for next entry
            current_name = ""
            current_group = ""
            current_logo = ""
            in_extinf = False

    return channels


def _name_from_url(url: str) -> str:
    """Extract a fallback name from a URL."""
    # Use the last path segment as name
    path = url.split("?")[0].rstrip("/")
    name = path.split("/")[-1] if "/" in path else url
    return name or "Unknown"


def parse_m3u_file(filepath: str) -> list[Channel]:
    """Parse an M3U file from disk."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    return parse_m3u(content)
