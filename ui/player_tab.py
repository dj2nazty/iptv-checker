"""Embedded VLC video player tab."""

import sys
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal

# Try importing VLC — if it fails, the player tab will show a friendly message
try:
    import vlc
    VLC_AVAILABLE = True
except (ImportError, OSError, FileNotFoundError):
    VLC_AVAILABLE = False


class PlayerTab(QWidget):
    """Tab with an embedded VLC video player for playing IPTV streams."""

    add_to_backup_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._current_name = ""
        self._current_url = ""
        self._is_playing = False
        self._vlc_instance = None
        self._player = None

        if VLC_AVAILABLE:
            try:
                self._vlc_instance = vlc.Instance([
                    "--no-xlib",
                    "--network-caching=3000",
                    "--http-reconnect",
                    "--live-caching=3000",
                    "--http-user-agent=VLC/3.0.18 LibVLC/3.0.18",
                ])
                self._player = self._vlc_instance.media_player_new()
            except Exception:
                self._vlc_instance = None
                self._player = None

        self._setup_ui()
        self._setup_timer()

    @property
    def vlc_ok(self) -> bool:
        return self._vlc_instance is not None and self._player is not None

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Now Playing Info ---
        info_bar = QHBoxLayout()
        info_bar.setContentsMargins(12, 8, 12, 8)

        self._channel_label = QLabel("No channel selected")
        self._channel_label.setObjectName("sectionLabel")
        self._channel_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #89b4fa;")
        info_bar.addWidget(self._channel_label, 1)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
        info_bar.addWidget(self._status_label)

        layout.addLayout(info_bar)

        # --- Video Frame ---
        self._video_frame = QFrame()
        self._video_frame.setStyleSheet("background-color: #000000;")
        self._video_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._video_frame.setMinimumHeight(400)
        layout.addWidget(self._video_frame, 1)

        if not self.vlc_ok:
            no_vlc = QLabel(
                "VLC is not installed or python-vlc could not find it.\n\n"
                "Install VLC media player (64-bit) from videolan.org\n"
                "then restart this app to enable the player."
            )
            no_vlc.setAlignment(Qt.AlignCenter)
            no_vlc.setStyleSheet("color: #f38ba8; font-size: 14px; padding: 40px;")
            no_vlc.setWordWrap(True)
            # Overlay on the video frame
            frame_layout = QVBoxLayout(self._video_frame)
            frame_layout.addWidget(no_vlc)

        # --- Controls Bar ---
        controls = QHBoxLayout()
        controls.setContentsMargins(12, 8, 12, 8)
        controls.setSpacing(12)

        self._play_btn = QPushButton("Play")
        self._play_btn.setFixedWidth(80)
        self._play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self._play_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setFixedWidth(80)
        self._stop_btn.clicked.connect(self.stop)
        controls.addWidget(self._stop_btn)

        # Volume
        controls.addWidget(QLabel("Vol:"))
        self._volume_slider = QSlider(Qt.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(80)
        self._volume_slider.setFixedWidth(120)
        self._volume_slider.valueChanged.connect(self._set_volume)
        controls.addWidget(self._volume_slider)

        self._volume_label = QLabel("80%")
        self._volume_label.setFixedWidth(40)
        controls.addWidget(self._volume_label)

        controls.addStretch()

        # Add to Backup button
        self._backup_btn = QPushButton("+ Add to Backup")
        self._backup_btn.setStyleSheet(
            "background-color: #f9e2af; color: #1e1e2e; font-weight: bold; padding: 8px 16px;"
        )
        self._backup_btn.clicked.connect(self.add_to_backup_requested.emit)
        controls.addWidget(self._backup_btn)

        # Fullscreen button
        self._fullscreen_btn = QPushButton("Fullscreen")
        self._fullscreen_btn.setFixedWidth(100)
        self._fullscreen_btn.clicked.connect(self._toggle_fullscreen)
        controls.addWidget(self._fullscreen_btn)

        layout.addLayout(controls)

    def _setup_timer(self):
        """Timer to update UI status periodically."""
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(1000)
        self._update_timer.timeout.connect(self._update_status)

    def play(self, name: str, url: str):
        """Play a stream by URL."""
        if not self.vlc_ok:
            self._status_label.setText("VLC not available")
            return

        self._current_name = name
        self._current_url = url

        self._channel_label.setText(name)
        self._status_label.setText("Connecting...")

        # Stop any current playback
        self._player.stop()

        # Set up media
        media = self._vlc_instance.media_new(url)
        media.add_option(":network-caching=3000")
        media.add_option(":http-user-agent=VLC/3.0.18 LibVLC/3.0.18")
        self._player.set_media(media)

        # Attach VLC to the video frame
        if sys.platform == "win32":
            self._player.set_hwnd(int(self._video_frame.winId()))
        elif sys.platform == "linux":
            self._player.set_xwindow(int(self._video_frame.winId()))
        elif sys.platform == "darwin":
            self._player.set_nsobject(int(self._video_frame.winId()))

        # Set volume and play
        self._player.audio_set_volume(self._volume_slider.value())
        self._player.play()
        self._is_playing = True
        self._play_btn.setText("Pause")
        self._update_timer.start()

    def stop(self):
        """Stop playback."""
        if self._player:
            self._player.stop()
        self._is_playing = False
        self._play_btn.setText("Play")
        self._status_label.setText("Stopped")
        self._update_timer.stop()

    def _toggle_play(self):
        if not self.vlc_ok or not self._current_url:
            return
        if self._is_playing:
            self._player.pause()
            self._is_playing = False
            self._play_btn.setText("Play")
        else:
            if self._player.get_state() in (vlc.State.Ended, vlc.State.Stopped):
                self.play(self._current_name, self._current_url)
            else:
                self._player.pause()
                self._is_playing = True
                self._play_btn.setText("Pause")

    def _set_volume(self, value):
        if self._player:
            self._player.audio_set_volume(value)
        self._volume_label.setText(f"{value}%")

    def _toggle_fullscreen(self):
        parent = self.window()
        if parent.isFullScreen():
            parent.showNormal()
            self._fullscreen_btn.setText("Fullscreen")
        else:
            parent.showFullScreen()
            self._fullscreen_btn.setText("Exit FS")

    def _update_status(self):
        """Update the status label with current playback info."""
        if not self.vlc_ok:
            return
        try:
            state = self._player.get_state()
        except Exception:
            return

        state_map = {
            vlc.State.NothingSpecial: "Idle",
            vlc.State.Opening: "Connecting...",
            vlc.State.Buffering: "Buffering...",
            vlc.State.Playing: "Playing",
            vlc.State.Paused: "Paused",
            vlc.State.Stopped: "Stopped",
            vlc.State.Ended: "Ended",
            vlc.State.Error: "Error",
        }
        status = state_map.get(state, "Unknown")

        if state == vlc.State.Playing:
            self._status_label.setStyleSheet("color: #a6e3a1; font-size: 12px;")
        elif state == vlc.State.Error:
            self._status_label.setStyleSheet("color: #f38ba8; font-size: 12px;")
            self._is_playing = False
            self._play_btn.setText("Play")
        elif state == vlc.State.Buffering:
            self._status_label.setStyleSheet("color: #f9e2af; font-size: 12px;")
        else:
            self._status_label.setStyleSheet("color: #a6adc8; font-size: 12px;")

        self._status_label.setText(status)

    def cleanup(self):
        """Clean up VLC resources."""
        self._update_timer.stop()
        if self._player:
            try:
                self._player.stop()
                self._player.release()
            except Exception:
                pass
        if self._vlc_instance:
            try:
                self._vlc_instance.release()
            except Exception:
                pass
