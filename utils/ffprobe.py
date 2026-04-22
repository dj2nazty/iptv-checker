"""ffprobe binary manager — locates, downloads, and wraps ffprobe."""

import json
import os
import subprocess
import sys
import zipfile
import tempfile
import requests

from utils.constants import FFPROBE_DOWNLOAD_URL


def _app_data_dir() -> str:
    """Return the app data directory for storing ffprobe."""
    base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    path = os.path.join(base, "iptv-checker")
    os.makedirs(path, exist_ok=True)
    return path


def get_ffprobe_path() -> str:
    """Return path to ffprobe.exe, downloading if necessary.

    Search order:
    1. Bundled with PyInstaller exe (sys._MEIPASS)
    2. App data directory
    3. System PATH
    4. Download from GitHub
    """
    # 1. PyInstaller bundle
    if hasattr(sys, "_MEIPASS"):
        bundled = os.path.join(sys._MEIPASS, "ffprobe.exe")
        if os.path.isfile(bundled):
            return bundled

    # 2. App data directory
    app_dir = _app_data_dir()
    local_path = os.path.join(app_dir, "ffprobe.exe")
    if os.path.isfile(local_path):
        return local_path

    # 3. System PATH
    import shutil
    system_path = shutil.which("ffprobe")
    if system_path:
        return system_path

    # 4. Download
    return _download_ffprobe(local_path)


def _download_ffprobe(dest_path: str) -> str:
    """Download ffprobe from GitHub releases and extract it."""
    print(f"Downloading ffprobe to {dest_path}...")
    tmp = tempfile.mktemp(suffix=".zip")
    try:
        resp = requests.get(FFPROBE_DOWNLOAD_URL, stream=True, timeout=120)
        resp.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        # Extract ffprobe.exe from the zip
        with zipfile.ZipFile(tmp) as zf:
            for name in zf.namelist():
                if name.endswith("ffprobe.exe"):
                    # Extract to dest_path
                    with zf.open(name) as src, open(dest_path, "wb") as dst:
                        dst.write(src.read())
                    return dest_path

        raise FileNotFoundError("ffprobe.exe not found in downloaded archive")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def probe_stream(url: str, timeout: int = 8, ffprobe_path: str = None) -> dict:
    """Probe a stream URL with ffprobe and return parsed JSON.

    Returns dict with keys: 'streams', 'format', or raises an exception.
    """
    if ffprobe_path is None:
        ffprobe_path = get_ffprobe_path()

    cmd = [
        ffprobe_path,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        "-user_agent", "VLC/3.0.18 LibVLC/3.0.18",
        "-timeout", str(timeout * 1_000_000),  # microseconds
        "-analyzeduration", "3000000",  # 3 seconds max analysis
        "-probesize", "1000000",  # 1MB probe size
        url,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout + 2,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )

    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed (exit {result.returncode}): {result.stderr[:200]}")

    return json.loads(result.stdout)


def parse_probe_result(data: dict) -> dict:
    """Extract useful fields from ffprobe JSON output.

    Returns dict with: video_codec, audio_codec, resolution, video_bitrate,
    audio_bitrate, fps, container.
    """
    info = {
        "video_codec": "",
        "audio_codec": "",
        "resolution": "",
        "video_bitrate": "",
        "audio_bitrate": "",
        "fps": "",
        "container": "",
    }

    streams = data.get("streams", [])
    fmt = data.get("format", {})

    for stream in streams:
        codec_type = stream.get("codec_type", "")
        if codec_type == "video" and not info["video_codec"]:
            info["video_codec"] = stream.get("codec_name", "").upper()
            w = stream.get("width", 0)
            h = stream.get("height", 0)
            if w and h:
                info["resolution"] = f"{w}x{h}"
            # Bitrate
            br = stream.get("bit_rate")
            if br:
                info["video_bitrate"] = f"{int(br) // 1000} kbps"
            # FPS from r_frame_rate (fraction like "30000/1001")
            rfr = stream.get("r_frame_rate", "")
            if "/" in rfr:
                num, den = rfr.split("/")
                try:
                    fps_val = int(num) / int(den)
                    info["fps"] = f"{fps_val:.2f}"
                except (ValueError, ZeroDivisionError):
                    pass
            elif rfr:
                info["fps"] = rfr

        elif codec_type == "audio" and not info["audio_codec"]:
            info["audio_codec"] = stream.get("codec_name", "").upper()
            br = stream.get("bit_rate")
            if br:
                info["audio_bitrate"] = f"{int(br) // 1000} kbps"

    info["container"] = fmt.get("format_name", "")

    # Fallback: if no per-stream video bitrate, try format-level
    if not info["video_bitrate"]:
        br = fmt.get("bit_rate")
        if br:
            info["video_bitrate"] = f"{int(br) // 1000} kbps"

    return info
