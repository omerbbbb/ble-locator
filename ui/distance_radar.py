from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QPushButton, QToolTip, QWidget

from core.models import DeviceEstimate


def _rssi_color(rssi: float) -> str:
    if rssi >= -60:
        return "#27ae60"
    elif rssi >= -75:
        return "#f39c12"
    return "#e74c3c"


GRAB_PX = 22.0
MARKER_HIT_PX = 16.0
_NICE_STEPS = [0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0]


class DistanceRadar(QWidget):
    anchor_placed = pyqtSignal(str, float, float)
    device_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self.setMouseTracking(True)
        self._devices: List[DeviceEstimate] = []
        self._by_id: Dict[str, DeviceEstimate] = {}
        self._scale_m: float = 4.0
        self._zoom: float = 1.0
        self._selected: Optional[str] = None
        self._focus: bool = False
        self._drag_id: Optional[str] = None
        self._drag_angle: float = 0.0
        self._grab_kind: Optional[str] = None
        self._moved = False

        self._btn_in = self._mk_btn("+", self.zoom_in)
        self._btn_out = self._mk_btn("−", self.zoom_out)
        self._btn_reset = self._mk_btn("⟳", self.zoom_reset)
        self._btn_focus = self._mk_btn("◎", self.toggle_focus)
        self._btn_focus.setToolTip("Focus: show only the selected device")

    def set_selected(self, device_id: Optional[str]):
        self._selected = device_id
        self.update()

    def toggle_focus(self):
        self._focus = not self._focus
        if self._focus:
            self._btn_focus.setStyleSheet(
                "QPushButton{background:#0ea5e9;color:#ffffff;border:1px solid #38bdf8;"
                "border-radius:6px;font-size:15px;}"
            )
        else:
            self._btn_focus.setStyleSheet(
                "QPushButton{background:#1f2937;color:#e2e8f0;border:1px solid #334155;"
                "border-radius:6px;font-size:15px;}"
                "QPushButton:hover{background:#334155;}"
            )
        self.update()

    def _shown_devices(self) -> List[DeviceEstimate]:
        # Focus shows only the selected device — but if it isn't currently
        # visible (rotated address / hidden / not yet measured), fall back to
        # showing everything rather than a blank radar.
        if self._focus and self._selected and self._selected in self._by_id:
            return [self._by_id[self._selected]]
        return self._devices

    def _mk_btn(self, text, slot) -> QPushButton:
        b = QPushButton(text, self)
        b.setFixedSize(28, 28)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            "QPushButton{background:#1f2937;color:#e2e8f0;border:1px solid #334155;"
            "border-radius:6px;font-size:15px;}"
            "QPushButton:hover{background:#334155;}"
        )
        b.clicked.connect(slot)
        return b

    def set_devices(self, devices: List[DeviceEstimate]):
        self._devices = devices
        self._by_id = {d.device_id: d for d in devices}
        max_d = max((d.distance for d in devices), default=1.0)
        target = max(4.0, math.ceil(max_d / 2.0) * 2.0)
        if target > self._scale_m:
            self._scale_m = target
        else:
            self._scale_m += (target - self._scale_m) * 0.1
        self.update()

    def zoom_in(self):
        self._zoom = min(self._zoom * 1.3, 200.0)
        self.update()

    def zoom_out(self):
        self._zoom = max(self._zoom / 1.3, 0.25)
        self.update()

    def zoom_reset(self):
        self._zoom = 1.0
        self.update()

    def wheelEvent(self, event):
        (self.zoom_in if event.angleDelta().y() > 0 else self.zoom_out)()

    def _center(self) -> Tuple[float, float]:
        return self.width() / 2.0, self.height() / 2.0

    def _max_r(self) -> float:
        return max(20.0, min(self.width(), self.height()) / 2.0 - 60)

    def _effective_scale(self) -> float:
        s = self._scale_m if self._scale_m > 0 else 4.0
        return s / self._zoom

    def _m_to_px(self, metres: float) -> float:
        return metres / self._effective_scale() * self._max_r()

    def _angle_of(self, d: DeviceEstimate) -> float:
        if self._drag_id == d.device_id:
            return self._drag_angle
        if d.angle is not None:
            return d.angle
        return self._hash_angle(d.device_id)

    @staticmethod
    def _hash_angle(device_id: str) -> float:
        h = 0
        for ch in device_id:
            h = (h * 31 + ord(ch)) & 0xFFFFFFFF
        return (h % 3600) / 3600.0 * 2.0 * math.pi

    def _marker_px(self, d: DeviceEstimate) -> Tuple[float, float]:
        cx, cy = self._center()
        r = self._m_to_px(d.distance)
        ang = self._angle_of(d)
        return cx + r * math.cos(ang), cy - r * math.sin(ang)

    def _click_angle(self, px: float, py: float) -> float:
        cx, cy = self._center()
        return math.atan2(cy - py, px - cx)

    @staticmethod
    def _grid_step(scale: float) -> float:
        for s in _NICE_STEPS:
            if scale / s <= 8:
                return s
        return _NICE_STEPS[-1]

    def resizeEvent(self, event):
        x = 8
        for b in (self._btn_in, self._btn_out, self._btn_reset, self._btn_focus):
            b.move(x, 8)
            x += 32

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor("#0d1117"))

        cx, cy = self._center()
        max_r = self._max_r()
        scale = self._effective_scale()

        step = self._grid_step(scale)
        painter.setFont(QFont("Helvetica", 9))
        n = 1
        while n * step <= scale + 1e-9:
            ring = n * step
            rpx = self._m_to_px(ring)
            n += 1
            if rpx > max_r + 1:
                continue
            painter.setPen(QPen(QColor("#1e293b"), 1))
            painter.drawEllipse(QPointF(cx, cy), rpx, rpx)
            painter.setPen(QColor("#475569"))
            lbl = f"{round(ring * 100)} cm" if ring < 1 else f"{ring:g} m"
            painter.drawText(QPointF(cx + 3, cy - rpx - 2), lbl)

        shown = self._shown_devices()
        has_selection = self._selected is not None and self._selected in self._by_id
        for d in shown:
            selected = d.device_id == self._selected
            # Dim everything else when one device is selected (not in focus mode).
            dim = has_selection and not selected and not self._focus
            base = QColor(_rssi_color(d.filtered_rssi))
            color = QColor("#3a4250") if dim else base
            rpx = self._m_to_px(d.distance)
            mx, my = self._marker_px(d)

            pen = QPen(color, 2 if d.is_anchor else 1)
            if not d.is_anchor:
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if rpx <= max(w, h):
                painter.drawEllipse(QPointF(cx, cy), rpx, rpx)

            if selected:
                # Bold highlight: bright thick ring + radial line to centre.
                painter.setPen(QPen(QColor("#38bdf8"), 3))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                if rpx <= max(w, h):
                    painter.drawEllipse(QPointF(cx, cy), rpx, rpx)
                painter.setPen(QPen(QColor("#38bdf8"), 2, Qt.PenStyle.DashLine))
                painter.drawLine(QPointF(cx, cy), QPointF(mx, my))
                painter.setPen(QPen(QColor("#ffffff"), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(mx, my), 12, 12)

            marker = QColor("#38bdf8") if selected else color
            painter.setBrush(marker)
            painter.setPen(QPen(QColor("white"), 1))
            painter.drawEllipse(QPointF(mx, my), 8 if selected else 6, 8 if selected else 6)

            prefix = "⚓ " if d.is_anchor else ""
            painter.setPen(QColor("#e2e8f0") if selected else color)
            bold = d.is_anchor or selected
            painter.setFont(QFont("Helvetica", 10 if selected else 9,
                                  QFont.Weight.Bold if bold else QFont.Weight.Normal))
            dtxt = f"{round(d.distance * 100)} cm" if d.distance < 1 else f"{d.distance:.2f} m"
            painter.drawText(QPointF(mx + 9, my + 4), f"{prefix}{d.name}  {dtxt}")

        painter.setBrush(QColor("#3b82f6"))
        painter.setPen(QPen(QColor("white"), 2))
        painter.drawEllipse(QPointF(cx, cy), 9, 9)
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Helvetica", 10, QFont.Weight.Bold))
        painter.drawText(QPointF(cx + 13, cy + 4), "You")

        painter.setPen(QColor("#64748b"))
        painter.setFont(QFont("Helvetica", 10))
        if self._selected and self._selected in self._by_id:
            tip = f"Selected: {self._by_id[self._selected].name} — click where it really is, or drag."
        else:
            tip = "Click a device to select, then click its real direction."
        painter.drawText(QPointF(8, h - 10), f"{tip}   (scroll to zoom ×{self._zoom:.1f})")
        painter.end()

    def _hit(self, px: float, py: float) -> Tuple[Optional[str], Optional[str]]:
        shown = self._shown_devices()
        best, bd = None, MARKER_HIT_PX
        for d in shown:
            mx, my = self._marker_px(d)
            dd = math.hypot(px - mx, py - my)
            if dd < bd:
                bd, best = dd, d.device_id
        if best is not None:
            return best, "marker"

        cx, cy = self._center()
        rc = math.hypot(px - cx, py - cy)
        best, bd = None, GRAB_PX
        for d in shown:
            diff = abs(rc - self._m_to_px(d.distance))
            if diff < bd:
                bd, best = diff, d.device_id
        if best is not None:
            return best, "ring"
        return None, None

    def mousePressEvent(self, event):
        pos = event.position()
        device_id, kind = self._hit(pos.x(), pos.y())
        if device_id is not None:
            if device_id != self._selected:
                self._selected = device_id
                self.device_selected.emit(device_id)
            self._drag_id = device_id
            self._grab_kind = kind
            self._moved = False
            self._drag_angle = (self._click_angle(pos.x(), pos.y()) if kind == "ring"
                                else self._angle_of(self._by_id[device_id]))
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
        else:
            # Plain click on empty space clears the selection — never places an
            # anchor. Anchors are set only by dragging a marker/ring.
            if self._selected is not None:
                self._selected = None
                self.device_selected.emit("")
                self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._drag_id is not None:
            self._moved = True
            self._drag_angle = self._click_angle(pos.x(), pos.y())
            self.update()
            return
        # Hover: show the device's UUID + distance as a tooltip.
        device_id, _ = self._hit(pos.x(), pos.y())
        if device_id is not None and device_id in self._by_id:
            d = self._by_id[device_id]
            dtxt = (f"{round(d.distance * 100)} cm" if d.distance < 1
                    else f"{d.distance:.2f} m")
            QToolTip.showText(event.globalPosition().toPoint(),
                              f"{d.name}\nUUID: {device_id}\nDistance: {dtxt}", self)
        else:
            QToolTip.hideText()

    def mouseReleaseEvent(self, event):
        if self._drag_id is not None:
            d = self._by_id.get(self._drag_id)
            # Only an actual drag places an anchor — a plain click just selects.
            if d is not None and self._moved:
                self.anchor_placed.emit(self._drag_id, self._drag_angle, d.distance)
            self._drag_id = None
            self._grab_kind = None
            self.unsetCursor()
            self.update()
