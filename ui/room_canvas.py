from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF, QTransform
from PyQt6.QtWidgets import QInputDialog, QMenu, QPushButton, QWidget

ANCHOR_COLORS = ["#e74c3c", "#e67e22", "#9b59b6", "#1abc9c", "#e91e63"]
_GRID_STEPS = [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0]


class RoomCanvas(QWidget):
    device_dropped = pyqtSignal(str, float, float)
    anchor_reaimed = pyqtSignal(str, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

        self.room_w: float = 8.0
        self.room_h: float = 6.0
        self.position: Optional[Tuple[float, float]] = None
        self.anchors: Dict[str, Tuple[float, float, str]] = {}
        self.distances: Dict[str, float] = {}
        self.uncertainty_ellipse: Optional[Tuple[float, float, float]] = None
        self._particles = None
        self._particle_weights = None

        self._zoom: float = 1.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        self._panning = False
        self._drag_start: Optional[QPointF] = None
        self._pan_start: Tuple[float, float] = (0.0, 0.0)

        # Live drag preview state
        self._drag_preview_pos: Optional[QPointF] = None
        self._drag_preview_dist: Optional[float] = None

        # Anchor re-aim state
        self._reaim_anchor_id: Optional[str] = None
        self._reaim_start: Optional[QPointF] = None

        self._btn_in = self._mk_btn("+", self.zoom_in)
        self._btn_out = self._mk_btn("−", self.zoom_out)
        self._btn_reset = self._mk_btn("⟳", self.zoom_reset)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

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

    # --- Zoom / Pan --------------------------------------------------
    def zoom_in(self):
        self._zoom = min(self._zoom * 1.4, 50.0)
        self.update()

    def zoom_out(self):
        self._zoom = max(self._zoom / 1.4, 0.5)
        self.update()

    def zoom_reset(self):
        self._zoom = 1.0
        self._pan_x = self._pan_y = 0.0
        self.update()

    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 1.0 / 1.25
        self._zoom = max(0.5, min(self._zoom * factor, 50.0))
        self.update()

    # --- Mouse: pan + anchor re-aim -----------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.AltModifier
        ):
            self._panning = True
            self._drag_start = event.position()
            self._pan_start = (self._pan_x, self._pan_y)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit_test_anchor(event.position())
            if hit is not None:
                self._reaim_anchor_id = hit
                self._reaim_start = event.position()
                self.setCursor(Qt.CursorShape.CrossCursor)

    def mouseMoveEvent(self, event):
        if self._panning and self._drag_start is not None:
            dx = event.position().x() - self._drag_start.x()
            dy = event.position().y() - self._drag_start.y()
            self._pan_x = self._pan_start[0] + dx
            self._pan_y = self._pan_start[1] + dy
            self.update()
            return

        if self._reaim_anchor_id is not None:
            mac_sp = self._mac_screen_pos()
            dx = event.position().x() - mac_sp.x()
            dy = -(event.position().y() - mac_sp.y())
            self.anchor_reaimed.emit(self._reaim_anchor_id, dx, dy)
            self.update()

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._panning = False
            self.unsetCursor()
        if self._reaim_anchor_id is not None:
            self._reaim_anchor_id = None
            self.unsetCursor()

    def _hit_test_anchor(self, screen_pos: QPointF) -> Optional[str]:
        for uid, (ax, ay, _name) in self.anchors.items():
            ap = self._world_to_screen(ax, ay)
            dx = screen_pos.x() - ap.x()
            dy = screen_pos.y() - ap.y()
            if dx * dx + dy * dy < 15 * 15:
                return uid
        return None

    # --- Drop support -------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-blelocator-device"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()
        self._drag_preview_pos = event.position()
        self.update()

    def dragLeaveEvent(self, event):
        self._drag_preview_pos = None
        self._drag_preview_dist = None
        self.update()

    def dropEvent(self, event):
        data = event.mimeData().data("application/x-blelocator-device")
        if not data:
            return
        device_id = bytes(data).decode()
        pos = event.position()
        mac_sp = self._mac_screen_pos()
        screen_dx = pos.x() - mac_sp.x()
        screen_dy = -(pos.y() - mac_sp.y())
        self.device_dropped.emit(device_id, screen_dx, screen_dy)
        self._drag_preview_pos = None
        self._drag_preview_dist = None
        event.acceptProposedAction()
        self.update()

    def set_drag_preview_distance(self, dist: float):
        self._drag_preview_dist = dist

    def _screen_to_world(self, sx: float, sy: float) -> Tuple[float, float]:
        m = self._margin()
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        base_x = (sx - self._pan_x - cx) / self._zoom + cx
        base_y = (sy - self._pan_y - cy) / self._zoom + cy
        cw = self.width() - 2 * m
        ch = self.height() - 2 * m
        wx = (base_x - m) / cw * self.room_w
        wy = (1.0 - (base_y - m) / ch) * self.room_h
        return max(0.0, min(self.room_w, wx)), max(0.0, min(self.room_h, wy))

    # --- Public API --------------------------------------------------
    def set_position(self, x: float, y: float):
        self.position = (x, y)
        self.update()

    def clear_position(self):
        self.position = None
        self.update()

    def set_anchors(self, anchors: Dict[str, Tuple[float, float, str]]):
        self.anchors = anchors
        self.update()

    def set_distances(self, distances: Dict[str, float]):
        self.distances = distances
        self.update()

    def set_uncertainty(self, ellipse: Optional[Tuple[float, float, float]]):
        self.uncertainty_ellipse = ellipse
        self.update()

    def set_particles(self, particles, weights):
        self._particles = particles
        self._particle_weights = weights
        self.update()

    # --- Coordinate transforms ----------------------------------------
    def _margin(self) -> int:
        return 30

    def _mac_screen_pos(self) -> QPointF:
        if self.position is not None:
            return self._world_to_screen(*self.position)
        return self._world_to_screen(self.room_w / 2.0, self.room_h / 2.0)

    def _world_to_screen(self, wx: float, wy: float) -> QPointF:
        m = self._margin()
        cw = self.width() - 2 * m
        ch = self.height() - 2 * m
        base_x = m + wx / self.room_w * cw
        base_y = m + (1.0 - wy / self.room_h) * ch
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        sx = cx + (base_x - cx) * self._zoom + self._pan_x
        sy = cy + (base_y - cy) * self._zoom + self._pan_y
        return QPointF(sx, sy)

    def _draw_circle_at(self, painter: QPainter, wx: float, wy: float, r_px: int,
                        color: str, label: str = ""):
        sp = self._world_to_screen(wx, wy)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(sp, r_px, r_px)
        if label:
            painter.setPen(QColor("white"))
            painter.setFont(QFont("Helvetica", 10))
            painter.drawText(QPointF(sp.x() + r_px + 4, sp.y() + 4), label)

    @staticmethod
    def _grid_step(room_dim: float, zoom: float) -> float:
        visible = room_dim / zoom
        for s in _GRID_STEPS:
            if visible / s <= 12:
                return s
        return _GRID_STEPS[-1]

    def _draw_arrow(self, painter: QPainter, from_pt: QPointF, to_pt: QPointF,
                    color: QColor, width: float = 2):
        painter.setPen(QPen(color, width))
        painter.drawLine(from_pt, to_pt)
        dx = to_pt.x() - from_pt.x()
        dy = to_pt.y() - from_pt.y()
        line_len = math.sqrt(dx * dx + dy * dy)
        if line_len > 20:
            nx, ny = dx / line_len, dy / line_len
            tip = to_pt
            left = QPointF(tip.x() - 10 * nx + 6 * ny,
                           tip.y() - 10 * ny - 6 * nx)
            right = QPointF(tip.x() - 10 * nx - 6 * ny,
                            tip.y() - 10 * ny + 6 * nx)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(QPolygonF([tip, left, right]))

    # --- Paint --------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, QColor("#0d1117"))
        m = self._margin()

        # Room border
        tl = self._world_to_screen(0, self.room_h)
        br = self._world_to_screen(self.room_w, 0)
        room_rect = QRectF(tl, br)
        painter.setPen(QPen(QColor("#4a90d9"), 2))
        painter.setBrush(QColor("#111827"))
        painter.drawRect(room_rect)

        # Adaptive grid
        step_x = self._grid_step(self.room_w, self._zoom)
        step_y = self._grid_step(self.room_h, self._zoom)

        painter.setFont(QFont("Helvetica", 8))
        gx = step_x
        while gx < self.room_w:
            p = self._world_to_screen(gx, 0)
            p2 = self._world_to_screen(gx, self.room_h)
            painter.setPen(QPen(QColor("#1e293b"), 1))
            painter.drawLine(QPointF(p.x(), p2.y()), p)
            painter.setPen(QColor("#475569"))
            lbl = f"{gx:.1f}" if gx != int(gx) else f"{int(gx)}"
            painter.drawText(QPointF(p.x() - 6, p.y() + 14), lbl)
            gx += step_x

        gy = step_y
        while gy < self.room_h:
            p = self._world_to_screen(0, gy)
            p2 = self._world_to_screen(self.room_w, gy)
            painter.setPen(QPen(QColor("#1e293b"), 1))
            painter.drawLine(p, QPointF(p2.x(), p.y()))
            painter.setPen(QColor("#475569"))
            lbl = f"{gy:.1f}" if gy != int(gy) else f"{int(gy)}"
            painter.drawText(QPointF(p.x() - 24, p.y() + 4), lbl)
            gy += step_y

        # Room label
        painter.setPen(QColor("#6b7280"))
        painter.setFont(QFont("Helvetica", 9))
        painter.drawText(QRect(0, 2, w, m - 4),
                         Qt.AlignmentFlag.AlignCenter,
                         f"Room: {self.room_w:.1f} × {self.room_h:.1f} m  ×{self._zoom:.1f}  "
                         f"(scroll=zoom  alt+drag=pan  right-click=settings)")

        # Particle cloud
        if self._particles is not None and self._particle_weights is not None:
            try:
                import numpy as np
                pw = self._particle_weights
                pw_norm = (pw - pw.min()) / max(pw.max() - pw.min(), 1e-9)
                painter.setPen(Qt.PenStyle.NoPen)
                for i in range(len(self._particles)):
                    px_w, py_w = float(self._particles[i, 0]), float(self._particles[i, 1])
                    sp = self._world_to_screen(px_w, py_w)
                    alpha = int(30 + pw_norm[i] * 180)
                    painter.setBrush(QColor(20, 220, 180, alpha))
                    painter.drawEllipse(sp, 2, 2)
            except Exception:
                pass

        # Anchors (fixed reference points)
        color_idx = 0
        anchor_colors: Dict[str, str] = {}
        mac_sp = self._mac_screen_pos()
        for uid, (ax, ay, name) in self.anchors.items():
            color = ANCHOR_COLORS[color_idx % len(ANCHOR_COLORS)]
            anchor_colors[uid] = color
            color_idx += 1

            ap = self._world_to_screen(ax, ay)
            # Anchor dot
            painter.setBrush(QColor(color))
            painter.setPen(QPen(QColor("white"), 1))
            painter.drawEllipse(ap, 8, 8)
            painter.setPen(QColor("white"))
            painter.setFont(QFont("Helvetica", 10))
            painter.drawText(QPointF(ap.x() + 12, ap.y() + 4), name)

            # Arrow from Mac to anchor
            arrow_c = QColor(color)
            arrow_c.setAlpha(180)
            self._draw_arrow(painter, mac_sp, ap, arrow_c)

            # Distance label on arrow
            dist = self.distances.get(uid)
            if dist is not None:
                mid = QPointF((mac_sp.x() + ap.x()) / 2,
                              (mac_sp.y() + ap.y()) / 2)
                painter.setPen(QColor(color))
                painter.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
                painter.drawText(QPointF(mid.x() + 4, mid.y() - 4),
                                 f"{dist:.1f}m")

            # Angle label near anchor
            dx_w = ax - (self.position[0] if self.position else self.room_w / 2.0)
            dy_w = ay - (self.position[1] if self.position else self.room_h / 2.0)
            angle_deg = math.degrees(math.atan2(dy_w, dx_w))
            painter.setPen(QColor(color))
            painter.setFont(QFont("Helvetica", 8))
            painter.drawText(QPointF(ap.x() + 12, ap.y() + 16),
                             f"{angle_deg:+.0f}°")

        # Mac dot (computed position — moves when trilateration works)
        if self.position is not None:
            # Uncertainty ellipse
            if self.uncertainty_ellipse is not None:
                semi_a, semi_b, angle_rad = self.uncertainty_ellipse
                cw_px = (self.width() - 2 * m)
                ch_px = (self.height() - 2 * m)
                px_per_m_x = cw_px / self.room_w * self._zoom
                px_per_m_y = ch_px / self.room_h * self._zoom
                rx = semi_a * px_per_m_x
                ry = semi_b * px_per_m_y
                painter.save()
                painter.translate(mac_sp)
                painter.rotate(-math.degrees(angle_rad))
                uc = QColor("#3b82f6")
                uc.setAlpha(35)
                painter.setBrush(uc)
                painter.setPen(QPen(QColor(59, 130, 246, 100), 1, Qt.PenStyle.DashLine))
                painter.drawEllipse(QPointF(0, 0), rx, ry)
                painter.restore()

            painter.setBrush(QColor("#3b82f6"))
            painter.setPen(QPen(QColor("white"), 2))
            painter.drawEllipse(mac_sp, 10, 10)
            painter.setPen(QColor("white"))
            painter.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
            painter.drawText(QPointF(mac_sp.x() + 14, mac_sp.y() + 4), "Mac (You)")
        else:
            # No position yet — show Mac at centre with "?"
            painter.setBrush(QColor("#3b82f6"))
            painter.setPen(QPen(QColor("#64748b"), 2, Qt.PenStyle.DashLine))
            painter.drawEllipse(mac_sp, 10, 10)
            painter.setPen(QColor("white"))
            painter.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
            painter.drawText(QPointF(mac_sp.x() - 5, mac_sp.y() + 5), "?")
            painter.setFont(QFont("Helvetica", 9))
            painter.drawText(QPointF(mac_sp.x() + 14, mac_sp.y() + 4), "Mac")

        # Live drag preview — distance ring + arrow
        if self._drag_preview_pos is not None:
            cursor = self._drag_preview_pos
            preview_c = QColor("#60a5fa")
            preview_c.setAlpha(150)

            # Distance ring
            if self._drag_preview_dist is not None and self._drag_preview_dist > 0.01:
                cw_px = (self.width() - 2 * m)
                px_per_m = cw_px / self.room_w * self._zoom
                ring_r = self._drag_preview_dist * px_per_m
                ring_c = QColor("#3b82f6")
                ring_c.setAlpha(60)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(ring_c, 1.5, Qt.PenStyle.DashLine))
                painter.drawEllipse(mac_sp, ring_r, ring_r)

            # Preview arrow from Mac to cursor
            self._draw_arrow(painter, mac_sp, cursor, preview_c, 2)

            # Angle readout
            dx = cursor.x() - mac_sp.x()
            dy = -(cursor.y() - mac_sp.y())
            angle = math.degrees(math.atan2(dy, dx))
            painter.setPen(QColor("#93c5fd"))
            painter.setFont(QFont("Helvetica", 10, QFont.Weight.Bold))
            painter.drawText(QPointF(cursor.x() + 12, cursor.y() - 8),
                             f"{angle:+.0f}°")

        # Instructional overlay
        n_anchors = len(self.anchors)
        if self.position is None:
            if n_anchors < 3:
                lines = [
                    "No position yet",
                    "",
                    f"Anchors set: {n_anchors} / 3",
                    "",
                    "→ Drag a device from the list on the right",
                    "   and drop it in its rough direction.",
                    "   Distance is auto-computed from BLE signal.",
                    "",
                    "→ Click an anchor to re-aim its direction.",
                    "",
                    "Mac position appears after 3 anchors.",
                ]
            else:
                lines = [
                    "Waiting for anchor signals…",
                    "",
                    "Anchors are set, but not all are visible",
                    "right now. Make sure they're powered on",
                    "and in range.",
                ]
            box_w, box_h = 360, 22 * len(lines) + 24
            bx = (w - box_w) // 2
            by = (h - box_h) // 2
            painter.setBrush(QColor(20, 27, 38, 235))
            painter.setPen(QPen(QColor("#3b82f6"), 1))
            painter.drawRoundedRect(bx, by, box_w, box_h, 10, 10)
            for i, line in enumerate(lines):
                if line == lines[0]:
                    painter.setPen(QColor("#3b82f6"))
                    painter.setFont(QFont("Helvetica", 14, QFont.Weight.Bold))
                else:
                    painter.setPen(QColor("#cbd5e1"))
                    painter.setFont(QFont("Helvetica", 11))
                painter.drawText(bx + 16, by + 28 + i * 22, line)

        painter.end()

    # --- Layout -------------------------------------------------------
    def resizeEvent(self, event):
        x = 8
        for b in (self._btn_in, self._btn_out, self._btn_reset):
            b.move(x, self.height() - 36)
            x += 32

    # --- Context menu -------------------------------------------------
    def _show_context_menu(self, pos: QPoint):
        menu = QMenu(self)
        menu.addAction("Set Room Dimensions…", self._set_room_dimensions)
        menu.addAction("Zoom to Fit", self.zoom_fit)
        menu.exec(self.mapToGlobal(pos))

    def _set_room_dimensions(self):
        w, ok = QInputDialog.getDouble(self, "Room Width", "Width (metres):", self.room_w, 1, 100, 1)
        if ok:
            self.room_w = w
        h, ok = QInputDialog.getDouble(self, "Room Height", "Height (metres):", self.room_h, 1, 100, 1)
        if ok:
            self.room_h = h
        self.update()
