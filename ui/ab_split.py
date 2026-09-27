"""A/B split comparison — two independent positioning pipelines side by side.

Each pane runs its own algorithm (Trilateration / Particle Filter / Fusion /
Weighted Centroid) on its own signal-filtered subset of readings (All / BLE /
WiFi).  Panes share the same anchor store and room dimensions but maintain
completely independent Kalman filter state, so their smoothing histories never
interfere.
"""

from __future__ import annotations

from typing import Dict

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.models import SignalReading
from services.anchor_store import AnchorStore
from services.pane_positioner import PanePositioner
from ui.room_canvas import RoomCanvas

ALGORITHMS = [
    ("Trilateration",       "trilateration"),
    ("Particle Filter",     "particle"),
    ("Fusion (T + PF)",     "fusion"),
    ("Weighted Centroid",   "centroid"),
    ("Ensemble (all four)", "ensemble"),
]

SIGNAL_FILTERS = [
    ("All signals", "all"),
    ("\U0001f4f6 BLE only",  "ble"),
    ("\U0001f4e1 WiFi only", "wifi"),
]


class _Pane(QWidget):
    def __init__(self, label: str, color: str, anchors: AnchorStore,
                 default_algo: int = 0, default_sig: int = 0, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)

        header = QHBoxLayout()
        title = QLabel(f"  {label}")
        title.setStyleSheet(
            f"color:{color};font-weight:bold;font-size:13px;"
            f"background:{color}22;border-radius:4px;padding:2px 8px;")
        header.addWidget(title)

        combo_style = (
            "QComboBox{background:#21262d;color:#e2e8f0;border:1px solid #334155;"
            "border-radius:4px;padding:2px 6px;font-size:11px;}"
            "QComboBox::drop-down{border:none;}"
        )

        self._algo_combo = QComboBox()
        for name, _ in ALGORITHMS:
            self._algo_combo.addItem(name)
        self._algo_combo.setCurrentIndex(default_algo)
        self._algo_combo.setStyleSheet(combo_style)
        self._algo_combo.setFixedWidth(155)

        self._sig_combo = QComboBox()
        for name, _ in SIGNAL_FILTERS:
            self._sig_combo.addItem(name)
        self._sig_combo.setCurrentIndex(default_sig)
        self._sig_combo.setStyleSheet(combo_style)
        self._sig_combo.setFixedWidth(110)

        header.addWidget(QLabel("Algo:"))
        header.addWidget(self._algo_combo)
        header.addSpacing(8)
        header.addWidget(QLabel("Signal:"))
        header.addWidget(self._sig_combo)
        header.addStretch()

        self._status_label = QLabel("—")
        self._status_label.setStyleSheet("color:#6b7280;font-size:10px;")
        header.addWidget(self._status_label)
        layout.addLayout(header)

        self._canvas = RoomCanvas()
        layout.addWidget(self._canvas, stretch=1)

        self._positioner = PanePositioner(anchors)
        self._positioner.algorithm = ALGORITHMS[default_algo][1]
        self._positioner.signal_filter = SIGNAL_FILTERS[default_sig][1]

        self._algo_combo.currentIndexChanged.connect(self._on_algo_changed)
        self._sig_combo.currentIndexChanged.connect(self._on_sig_changed)

    def update_readings(
        self,
        readings: Dict[str, SignalReading],
        room_w: float,
        room_h: float,
    ):
        self._canvas.room_w = room_w
        self._canvas.room_h = room_h

        position, anchors_ui, distances, particles, pw = \
            self._positioner.update(readings, room_w, room_h)

        self._canvas.set_anchors(anchors_ui)
        self._canvas.set_distances(distances)
        self._canvas.set_particles(particles, pw)

        if position is not None:
            self._canvas.set_position(*position)
            unc = self._positioner.uncertainty
            unc_str = f"  ±{unc:.2f}m" if unc is not None else ""
            self._status_label.setText(
                f"({position[0]:.2f}, {position[1]:.2f}) m{unc_str}  "
                f"| {len(anchors_ui)} anchors"
            )
        else:
            self._canvas.clear_position()
            self._status_label.setText(f"No position  | {len(anchors_ui)} anchors")

    def _on_algo_changed(self, idx: int):
        self._positioner.algorithm = ALGORITHMS[idx][1]
        self._positioner.reset()

    def _on_sig_changed(self, idx: int):
        self._positioner.signal_filter = SIGNAL_FILTERS[idx][1]
        self._positioner.reset()


class ABSplitView(QWidget):
    """Two independent positioning panes for algorithm/signal comparison."""

    anchor_placed = pyqtSignal(str, float, float)

    def __init__(self, anchors: AnchorStore, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        hint = QLabel(
            "Each pane runs a completely independent positioning pipeline. "
            "Pick a different algorithm and/or signal type on each side to compare results."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            "color:#9ca3af;font-size:11px;padding:4px 8px;"
            "background:#161b22;border-bottom:1px solid #21262d;")
        layout.addWidget(hint)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._pane_a = _Pane("Pane A", "#3b82f6", anchors,
                             default_algo=0, default_sig=0)
        self._pane_b = _Pane("Pane B", "#22c55e", anchors,
                             default_algo=1, default_sig=1)

        splitter.addWidget(self._pane_a)
        splitter.addWidget(self._pane_b)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)

    def set_readings(
        self,
        readings: Dict[str, SignalReading],
        room_w: float,
        room_h: float,
    ):
        self._pane_a.update_readings(readings, room_w, room_h)
        self._pane_b.update_readings(readings, room_w, room_h)

    def set_devices(self, devices):
        pass
