"""Auto-layout view — shows device positions computed from pairwise distances.

Three mini-maps:
  1. Mac-only view (distances as the Mac sees them)
  2. iPhone-only view (distances as the iPhone sees them)
  3. Combined (fused auto-layout result)

Plus a direction-hint panel: for each visible device, the user picks a rough
direction ("upper-left", "right", etc.) so the system can orient the map.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from engine.auto_layout import DIRECTION_ANGLES

_COLORS = [
    QColor(239, 68, 68), QColor(59, 130, 246), QColor(16, 185, 129),
    QColor(245, 158, 11), QColor(139, 92, 246), QColor(236, 72, 153),
    QColor(6, 182, 212), QColor(234, 179, 8),
]

_DIR_LABELS = [
    ("—", ""),
    ("→ Right", "right"),
    ("↗ Upper-right", "upper-right"),
    ("↑ Above", "above"),
    ("↖ Upper-left", "upper-left"),
    ("← Left", "left"),
    ("↙ Lower-left", "lower-left"),
    ("↓ Below", "below"),
    ("↘ Lower-right", "lower-right"),
]


class _MiniMap(QWidget):
    """Small room map showing positioned devices relative to a reference."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.title = title
        self.room_w = 5.0
        self.room_h = 3.0
        self.ref_pos: Optional[Tuple[float, float]] = None
        self.ref_label = ""
        self.devices: List[dict] = []  # [{name, x, y, dist, color}]

    def _to_screen(self, x, y, w, h, pad=30):
        sx = pad + (x / max(self.room_w, 0.1)) * (w - 2 * pad)
        sy = pad + (y / max(self.room_h, 0.1)) * (h - 2 * pad)
        return sx, sy

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(13, 17, 23))

        # Title
        p.setPen(QColor(147, 197, 253))
        p.setFont(QFont("Helvetica", 10, QFont.Weight.Bold))
        p.drawText(QRectF(4, 2, w - 8, 18), Qt.AlignmentFlag.AlignLeft, self.title)

        # Room rectangle
        x0, y0 = self._to_screen(0, 0, w, h)
        x1, y1 = self._to_screen(self.room_w, self.room_h, w, h)
        p.setPen(QPen(QColor(48, 54, 61), 1))
        p.drawRect(QRectF(x0, y0, x1 - x0, y1 - y0))

        m_per_px = self.room_w / max(x1 - x0, 1)

        # Reference point (Mac or iPhone)
        if self.ref_pos is not None:
            sx, sy = self._to_screen(self.ref_pos[0], self.ref_pos[1], w, h)
            p.setBrush(QColor(59, 130, 246))
            p.setPen(QPen(QColor(147, 197, 253), 2))
            p.drawEllipse(QPointF(sx, sy), 7, 7)
            p.setPen(QColor(147, 197, 253))
            p.setFont(QFont("Helvetica", 8))
            p.drawText(QPointF(sx + 10, sy + 4), self.ref_label)

        # Devices
        for dev in self.devices:
            sx, sy = self._to_screen(dev["x"], dev["y"], w, h)
            color = dev.get("color", QColor(239, 68, 68))

            # Distance line from ref
            if self.ref_pos is not None:
                rx, ry = self._to_screen(self.ref_pos[0], self.ref_pos[1], w, h)
                line_color = QColor(color)
                line_color.setAlpha(60)
                p.setPen(QPen(line_color, 1, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(rx, ry), QPointF(sx, sy))
                # Distance label
                mx, my = (rx + sx) / 2, (ry + sy) / 2
                p.setPen(QColor(100, 116, 139))
                p.setFont(QFont("Helvetica", 8))
                dist = dev.get("dist", 0)
                p.drawText(QPointF(mx + 2, my - 2), f"{dist:.1f}m")

            p.setBrush(color)
            p.setPen(QPen(QColor("white"), 1))
            p.drawEllipse(QPointF(sx, sy), 5, 5)
            p.setPen(QColor("white"))
            p.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
            p.drawText(QPointF(sx + 8, sy + 4), dev["name"])

        if self.ref_pos is None and not self.devices:
            p.setPen(QColor(100, 116, 139))
            p.setFont(QFont("Helvetica", 10))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data yet")

        p.end()


class _DeviceHintRow(QWidget):
    changed = pyqtSignal()

    def __init__(self, device_id: str, name: str, color: QColor, parent=None):
        super().__init__(parent)
        self.device_id = device_id

        row = QHBoxLayout(self)
        row.setContentsMargins(4, 2, 4, 2)
        row.setSpacing(6)

        dot = QLabel("●")
        dot.setStyleSheet(f"color:{color.name()};font-size:13px;")
        dot.setFixedWidth(16)
        row.addWidget(dot)

        lbl = QLabel(name)
        lbl.setStyleSheet("font-size:11px;")
        lbl.setMinimumWidth(120)
        row.addWidget(lbl, stretch=1)

        self._dist_label = QLabel("")
        self._dist_label.setStyleSheet("font-size:10px;color:#94a3b8;")
        self._dist_label.setFixedWidth(56)
        row.addWidget(self._dist_label)

        self.combo = QComboBox()
        for label, _ in _DIR_LABELS:
            self.combo.addItem(label)
        self.combo.setFixedWidth(130)
        self.combo.setStyleSheet(
            "QComboBox{background:#1f2937;color:#e2e8f0;border:1px solid #334155;"
            "border-radius:4px;padding:2px 6px;font-size:11px;}"
        )
        self.combo.currentIndexChanged.connect(lambda _: self.changed.emit())
        row.addWidget(self.combo)

    def direction(self) -> str:
        idx = self.combo.currentIndex()
        if idx <= 0:
            return ""
        return _DIR_LABELS[idx][1]

    def set_distance(self, d: float):
        self._dist_label.setText(f"{d:.1f}m" if d >= 1 else f"{d*100:.0f}cm")


class AutoLayoutView(QWidget):
    hints_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color_map: Dict[str, QColor] = {}
        self._cidx = 0
        self._device_rows: Dict[str, _DeviceHintRow] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        header = QLabel(
            "<b>Auto Layout</b> — positions computed from pairwise BLE distances. "
            "Pick a rough direction for each device to orient the map."
        )
        header.setWordWrap(True)
        header.setStyleSheet("font-size:11px;color:#9ca3af;padding:4px;")
        layout.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Three mini maps side by side
        maps_widget = QWidget()
        maps_layout = QHBoxLayout(maps_widget)
        maps_layout.setContentsMargins(0, 0, 0, 0)
        maps_layout.setSpacing(4)

        self._mac_map = _MiniMap("Mac Only")
        self._iphone_map = _MiniMap("iPhone Only")
        self._combined_map = _MiniMap("Combined")
        maps_layout.addWidget(self._mac_map)
        maps_layout.addWidget(self._iphone_map)
        maps_layout.addWidget(self._combined_map)
        splitter.addWidget(maps_widget)

        # Device hints panel
        hints_container = QWidget()
        hints_layout = QVBoxLayout(hints_container)
        hints_layout.setContentsMargins(4, 4, 4, 4)
        hints_layout.setSpacing(2)

        hints_header = QLabel("<b>Direction Hints</b>")
        hints_header.setStyleSheet("font-size:11px;color:#93c5fd;")
        hints_layout.addWidget(hints_header)

        self._hints_box = QVBoxLayout()
        self._hints_box.setSpacing(1)
        hints_layout.addLayout(self._hints_box)
        hints_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(hints_container)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        splitter.addWidget(scroll)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)

        self._status = QLabel("")
        self._status.setStyleSheet("font-size:11px;color:#64748b;")
        layout.addWidget(self._status)

    def _color(self, device_id: str) -> QColor:
        if device_id not in self._color_map:
            self._color_map[device_id] = _COLORS[self._cidx % len(_COLORS)]
            self._cidx += 1
        return self._color_map[device_id]

    def get_hints(self) -> Dict[str, str]:
        return {did: row.direction() for did, row in self._device_rows.items()
                if row.direction()}

    def update_view(
        self,
        room_w: float,
        room_h: float,
        mac_id: str,
        mac_distances: Dict[str, Tuple[float, str]],
        iphone_id: Optional[str],
        iphone_distances: Dict[str, Tuple[float, str]],
        combined_positions: Optional[Dict[str, Tuple[float, float]]],
        device_names: Dict[str, str],
    ):
        """Update all three maps.

        mac_distances: {device_id: (distance, name)}
        iphone_distances: {device_id: (distance, name)}
        combined_positions: {device_id: (x, y)} from auto-layout solver
        """
        for m in (self._mac_map, self._iphone_map, self._combined_map):
            m.room_w = room_w
            m.room_h = room_h

        cx, cy = room_w / 2, room_h / 2

        # Mac-only map: Mac at centre, devices placed by distance (spread radially)
        self._mac_map.ref_pos = (cx, cy)
        self._mac_map.ref_label = "Mac"
        self._mac_map.devices = []
        for i, (did, (dist, name)) in enumerate(mac_distances.items()):
            angle = i * (2 * math.pi / max(len(mac_distances), 1))
            x = cx + dist * math.cos(angle)
            y = cy + dist * math.sin(angle)
            x = max(0.1, min(room_w - 0.1, x))
            y = max(0.1, min(room_h - 0.1, y))
            self._mac_map.devices.append({
                "name": name, "x": x, "y": y,
                "dist": dist, "color": self._color(did),
            })

        # iPhone-only map
        if iphone_id and iphone_distances:
            self._iphone_map.ref_pos = (cx, cy)
            self._iphone_map.ref_label = device_names.get(iphone_id, "iPhone")
            self._iphone_map.devices = []
            for i, (did, (dist, name)) in enumerate(iphone_distances.items()):
                angle = i * (2 * math.pi / max(len(iphone_distances), 1))
                x = cx + dist * math.cos(angle)
                y = cy + dist * math.sin(angle)
                x = max(0.1, min(room_w - 0.1, x))
                y = max(0.1, min(room_h - 0.1, y))
                self._iphone_map.devices.append({
                    "name": name, "x": x, "y": y,
                    "dist": dist, "color": self._color(did),
                })
        else:
            self._iphone_map.ref_pos = None
            self._iphone_map.devices = []

        # Combined map
        if combined_positions:
            self._combined_map.ref_pos = combined_positions.get(mac_id, (cx, cy))
            self._combined_map.ref_label = "Mac"
            self._combined_map.devices = []
            for did, (x, y) in combined_positions.items():
                if did == mac_id:
                    continue
                name = device_names.get(did, did[:8])
                ref = self._combined_map.ref_pos
                dist = math.sqrt((x - ref[0]) ** 2 + (y - ref[1]) ** 2)
                self._combined_map.devices.append({
                    "name": name, "x": x, "y": y,
                    "dist": dist, "color": self._color(did),
                })
        else:
            self._combined_map.ref_pos = (cx, cy)
            self._combined_map.ref_label = "Mac"
            self._combined_map.devices = []

        # Update all maps
        self._mac_map.update()
        self._iphone_map.update()
        self._combined_map.update()

        # Update hint rows for all known devices
        all_devices = set(mac_distances.keys())
        if iphone_distances:
            all_devices |= set(iphone_distances.keys())
        if iphone_id:
            all_devices.discard(mac_id)

        for did in list(self._device_rows.keys()):
            if did not in all_devices:
                row = self._device_rows.pop(did)
                self._hints_box.removeWidget(row)
                row.deleteLater()

        for did in all_devices:
            name = device_names.get(did, did[:8])
            if did not in self._device_rows:
                row = _DeviceHintRow(did, name, self._color(did))
                row.changed.connect(self.hints_changed.emit)
                self._device_rows[did] = row
                self._hints_box.addWidget(row)
            row = self._device_rows[did]
            d = mac_distances.get(did, (0, ""))[0]
            if d == 0 and iphone_distances:
                d = iphone_distances.get(did, (0, ""))[0]
            row.set_distance(d)

        n_hints = sum(1 for r in self._device_rows.values() if r.direction())
        self._status.setText(
            f"{len(all_devices)} devices · {n_hints} direction hints · "
            f"{'Solved' if combined_positions else 'Need hints to solve'}")
