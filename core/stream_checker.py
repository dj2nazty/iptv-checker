"""Multi-threaded stream checker using ffprobe."""

import subprocess
import time
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt5.QtCore import QObject, pyqtSignal, QTimer

from models.channel import Channel
from utils.ffprobe import get_ffprobe_path, probe_stream, parse_probe_result
from utils.constants import DEFAULT_CONCURRENCY, DEFAULT_TIMEOUT


class StreamChecker(QObject):
    """Checks streams concurrently and reports results via Qt signals.

    Uses a thread-safe queue + QTimer polling to avoid flooding the UI thread.
    """

    channel_checked = pyqtSignal(int, object)
    scan_progress = pyqtSignal(int, int)
    scan_finished = pyqtSignal()
    scan_error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_event = threading.Event()
        self._executor = None
        self._ffprobe_path = None
        self._result_queue = queue.Queue()
        self._total = 0
        self._checked = 0
        self._scan_done = False

        # Timer polls the result queue from the main thread
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(150)  # poll every 150ms
        self._poll_timer.timeout.connect(self._poll_results)

    def start_scan(self, channels: list[Channel],
                   max_workers: int = DEFAULT_CONCURRENCY,
                   timeout: int = DEFAULT_TIMEOUT):
        """Start scanning channels in a background thread."""
        self._stop_event.clear()
        self._total = len(channels)
        self._checked = 0
        self._scan_done = False

        # Clear the queue
        while not self._result_queue.empty():
            try:
                self._result_queue.get_nowait()
            except queue.Empty:
                break

        # Resolve ffprobe path once before spawning workers
        try:
            self._ffprobe_path = get_ffprobe_path()
        except Exception as e:
            self.scan_error.emit(f"Cannot find ffprobe: {e}")
            self.scan_finished.emit()
            return

        # Start polling timer
        self._poll_timer.start()

        thread = threading.Thread(
            target=self._run_scan,
            args=(channels, max_workers, timeout),
            daemon=True,
        )
        thread.start()

    def stop_scan(self):
        """Signal all workers to stop."""
        self._stop_event.set()
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def _poll_results(self):
        """Called by QTimer on the main thread — drains the result queue."""
        batch = 0
        while not self._result_queue.empty() and batch < 50:
            try:
                msg_type, data = self._result_queue.get_nowait()
            except queue.Empty:
                break

            if msg_type == "result":
                idx, channel = data
                self.channel_checked.emit(idx, channel)
            elif msg_type == "progress":
                current, total = data
                self.scan_progress.emit(current, total)
            elif msg_type == "error":
                self.scan_error.emit(data)
            elif msg_type == "finished":
                self._poll_timer.stop()
                self.scan_finished.emit()
                return

            batch += 1

    def _run_scan(self, channels: list[Channel],
                  max_workers: int, timeout: int):
        """Worker method that runs in a background thread."""
        total = len(channels)
        checked = 0

        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            futures = {}
            for idx, channel in enumerate(channels):
                if self._stop_event.is_set():
                    break
                future = self._executor.submit(
                    self._check_single, channel, timeout
                )
                futures[future] = idx

            for future in as_completed(futures):
                if self._stop_event.is_set():
                    break
                idx = futures[future]
                try:
                    updated = future.result()
                    self._result_queue.put(("result", (idx, updated)))
                except Exception as e:
                    channels[idx].status = "error"
                    channels[idx].error_message = str(e)
                    self._result_queue.put(("result", (idx, channels[idx])))

                checked += 1
                self._result_queue.put(("progress", (checked, total)))

        except Exception as e:
            self._result_queue.put(("error", str(e)))
        finally:
            self._executor.shutdown(wait=False)
            self._executor = None
            self._result_queue.put(("finished", None))

    def _check_single(self, channel: Channel, timeout: int) -> Channel:
        """Check a single channel with ffprobe."""
        if self._stop_event.is_set():
            return channel

        start = time.time()

        # Skip channels without URLs (e.g. series placeholders)
        if not channel.stream_url:
            channel.status = "dead"
            channel.error_message = "No stream URL"
            return channel

        if self._stop_event.is_set():
            return channel

        # Probe directly with ffprobe
        try:
            data = probe_stream(
                channel.stream_url,
                timeout=timeout,
                ffprobe_path=self._ffprobe_path,
            )
            info = parse_probe_result(data)
            channel.status = "live"
            channel.video_codec = info["video_codec"]
            channel.audio_codec = info["audio_codec"]
            channel.resolution = info["resolution"]
            channel.video_bitrate = info["video_bitrate"]
            channel.audio_bitrate = info["audio_bitrate"]
            channel.fps = info["fps"]
            channel.container = info["container"]
        except subprocess.TimeoutExpired:
            channel.status = "timeout"
            channel.error_message = "ffprobe timeout"
        except Exception as e:
            channel.status = "dead"
            channel.error_message = f"Probe failed: {str(e)[:80]}"

        channel.probe_duration_ms = int((time.time() - start) * 1000)
        return channel
