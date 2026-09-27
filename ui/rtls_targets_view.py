"""RTLS targets view — where every device is, from all antennas combined.

Top: a room map plotting each antenna (blue) and each located target (colored
dot + accuracy circle). Bottom: a table with one row per target, one column
per antenna (that antenna's measured distance) plus the fused (x, y), its
uncertainty and GDOP — exactly the "computer sees / antenna sees / fused"
breakdown.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_COLORS = [
    QColor(239, 68, 68), QColor(59, 130, 246), QColor(16, 185, 129),
    QColor(245, 158, 11), QColor(139, 92, 246), QColor(236, 72, 153),
    QColor(6, 182, 212), QColor(234, 179, 8),
]


class _RoomMap(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(260)
        self.room_w = 8.0
        self.room_h = 6.0
        self.antennas: Dict[str, Tuple[float, float, str]] = {}
        self.targets: List[dict] = []   # {x,y,name,color,unc}

    def _to_screen(self, x, y, w, h, pad=28):
        sx = pad + (x / max(self.room_w, 0.1)) * (w - 2 * pad)
        sy = pad + (y / max(self.room_h, 0.1)) * (h - 2 * pad)
        return sx, sy

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, QColor(13, 17, 23))
        # room rectangle
        x0, y0 = self._to_screen(0, 0, w, h)
        x1, y1 = self._to_screen(self.room_w, self.room_h, w, h)
        p.setPen(QPen(QColor(48, 54, 61), 1))
        p.drawRect(QRectF(x0, y0, x1 - x0, y1 - y0))

        m_per_px = self.room_w / max(x1 - x0, 1)

        # antennas
        for nid, (ax, ay, name) in self.antennas.items():
            sx, sy = self._to_screen(ax, ay, w, h)
            p.setBrush(QColor(59, 130, 246))
            p.setPen(QPen(QColor(147, 197, 253), 2))
            p.drawEllipse(QPointF(sx, sy), 6, 6)
            p.setPen(QColor(147, 197, 253))
            p.setFont(QFont("Helvetica", 8))
            p.drawText(QPointF(sx + 8, sy + 3), f"📡 {name}")

        # targets
        for t in self.targets:
            sx, sy = self._to_screen(t["x"], t["y"], w, h)
            color = t["color"]
            # accuracy circle
            unc = t.get("unc")
            if unc:
                r_px = max(6, unc / max(m_per_px, 1e-6))
                ring = QColor(color); ring.setAlpha(40)
                p.setBrush(ring)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(sx, sy), r_px, r_px)
            p.setBrush(color)
            p.setPen(QPen(QColor("white"), 1))
            p.drawEllipse(QPointF(sx, sy), 5, 5)
            p.setPen(QColor("white"))
            p.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
            p.drawText(QPointF(sx + 8, sy + 3), t["name"])

        if not self.antennas:
            p.setPen(QColor(100, 116, 139))
            p.setFont(QFont("Helvetica", 11))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Waiting for antennas…")
        p.end()


class RtlsTargetsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._color_map: Dict[str, QColor] = {}
        self._cidx = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._map = _RoomMap()
        layout.addWidget(self._map, stretch=2)

        self._table = QTableWidget(0, 0)
        self._table.setStyleSheet(
            "QTableWidget{background:#0d1117;color:#e2e8f0;font-size:11px;"
            "gridline-color:#21262d;}"
            "QHeaderView::section{background:#161b22;color:#94a3b8;"
            "padding:3px;border:none;font-size:11px;}")
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table, stretch=1)

        self._status = QLabel("")
        self._status.setStyleSheet("font-size:11px;color:#64748b;")
        layout.addWidget(self._status)

    def _color(self, tid: str) -> QColor:
        if tid not in self._color_map:
            self._color_map[tid] = _COLORS[self._cidx % len(_COLORS)]
            self._cidx += 1
        return self._color_map[tid]

    def update_view(
        self,
        room_w: float,
        room_h: float,
        antennas: Dict[str, Tuple[float, float, str]],   # node_id -> (x,y,name)
        per_target_fixes: Dict[str, dict],               # from collect_target_fixes
        targets: List,                                   # List[TargetEstimate]
    ):
        self._map.room_w = room_w
        self._map.room_h = room_h
        self._map.antennas = antennas

        est_by_id = {t.target_id: t for t in targets}
        self._map.targets = [
            {"x": t.x, "y": t.y, "name": t.name, "color": self._color(t.target_id),
             "unc": t.uncertainty_radius}
            for t in targets
        ]
        self._map.update()

        # table: columns = antennas + fused + gdop
        node_ids = list(antennas.keys())
        headers = ["Target"] + [antennas[n][2] for n in node_ids] + ["Fused (x,y)", "±", "GDOP"]
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)

        rows = [tid for tid in per_target_fixes if tid in est_by_id]
        self._table.setRowCount(len(rows))

        for r, tid in enumerate(rows):
            entry = per_target_fixes[tid]
            est = est_by_id[tid]
            dist_by_node = {f[0]: f[3] for f in entry["fixes"]}

            name_item = QTableWidgetItem(entry["name"])
            name_item.setForeground(self._color(tid))
            self._table.setItem(r, 0, name_item)

            for c, nid in enumerate(node_ids, start=1):
                d = dist_by_node.get(nid)
                txt = f"{d:.1f} m" if d is not None else "—"
                self._table.setItem(r, c, QTableWidgetItem(txt))

            base = 1 + len(node_ids)
            self._table.setItem(r, base,
                                QTableWidgetItem(f"({est.x:.2f}, {est.y:.2f})"))
            unc = f"{est.uncertainty_radius:.2f}" if est.uncertainty_radius else "—"
            self._table.setItem(r, base + 1, QTableWidgetItem(unc))
            g = f"{est.gdop:.1f}" if est.gdop else "—"
            self._table.setItem(r, base + 2, QTableWidgetItem(g))

        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._status.setText(
            f"{len(antennas)} antennas · {len(rows)} targets located "
            f"(need a device seen by ≥2 antennas)")
