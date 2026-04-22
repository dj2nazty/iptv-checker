"""Data models and Qt table model for channels."""

from dataclasses import dataclass, field
from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex, QVariant
from utils.constants import COLUMN_HEADERS


@dataclass
class Channel:
    name: str = ""
    group: str = ""
    logo_url: str = ""
    stream_url: str = ""
    stream_type: str = "live"  # "live", "vod", "series"
    # Populated after probe
    status: str = "pending"  # "pending", "live", "dead", "timeout", "error"
    video_codec: str = ""
    audio_codec: str = ""
    resolution: str = ""
    video_bitrate: str = ""
    audio_bitrate: str = ""
    fps: str = ""
    container: str = ""
    http_status: int = 0
    error_message: str = ""
    probe_duration_ms: int = 0


@dataclass
class AccountInfo:
    username: str = ""
    password: str = ""
    status: str = ""
    expiry_date: str = ""
    max_connections: int = 0
    active_connections: int = 0
    server_url: str = ""
    server_port: str = ""
    server_protocol: str = "http"
    created_at: str = ""
    is_trial: bool = False
    live_count: int = 0
    vod_count: int = 0
    series_count: int = 0


class ChannelTableModel(QAbstractTableModel):
    """Qt table model backed by a list of Channel objects."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._channels: list[Channel] = []
        self._headers = COLUMN_HEADERS

    def set_channels(self, channels: list[Channel]):
        self.beginResetModel()
        self._channels = channels
        self.endResetModel()

    def get_channel(self, row: int) -> Channel:
        return self._channels[row]

    def get_all_channels(self) -> list[Channel]:
        return self._channels

    def update_channel(self, row: int, channel: Channel):
        if 0 <= row < len(self._channels):
            self._channels[row] = channel
            self.dataChanged.emit(
                self.index(row, 0),
                self.index(row, self.columnCount() - 1)
            )

    def rowCount(self, parent=QModelIndex()):
        return len(self._channels)

    def columnCount(self, parent=QModelIndex()):
        return len(self._headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self._headers[section]
        return QVariant()

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._channels):
            return QVariant()

        ch = self._channels[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            return self._get_display_data(index.row(), col, ch)
        elif role == Qt.ForegroundRole and col == 3:  # Status column
            from PyQt5.QtGui import QColor
            colors = {
                "live": QColor("#a6e3a1"),
                "dead": QColor("#f38ba8"),
                "pending": QColor("#f9e2af"),
                "timeout": QColor("#9399b2"),
                "error": QColor("#fab387"),
            }
            return colors.get(ch.status, QColor("#cdd6f4"))
        elif role == Qt.TextAlignmentRole:
            if col == 0:
                return Qt.AlignCenter
            return Qt.AlignLeft | Qt.AlignVCenter

        return QVariant()

    def _get_display_data(self, row: int, col: int, ch: Channel):
        mapping = {
            0: str(row + 1),
            1: ch.name,
            2: ch.group,
            3: ch.status.upper(),
            4: ch.resolution,
            5: ch.video_codec,
            6: ch.audio_codec,
            7: ch.video_bitrate,
            8: ch.audio_bitrate,
            9: ch.fps,
            10: ch.container,
        }
        return mapping.get(col, "")

    def sort(self, column, order=Qt.AscendingOrder):
        self.beginResetModel()
        key_map = {
            1: lambda c: c.name.lower(),
            2: lambda c: c.group.lower(),
            3: lambda c: c.status,
            4: lambda c: c.resolution,
            5: lambda c: c.video_codec,
            7: lambda c: c.video_bitrate,
            9: lambda c: c.fps,
        }
        key_func = key_map.get(column)
        if key_func:
            reverse = order == Qt.DescendingOrder
            self._channels.sort(key=key_func, reverse=reverse)
        self.endResetModel()
