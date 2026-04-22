"""Custom reusable widgets."""

from PyQt5.QtWidgets import QStyledItemDelegate
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QPainter, QColor, QFont


class StatusDelegate(QStyledItemDelegate):
    """Custom delegate for the Status column — draws colored status badges."""

    STATUS_COLORS = {
        "LIVE": QColor("#a6e3a1"),
        "DEAD": QColor("#f38ba8"),
        "PENDING": QColor("#f9e2af"),
        "TIMEOUT": QColor("#9399b2"),
        "ERROR": QColor("#fab387"),
    }

    def paint(self, painter: QPainter, option, index):
        text = index.data(Qt.DisplayRole)
        if not text:
            super().paint(painter, option, index)
            return

        painter.save()

        # Draw selection background if selected
        if option.state & 0x00000008:  # QStyle.State_Selected
            painter.fillRect(option.rect, QColor("#45475a"))

        color = self.STATUS_COLORS.get(text, QColor("#cdd6f4"))

        # Draw colored dot
        dot_size = 8
        dot_x = option.rect.x() + 8
        dot_y = option.rect.center().y() - dot_size // 2
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(dot_x, dot_y, dot_size, dot_size)

        # Draw text
        painter.setPen(color)
        font = QFont(painter.font())
        font.setBold(True)
        painter.setFont(font)
        text_rect = QRect(
            dot_x + dot_size + 6,
            option.rect.y(),
            option.rect.width() - dot_size - 20,
            option.rect.height(),
        )
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, text)

        painter.restore()

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        hint.setHeight(max(hint.height(), 28))
        return hint
