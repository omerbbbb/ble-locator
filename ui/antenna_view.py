"""Per-antenna visualization: signal quality and accuracy breakdown by radio type.

Shows a summary card per antenna type (BLE, WiFi, UWB) with:
- Device count
- Average RSSI
- Best / worst signal
- Distribution bar
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from core.models import DeviceEstimate, SignalType

RADIO_META = {
    SignalType.BLE:  ("BLE",  "#3b82f6", "📶"),
    SignalType.WIFI: ("WiFi", "#22c55e", "📡"),
    SignalType.UWB:  ("UWB",  "#f59e0b", "🎯"),
}


class AntennaView(QWidget):
    """Paints per-radio-type signal quality cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self._devices: List[DeviceEstimate] = []

    def set_devices(self, devices: List[DeviceEstimate]):
        self._devices = devices
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor("#0d1117"))

        by_type: Dict[SignalType, List[DeviceEstimate]] = {}
        for d in self._devices:
            by_type.setdefault(d.signal_type, []).append(d)

        types_present = [t for t in (SignalType.BLE, SignalType.WIFI, SignalType.UWB)
                         if t in by_type]

        if not types_present:
            painter.setPen(QColor("#6b7280"))
            painter.setFont(QFont("Helvetica", 13))
            painter.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                             "No devices detected yet")
            painter.end()
            return

        n = len(types_present)
        card_w = min(320, (w - 20) // n - 10)
        card_h = min(h - 20, 300)
        start_x = (w - n * (card_w + 10) + 10) // 2
        y0 = max(10, (h - card_h) // 2)

        for i, sig_type in enumerate(types_present):
            devs = by_type[sig_type]
            label, color, icon = RADIO_META.get(sig_type, ("?", "#888", "?"))
            cx = start_x + i * (card_w + 10)
            self._draw_card(painter, cx, y0, card_w, card_h, label, color, icon, devs)

        painter.end()

    def _draw_card(self, painter: QPainter, x: int, y: int, w: int, h: int,
                   label: str, color: str, icon: str, devs: List[DeviceEstimate]):
        painter.setBrush(QColor("#161b22"))
        painter.setPen(QPen(QColor(color), 2))
        painter.drawRoundedRect(x, y, w, h, 10, 10)

        # Header
        painter.setPen(QColor(color))
        painter.setFont(QFont("Helvetica", 16, QFont.Weight.Bold))
        painter.drawText(x + 12, y + 30, f"{icon} {label}")

        # Stats
        rssi_vals = [d.filtered_rssi for d in devs]
        dist_vals = [d.distance for d in devs]
        n_anchors = sum(1 for d in devs if d.is_anchor)

        avg_rssi = sum(rssi_vals) / len(rssi_vals) if rssi_vals else 0
        best = max(rssi_vals) if rssi_vals else 0
        worst = min(rssi_vals) if rssi_vals else 0
        avg_dist = sum(dist_vals) / len(dist_vals) if dist_vals else 0
        closest = min(dist_vals) if dist_vals else 0

        painter.setFont(QFont("Helvetica", 11))
        rows = [
            (f"Devices: {len(devs)}", "#e2e8f0"),
            (f"Anchors: {n_anchors}", "#93c5fd"),
            (f"Avg RSSI: {avg_rssi:.0f} dBm", "#e2e8f0"),
            (f"Best: {best:.0f} dBm  /  Worst: {worst:.0f} dBm", "#9ca3af"),
            (f"Avg distance: {avg_dist:.2f} m", "#e2e8f0"),
            (f"Closest: {closest:.2f} m", "#9ca3af"),
        ]
        for j, (text, text_color) in enumerate(rows):
            painter.setPen(QColor(text_color))
            painter.drawText(x + 12, y + 58 + j * 22, text)

        # Signal distribution bar
        bar_y = y + 58 + len(rows) * 22 + 12
        bar_w = w - 24
        bar_h = 16
        if bar_w > 0 and rssi_vals:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#21262d"))
            painter.drawRoundedRect(x + 12, bar_y, bar_w, bar_h, 4, 4)

            strong = sum(1 for r in rssi_vals if r >= -60)
            medium = sum(1 for r in rssi_vals if -75 <= r < -60)
            weak = sum(1 for r in rssi_vals if r < -75)
            total = len(rssi_vals)

            seg_x = x + 12
            for count, seg_color in [(strong, "#27ae60"), (medium, "#f39c12"), (weak, "#e74c3c")]:
                if count > 0:
                    seg_w = max(2, int(count / total * bar_w))
                    painter.setBrush(QColor(seg_color))
                    painter.drawRoundedRect(seg_x, bar_y, seg_w, bar_h, 4, 4)
                    seg_x += seg_w

            painter.setPen(QColor("#9ca3af"))
            painter.setFont(QFont("Helvetica", 9))
            painter.drawText(x + 12, bar_y + bar_h + 14,
                             f"🟢 {strong} strong   🟠 {medium} medium   🔴 {weak} weak")
