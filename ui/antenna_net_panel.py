"""Antenna network panel — see, place, and toggle the connected antennas.

Lists every antenna feeding the manager (the local computer + remote nodes).
Per antenna: include/exclude checkbox, name, live device count, health dot,
and X/Y position spin-boxes. Position editing mirrors the anchor flow: the
user places each antenna in room coordinates; an "auto-snap to measured
radius" assist is available where the manager has a distance to that antenna,
and can be turned off for fully manual placement.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, Optional, Set, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class _AntennaRow(QWidget):
    changed = pyqtSignal()

    def __init__(self, node_id: str, name: str, is_local: bool, parent=None):
        super().__init__(parent)
        self.node_id = node_id
        self._is_local = is_local

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 3, 6, 3)
        row.setSpacing(6)

        self.include = QCheckBox()
        self.include.setChecked(True)
        self.include.setToolTip("Use this antenna in fusion")
        self.include.toggled.connect(lambda _: self.changed.emit())
        row.addWidget(self.include)

        self._dot = QLabel("●")
        self._dot.setStyleSheet("color:#10b981;font-size:13px;")
        row.addWidget(self._dot)

        icon = "🖥️" if is_local else "📡"
        self._name = QLabel(f"{icon} {name}")
        self._name.setStyleSheet("font-size:12px;")
        self._name.setMinimumWidth(140)
        row.addWidget(self._name, stretch=1)

        self._count = QLabel("0 devices")
        self._count.setStyleSheet("font-size:11px;color:#94a3b8;")
        self._count.setFixedWidth(80)
        self._count.setToolTip("devices seen by this antenna")
        row.addWidget(self._count)

        self._age = QLabel("")
        self._age.setStyleSheet("font-size:10px;color:#475569;")
        self._age.setFixedWidth(56)
        row.addWidget(self._age)

        row.addWidget(QLabel("x"))
        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(0.0, 100.0)
        self.x_spin.setSingleStep(0.1)
        self.x_spin.setDecimals(2)
        self.x_spin.setFixedWidth(64)
        self.x_spin.valueChanged.connect(lambda _: self.changed.emit())
        row.addWidget(self.x_spin)

        row.addWidget(QLabel("y"))
        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(0.0, 100.0)
        self.y_spin.setSingleStep(0.1)
        self.y_spin.setDecimals(2)
        self.y_spin.setFixedWidth(64)
        self.y_spin.valueChanged.connect(lambda _: self.changed.emit())
        row.addWidget(self.y_spin)

    def set_health(self, fresh: bool):
        self._dot.setStyleSheet(
            f"color:{'#10b981' if fresh else '#ef4444'};font-size:13px;")

    def set_count(self, n: int):
        self._count.setText(f"{n} devices")

    def set_age(self, seconds_ago: float):
        if seconds_ago < 2:
            txt, color = "just now", "#10b981"
        elif seconds_ago < 6:
            txt, color = f"{seconds_ago:.0f}s ago", "#94a3b8"
        else:
            txt, color = f"{seconds_ago:.0f}s ago", "#ef4444"
        self._age.setText(txt)
        self._age.setStyleSheet(f"font-size:10px;color:{color};")

    def position(self) -> Tuple[float, float]:
        return self.x_spin.value(), self.y_spin.value()

    def set_position_silent(self, x: float, y: float):
        for sp, v in ((self.x_spin, x), (self.y_spin, y)):
            sp.blockSignals(True)
            sp.setValue(v)
            sp.blockSignals(False)

    def included(self) -> bool:
        return self.include.isChecked()


class AntennaNetPanel(QWidget):
    """Shows connected antennas; emits when inclusion or positions change."""
    layout_changed = pyqtSignal()  # selection or positions changed

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: Dict[str, _AntennaRow] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        title = QLabel("Antenna network")
        title.setStyleSheet("font-size:13px;font-weight:bold;color:#e2e8f0;")
        outer.addWidget(title)

        hint = QLabel("Tick the antennas to fuse, and set each one's position "
                      "in the room (metres).")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size:11px;color:#64748b;")
        outer.addWidget(hint)

        self._summary = QLabel("No antennas connected")
        self._summary.setStyleSheet(
            "font-size:12px;color:#94a3b8;padding:4px 6px;"
            "background:#161b22;border:1px solid #21262d;border-radius:4px;")
        outer.addWidget(self._summary)

        self._rows_box = QVBoxLayout()
        self._rows_box.setSpacing(2)
        outer.addLayout(self._rows_box)

        self._empty = QLabel("No antennas yet. Run the app with --antenna on "
                             "another computer, or wait for one to connect.")
        self._empty.setWordWrap(True)
        self._empty.setStyleSheet("font-size:11px;color:#475569;padding:8px;")
        outer.addWidget(self._empty)

        outer.addStretch()

    def included_nodes(self) -> Set[str]:
        return {nid for nid, r in self._rows.items() if r.included()}

    def positions(self) -> Dict[str, Tuple[float, float]]:
        return {nid: r.position() for nid, r in self._rows.items()}

    def sync(self, antennas: Dict[str, dict]):
        """antennas: {node_id: {name, is_local, x, y, count, last_seen}}."""
        now = time.time()
        # add new rows
        for nid, info in antennas.items():
            if nid not in self._rows:
                row = _AntennaRow(nid, info["name"], info.get("is_local", False))
                row.set_position_silent(info.get("x", 0.0), info.get("y", 0.0))
                row.changed.connect(self.layout_changed.emit)
                self._rows[nid] = row
                self._rows_box.addWidget(row)
            r = self._rows[nid]
            r.set_count(info.get("count", 0))
            age = now - info.get("last_seen", now)
            r.set_health(age <= 6.0)
            r.set_age(age)

        # remove gone rows
        for nid in list(self._rows.keys()):
            if nid not in antennas:
                row = self._rows.pop(nid)
                self._rows_box.removeWidget(row)
                row.deleteLater()

        self._empty.setVisible(not self._rows)
        n = len(self._rows)
        if n == 0:
            self._summary.setText("No antennas connected")
        else:
            total_dev = sum(info.get("count", 0) for info in antennas.values())
            self._summary.setText(
                f"📡 {n} antenna{'s' if n > 1 else ''} connected — "
                f"{total_dev} total devices seen")
