"""Camera AR view — camera feed with device overlays.

Uses QGraphicsView + QGraphicsVideoItem so that video and overlays
composite in the SAME rendering pipeline. This solves the macOS issue
where QVideoWidget uses a native Metal layer that hides Qt widget overlays.

All selected devices show as distance labels on the video feed.
Anchors (known position) also project as circles when heading is set.
"""

from __future__ import annotations

import math
import time
from typing import Dict, List, Optional, Set, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QMouseEvent
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from engine.ar_projector import circle_radius, project
from ui.camera_capture import CameraCapture
from services.anchor_store import AnchorStore

_FOV_DEG = 60.0
_FOV_RAD = math.radians(_FOV_DEG)
_DEVICE_KEEP_SEC = 20.0
_LIST_REBUILD_INTERVAL = 3.0

_COLORS = [
    QColor(239, 68, 68),    # red
    QColor(59, 130, 246),   # blue
    QColor(16, 185, 129),   # green
    QColor(245, 158, 11),   # amber
    QColor(139, 92, 246),   # violet
    QColor(236, 72, 153),   # pink
    QColor(6, 182, 212),    # cyan
    QColor(234, 179, 8),    # yellow
]


class _DeviceOverlayInfo:
    __slots__ = ("device_id", "name", "distance", "is_anchor",
                 "room_x", "room_y", "color", "last_seen")

    def __init__(self, device_id, name, distance, is_anchor,
                 room_x, room_y, color, last_seen):
        self.device_id = device_id
        self.name = name
        self.distance = distance
        self.is_anchor = is_anchor
        self.room_x = room_x
        self.room_y = room_y
        self.color = color
        self.last_seen = last_seen


# ── Mini room-map widget (click to set heading) ────────────────────────

class _MiniMap(QWidget):
    heading_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(140, 110)
        self.my_pos: Optional[Tuple[float, float]] = None
        self.anchors: Dict[str, Tuple[float, float, str, QColor]] = {}
        self.heading: float = 0.0
        self.heading_set: bool = False
        self.room_w: float = 8.0
        self.room_h: float = 6.0
        self.setCursor(Qt.CursorShape.CrossCursor)

    def mousePressEvent(self, event: QMouseEvent):
        if self.my_pos is None:
            return
        mx, my = self._room_to_widget(*self.my_pos)
        cx = event.position().x()
        cy = event.position().y()
        dx, dy = cx - mx, cy - my
        if abs(dx) < 2 and abs(dy) < 2:
            return
        self.heading = math.atan2(dy, dx)
        self.heading_set = True
        self.heading_changed.emit(self.heading)
        self.update()

    def _room_to_widget(self, rx, ry):
        pad = 10
        sx = pad + (rx / max(self.room_w, 0.1)) * (self.width() - 2 * pad)
        sy = pad + (ry / max(self.room_h, 0.1)) * (self.height() - 2 * pad)
        return sx, sy

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, QColor(13, 17, 23, 200))
        p.setPen(QPen(QColor(48, 54, 61), 1))
        p.drawRect(0, 0, w - 1, h - 1)

        p.setPen(QColor(148, 163, 184))
        p.setFont(QFont("Helvetica", 8))
        if not self.heading_set:
            p.drawText(QRectF(0, 2, w, 14), Qt.AlignmentFlag.AlignCenter,
                       "Click to set camera dir")
        else:
            deg = int(math.degrees(self.heading)) % 360
            p.drawText(QRectF(0, 2, w, 14), Qt.AlignmentFlag.AlignCenter,
                       f"Camera: {deg}°")

        for uid, (ax, ay, name, color) in self.anchors.items():
            sx, sy = self._room_to_widget(ax, ay)
            p.setBrush(QColor(color.red(), color.green(), color.blue(), 120))
            p.setPen(QPen(color, 1))
            p.drawEllipse(QPointF(sx, sy), 4, 4)
            p.setPen(QColor(200, 200, 200))
            p.setFont(QFont("Helvetica", 7))
            p.drawText(int(sx) + 6, int(sy) + 3, name[:8])

        if self.my_pos is not None:
            mx, my = self._room_to_widget(*self.my_pos)
            p.setBrush(QColor(59, 130, 246))
            p.setPen(QPen(QColor(147, 197, 253), 2))
            p.drawEllipse(QPointF(mx, my), 5, 5)

            if self.heading_set:
                arrow_len = 22
                ex = mx + math.cos(self.heading) * arrow_len
                ey = my + math.sin(self.heading) * arrow_len
                p.setPen(QPen(QColor(250, 204, 21), 2))
                p.drawLine(QPointF(mx, my), QPointF(ex, ey))
                for sign in (-1, 1):
                    bx = ex - math.cos(self.heading + sign * 0.5) * 6
                    by = ey - math.sin(self.heading + sign * 0.5) * 6
                    p.drawLine(QPointF(ex, ey), QPointF(bx, by))

        p.end()


# ── Main camera view widget ─────────────────────────────────────────────

class CameraView(QWidget):
    """Camera tab — video + overlay via QGraphicsScene."""

    def __init__(self, anchors: AnchorStore, parent=None):
        super().__init__(parent)
        self._anchors = anchors
        self._heading = 0.0
        self._heading_set = False
        self._my_pos: Optional[Tuple[float, float]] = None
        self._all_devices: Dict[str, _DeviceOverlayInfo] = {}
        self._selected_ids: Set[str] = set()
        self._color_map: Dict[str, QColor] = {}
        self._color_idx = 0
        self._room_w = 8.0
        self._room_h = 6.0
        self._camera_on = False
        self._last_rebuild = 0.0

        # graphics scene overlay items (reused each frame)
        self._overlay_items: List[QGraphicsItem] = []

        self._setup_ui()

    def _get_color(self, device_id: str) -> QColor:
        if device_id not in self._color_map:
            self._color_map[device_id] = _COLORS[self._color_idx % len(_COLORS)]
            self._color_idx += 1
        return self._color_map[device_id]

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

        # left column: camera
        cam_col = QVBoxLayout()
        cam_col.setSpacing(4)

        btn_row = QHBoxLayout()
        self._toggle_btn = QPushButton("Start Camera")
        self._toggle_btn.setStyleSheet(
            "QPushButton{background:#1f6feb;color:white;border:none;"
            "border-radius:6px;padding:5px 14px;font-size:12px;}"
            "QPushButton:hover{background:#388bfd;}"
        )
        self._toggle_btn.clicked.connect(self._toggle_camera)
        btn_row.addWidget(self._toggle_btn)
        btn_row.addStretch()
        cam_col.addLayout(btn_row)

        # QGraphicsView + QGraphicsVideoItem
        self._scene = QGraphicsScene(self)
        self._video_item = QGraphicsVideoItem()
        self._scene.addItem(self._video_item)

        self._gview = QGraphicsView(self._scene)
        self._gview.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._gview.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._gview.setStyleSheet("QGraphicsView{border:none;background:#000;}")
        self._gview.setRenderHint(QPainter.RenderHint.Antialiasing)

        # resize video item when the native size changes
        self._video_item.nativeSizeChanged.connect(self._on_native_size)

        cam_col.addWidget(self._gview, stretch=1)
        root.addLayout(cam_col, stretch=1)

        # right column: mini-map + device list
        right_col = QVBoxLayout()
        right_col.setSpacing(6)

        self._minimap = _MiniMap()
        self._minimap.heading_changed.connect(self._on_minimap_heading)
        right_col.addWidget(self._minimap)

        picker_label = QLabel("Show on camera:")
        picker_label.setStyleSheet("font-size:11px;font-weight:bold;color:#94a3b8;")
        right_col.addWidget(picker_label)

        self._select_all_btn = QPushButton("Select All")
        self._select_all_btn.setStyleSheet(
            "QPushButton{background:#334155;color:#e2e8f0;border:none;"
            "border-radius:4px;padding:3px 8px;font-size:11px;}"
            "QPushButton:hover{background:#475569;}"
        )
        self._select_all_btn.clicked.connect(self._toggle_select_all)
        right_col.addWidget(self._select_all_btn)

        self._device_list = QListWidget()
        self._device_list.setStyleSheet(
            "QListWidget{background:#0d1117;border:1px solid #21262d;"
            "border-radius:6px;font-size:11px;}"
            "QListWidget::item{padding:3px 4px;}"
        )
        self._device_list.setFixedWidth(180)
        self._device_list.itemChanged.connect(self._on_item_changed)
        right_col.addWidget(self._device_list, stretch=1)

        root.addLayout(right_col)

        # camera capture — outputs to the graphics video item
        self._capture = CameraCapture(self._video_item, self)
        self._capture.error_occurred.connect(self._on_camera_error)
        self._capture.started.connect(self._on_camera_started)

    def _on_native_size(self, size):
        if size.isEmpty():
            return
        self._video_item.setSize(size)
        self._gview.fitInView(self._video_item, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._video_item.nativeSize().isEmpty():
            self._gview.fitInView(self._video_item,
                                  Qt.AspectRatioMode.KeepAspectRatio)

    # ── overlay drawing via scene items ──────────────────────────────────

    def _clear_overlay(self):
        for item in self._overlay_items:
            self._scene.removeItem(item)
        self._overlay_items.clear()

    def _add_text(self, text: str, x: float, y: float, color: QColor,
                  size: int = 11, bold: bool = False):
        t = QGraphicsSimpleTextItem(text)
        font = QFont("Helvetica", size)
        if bold:
            font.setBold(True)
        t.setFont(font)
        t.setBrush(QBrush(color))
        t.setPos(x, y)
        t.setZValue(10)
        self._scene.addItem(t)
        self._overlay_items.append(t)

    def _add_circle(self, cx: float, cy: float, r: float,
                    fill_color: QColor, border_color: QColor):
        ellipse = QGraphicsEllipseItem(cx - r, cy - r, 2 * r, 2 * r)
        ellipse.setBrush(QBrush(fill_color))
        ellipse.setPen(QPen(border_color, 2))
        ellipse.setZValue(8)
        self._scene.addItem(ellipse)
        self._overlay_items.append(ellipse)

    def _add_rect(self, x: float, y: float, w: float, h: float,
                  fill_color: QColor, border_color: QColor = None):
        rect = QGraphicsRectItem(x, y, w, h)
        rect.setBrush(QBrush(fill_color))
        if border_color:
            rect.setPen(QPen(border_color, 1))
        else:
            rect.setPen(QPen(Qt.PenStyle.NoPen))
        rect.setZValue(9)
        self._scene.addItem(rect)
        self._overlay_items.append(rect)

    def _update_overlay(self):
        self._clear_overlay()

        vid_rect = self._video_item.boundingRect()
        vw = vid_rect.width()
        vh = vid_rect.height()
        if vw < 10 or vh < 10:
            return

        selected = [d for d in self._all_devices.values()
                    if d.device_id in self._selected_ids]

        if not selected:
            if self._my_pos is not None:
                self._add_rect(0, 0, vw, 28, QColor(0, 0, 0, 160))
                self._add_text("Select devices from the list →",
                               vw / 2 - 110, 6, QColor("#f59e0b"), 11)
            else:
                self._add_rect(0, 0, vw, 28, QColor(0, 0, 0, 160))
                self._add_text("Waiting for position fix…",
                               vw / 2 - 90, 6, QColor("#f59e0b"), 11)
            return

        # AR circles for anchors with known position
        if self._heading_set and self._my_pos is not None:
            room_depth = max(self._room_w, self._room_h)
            for dev in selected:
                if dev.is_anchor and dev.room_x is not None:
                    pp = project(self._my_pos, (dev.room_x, dev.room_y),
                                 self._heading, _FOV_RAD,
                                 int(vw), int(vh), room_depth)
                    if pp is not None:
                        r = circle_radius(pp.distance)
                        # glow
                        glow = QColor(dev.color)
                        glow.setAlpha(30)
                        self._add_circle(pp.screen_x, pp.screen_y,
                                         r * 1.8, glow, QColor(0, 0, 0, 0))
                        # main circle
                        fill = QColor(dev.color)
                        fill.setAlpha(140)
                        border = QColor(dev.color)
                        border.setAlpha(200)
                        self._add_circle(pp.screen_x, pp.screen_y,
                                         r, fill, border)
                        # label
                        label = f"{dev.name}  {pp.distance:.1f}m"
                        lx = pp.screen_x + r + 8
                        ly = pp.screen_y - 8
                        self._add_rect(lx - 2, ly - 2, len(label) * 7 + 8, 18,
                                       QColor(0, 0, 0, 160))
                        self._add_text(label, lx, ly, QColor("white"), 10, True)

        # distance bars at bottom for ALL selected devices
        sorted_devs = sorted(selected, key=lambda d: d.distance)[:10]
        bar_h = 18
        margin = 3
        total_h = len(sorted_devs) * (bar_h + margin)
        start_y = vh - total_h - 8

        self._add_rect(0, start_y - 6, vw, total_h + 14,
                       QColor(0, 0, 0, 100))

        max_dist = max((d.distance for d in sorted_devs), default=1.0)
        max_dist = max(max_dist, 0.5)

        for i, dev in enumerate(sorted_devs):
            y = start_y + i * (bar_h + margin)
            frac = min(dev.distance / max_dist, 1.0)
            bar_w = max(4, frac * (vw - 180))

            fill = QColor(dev.color)
            fill.setAlpha(90)
            border = QColor(dev.color)
            border.setAlpha(160)

            self._add_rect(120, y, bar_w, bar_h, fill, border)

            prefix = "⚓ " if dev.is_anchor else ""
            self._add_text(f"{prefix}{dev.name[:14]}", 4, y + 1,
                           QColor("white"), 9)
            self._add_text(f"{dev.distance:.1f}m", 124 + bar_w, y + 1,
                           border, 9, True)

    # ── public API ───────────────────────────────────────────────────────

    def set_result(self, position, anchors_ui, distances, room_w, room_h,
                   devices=None):
        self._room_w = room_w
        self._room_h = room_h
        self._my_pos = position
        now = time.time()

        seen_ids: Set[str] = set()

        for uid, (ax, ay, name) in anchors_ui.items():
            seen_ids.add(uid)
            dist = distances.get(uid, 0.0)
            self._all_devices[uid] = _DeviceOverlayInfo(
                uid, name, dist, True, ax, ay, self._get_color(uid), now)

        if devices:
            for dev in devices:
                seen_ids.add(dev.device_id)
                if dev.device_id not in self._all_devices:
                    self._all_devices[dev.device_id] = _DeviceOverlayInfo(
                        dev.device_id, dev.name, dev.distance,
                        dev.is_anchor, None, None,
                        self._get_color(dev.device_id), now)
                else:
                    d = self._all_devices[dev.device_id]
                    d.distance = dev.distance
                    d.name = dev.name
                    d.last_seen = now

        expired = [uid for uid, d in self._all_devices.items()
                   if now - d.last_seen > _DEVICE_KEEP_SEC]
        for uid in expired:
            del self._all_devices[uid]
            self._selected_ids.discard(uid)

        current_ids = {self._device_list.item(i).data(Qt.ItemDataRole.UserRole)
                       for i in range(self._device_list.count())}
        new_ids = set(self._all_devices.keys())
        added = new_ids - current_ids
        removed = current_ids - new_ids
        if added or removed or (now - self._last_rebuild > _LIST_REBUILD_INTERVAL
                                and current_ids != new_ids):
            self._rebuild_picker()
            self._last_rebuild = now

        # mini-map
        self._minimap.my_pos = position
        self._minimap.room_w = room_w
        self._minimap.room_h = room_h
        anchor_map = {}
        for uid, (ax, ay, name) in anchors_ui.items():
            anchor_map[uid] = (ax, ay, name, self._get_color(uid))
        self._minimap.anchors = anchor_map
        self._minimap.update()

        # scene overlay
        self._update_overlay()

    def _rebuild_picker(self):
        self._device_list.blockSignals(True)
        scroll_pos = self._device_list.verticalScrollBar().value()
        self._device_list.clear()
        for uid, dev in sorted(self._all_devices.items(),
                               key=lambda x: (not x[1].is_anchor, x[1].name)):
            prefix = "⚓ " if dev.is_anchor else ""
            label = f"{prefix}{dev.name}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, uid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if uid in self._selected_ids
                else Qt.CheckState.Unchecked)
            item.setForeground(dev.color)
            self._device_list.addItem(item)
        self._device_list.verticalScrollBar().setValue(scroll_pos)
        self._device_list.blockSignals(False)

    # ── slots ────────────────────────────────────────────────────────────

    def _on_item_changed(self, item: QListWidgetItem):
        uid = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self._selected_ids.add(uid)
        else:
            self._selected_ids.discard(uid)

    def _toggle_select_all(self):
        all_ids = {self._device_list.item(i).data(Qt.ItemDataRole.UserRole)
                   for i in range(self._device_list.count())}
        if self._selected_ids >= all_ids and all_ids:
            self._selected_ids.clear()
            self._select_all_btn.setText("Select All")
        else:
            self._selected_ids = all_ids
            self._select_all_btn.setText("Deselect All")
        self._rebuild_picker()

    def _on_minimap_heading(self, heading: float):
        self._heading = heading
        self._heading_set = True

    def _on_camera_error(self, msg: str):
        self._camera_on = False
        self._toggle_btn.setText("Start Camera")

    def _on_camera_started(self):
        self._toggle_btn.setText("Stop Camera")

    def _toggle_camera(self):
        if self._camera_on:
            self._capture.stop()
            self._camera_on = False
            self._toggle_btn.setText("Start Camera")
        else:
            self._camera_on = True
            self._toggle_btn.setText("Starting…")
            self._capture.start()

    # ── cleanup ──────────────────────────────────────────────────────────

    def stop(self):
        self._camera_on = False
        self._capture.stop()
