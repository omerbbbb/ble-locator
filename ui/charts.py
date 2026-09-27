"""RSSI-over-time chart drawn with QPainter — no matplotlib dependency.

Shows raw RSSI (grey dashed) vs Kalman-filtered RSSI (coloured) for each
anchor. Each coloured line = one anchor device. The chart only tracks anchors,
not all visible devices, because anchors are the fixed reference points
whose signal stability directly affects positioning accuracy.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, Deque, Tuple

from PyQt6.QtCore import QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

HISTORY_LEN = 60
ANCHOR_COLORS = ["#e74c3c", "#3498db", "#2ecc71", "#9b59b6", "#f39c12"]


class RSSIChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self._history: Dict[str, Deque[Tuple[float, float]]] = {}
        self._names: Dict[str, str] = {}
        self._color_map: Dict[str, str] = {}
        self._color_idx = 0

    def add_reading(self, device_id: str, raw: float, filtered: float,
                    name: str = ""):
        if device_id not in self._history:
            self._history[device_id] = deque(maxlen=HISTORY_LEN)
            self._color_map[device_id] = ANCHOR_COLORS[self._color_idx % len(ANCHOR_COLORS)]
            self._color_idx += 1
        self._history[device_id].append((raw, filtered))
        if name:
            self._names[device_id] = name
        self.update()

    def clear_history(self):
        self._history.clear()
        self._names.clear()
        self._color_map.clear()
        self._color_idx = 0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        margin_l, margin_r, margin_t, margin_b = 38, 10, 8, 22
        cw = w - margin_l - margin_r
        ch = h - margin_t - margin_b

        painter.fillRect(0, 0, w, h, QColor("#0d1117"))

        if not self._history:
            painter.setPen(QColor("#6b7280"))
            painter.setFont(QFont("Helvetica", 11))
            painter.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                             "Anchor RSSI will appear here once anchors are set")
            painter.end()
            return

        # Axes
        painter.setPen(QPen(QColor("#334155"), 1))
        painter.drawLine(margin_l, margin_t, margin_l, h - margin_b)
        painter.drawLine(margin_l, h - margin_b, w - margin_r, h - margin_b)

        y_min, y_max = -100.0, -40.0

        def to_screen(val: float, idx: int, total: int) -> QPoint:
            x = margin_l + int(idx / max(total - 1, 1) * cw)
            y = h - margin_b - int((val - y_min) / (y_max - y_min) * ch)
            return QPoint(x, y)

        # Y-axis grid + labels
        painter.setFont(QFont("Helvetica", 8))
        for rssi in range(-100, -35, 10):
            y = h - margin_b - int((rssi - y_min) / (y_max - y_min) * ch)
            painter.setPen(QPen(QColor("#1e293b"), 1))
            painter.drawLine(margin_l, y, w - margin_r, y)
            painter.setPen(QColor("#6b7280"))
            painter.drawText(QRect(0, y - 8, margin_l - 4, 16),
                             Qt.AlignmentFlag.AlignRight, str(rssi))

        # Signal quality bands
        for rssi_start, rssi_end, band_color, label in [
            (-60, -40, "#27ae6018", "Strong"),
            (-75, -60, "#f39c1210", ""),
            (-100, -75, "#e74c3c10", ""),
        ]:
            y1 = h - margin_b - int((rssi_end - y_min) / (y_max - y_min) * ch)
            y2 = h - margin_b - int((rssi_start - y_min) / (y_max - y_min) * ch)
            painter.fillRect(margin_l + 1, y1, cw - 1, y2 - y1, QColor(band_color))

        # Data lines
        legend_y = margin_t + 4
        for device_id, history in self._history.items():
            if len(history) < 2:
                continue
            color = QColor(self._color_map[device_id])
            points = list(history)
            total = len(points)

            # Raw — thin grey dashed
            pen = QPen(QColor("#444"), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            for i in range(1, total):
                p1 = to_screen(points[i - 1][0], i - 1, total)
                p2 = to_screen(points[i][0], i, total)
                painter.drawLine(p1, p2)

            # Filtered — solid coloured
            pen = QPen(color, 2)
            painter.setPen(pen)
            for i in range(1, total):
                p1 = to_screen(points[i - 1][1], i - 1, total)
                p2 = to_screen(points[i][1], i, total)
                painter.drawLine(p1, p2)

            # Legend entry
            name = self._names.get(device_id, device_id[:8])
            last_raw = points[-1][0]
            last_filt = points[-1][1]
            painter.setPen(color)
            painter.setFont(QFont("Helvetica", 9))
            painter.setBrush(color)
            painter.drawEllipse(QPoint(w - margin_r - 6, legend_y + 4), 4, 4)
            painter.drawText(QPointF(w - margin_r - 160, legend_y + 8),
                             f"⚓ {name}  {last_filt:.0f} dBm")
            legend_y += 16

        # Bottom labels
        painter.setPen(QColor("#6b7280"))
        painter.setFont(QFont("Helvetica", 9))
        painter.drawText(
            QRect(margin_l, h - margin_b + 4, cw, margin_b - 4),
            Qt.AlignmentFlag.AlignLeft,
            "Each line = one anchor  |  Solid = filtered (Kalman)  |  Dashed = raw RSSI"
        )

        painter.end()
