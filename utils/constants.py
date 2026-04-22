"""Application-wide constants."""

APP_NAME = "IPTV Stream Checker"
APP_VERSION = "2.1.3"

# Stream checking defaults
DEFAULT_CONCURRENCY = 10
MAX_CONCURRENCY = 50
DEFAULT_TIMEOUT = 8  # seconds per stream
MIN_TIMEOUT = 1
MAX_TIMEOUT = 30

# ffprobe
FFPROBE_DOWNLOAD_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
FFPROBE_TIMEOUT_EXTRA = 2  # extra seconds beyond stream timeout for subprocess kill

# Xtreme Codes API
XTREME_API_TIMEOUT = 30  # seconds

# UI
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800

# Table columns
COLUMN_HEADERS = [
    "#", "Name", "Group", "Status", "Resolution",
    "Video Codec", "Audio Codec", "Video Bitrate",
    "Audio Bitrate", "FPS", "Container"
]
