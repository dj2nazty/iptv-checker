"""Export channels to CSV and filtered M3U."""

import csv
from models.channel import Channel


def export_csv(channels: list[Channel], filepath: str):
    """Export all channels to a CSV file with full metadata."""
    headers = [
        "Name", "Group", "Status", "Stream URL", "Resolution",
        "Video Codec", "Audio Codec", "Video Bitrate", "Audio Bitrate",
        "FPS", "Container", "HTTP Status", "Error"
    ]

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for ch in channels:
            writer.writerow([
                ch.name, ch.group, ch.status, ch.stream_url,
                ch.resolution, ch.video_codec, ch.audio_codec,
                ch.video_bitrate, ch.audio_bitrate, ch.fps,
                ch.container, ch.http_status, ch.error_message,
            ])


def export_working_m3u(channels: list[Channel], filepath: str):
    """Export only working (live) channels as an M3U playlist."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for ch in channels:
            if ch.status == "live":
                logo = f' tvg-logo="{ch.logo_url}"' if ch.logo_url else ""
                group = f' group-title="{ch.group}"' if ch.group else ""
                f.write(f'#EXTINF:-1 tvg-name="{ch.name}"{logo}{group},{ch.name}\n')
                f.write(f"{ch.stream_url}\n")
