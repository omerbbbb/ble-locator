"""Combination comparison view — which antenna set locates a target best.

Pick a target; see its position computed by every antenna subset (size ≥2),
ranked by predicted accuracy (GDOP, then uncertainty). Lets the user discover
which antennas help and which combinations to trust.
"""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class CombinationView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._target_ids: List[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.addWidget(QLabel("Target:"))
        self._combo = QComboBox()
        self._combo.setMinimumWidth(200)
        self._combo.setStyleSheet(
            "QComboBox{background:#1f2937;color:#e2e8f0;border:1px solid #334155;"
            "border-radius:6px;padding:3px 8px;font-size:12px;}")
        top.addWidget(self._combo)
        top.addStretch()
        layout.addLayout(top)

        hint = QLabel("Every antenna combination, ranked by predicted accuracy "
                      "(lower GDOP = better geometry). Use it to see which "
                      "antennas matter most.")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size:11px;color:#64748b;")
        layout.addWidget(hint)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["Antennas", "Position (x,y)", "Uncertainty ±", "GDOP"])
        self._table.setStyleSheet(
            "QTableWidget{background:#0d1117;color:#e2e8f0;font-size:11px;"
            "gridline-color:#21262d;}"
            "QHeaderView::section{background:#161b22;color:#94a3b8;"
            "padding:4px;border:none;font-size:11px;}")
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table, stretch=1)

    @property
    def selected_target(self) -> Optional[str]:
        return self._combo.currentData()

    def set_targets(self, targets: List[tuple]):
        """targets: [(target_id, name)]."""
        ids = [t[0] for t in targets]
        if ids == self._target_ids:
            return
        self._target_ids = ids
        keep = self._combo.currentData()
        self._combo.blockSignals(True)
        self._combo.clear()
        for tid, name in targets:
            self._combo.addItem(name, tid)
        idx = self._combo.findData(keep)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        self._combo.blockSignals(False)

    def set_results(self, results: List):
        """results: ranked List[CombinationResult] (best first)."""
        self._table.setRowCount(len(results))
        for r, res in enumerate(results):
            est = res.estimate
            names = " + ".join(res.node_ids)
            self._table.setItem(r, 0, QTableWidgetItem(names))
            self._table.setItem(r, 1, QTableWidgetItem(f"({est.x:.2f}, {est.y:.2f})"))
            unc = f"{est.uncertainty_radius:.2f}" if est.uncertainty_radius else "—"
            self._table.setItem(r, 2, QTableWidgetItem(unc))
            g = f"{est.gdop:.2f}" if est.gdop else "poor"
            gitem = QTableWidgetItem(g)
            if r == 0:
                for c in range(4):
                    it = self._table.item(r, c)
                    if it:
                        it.setForeground(Qt.GlobalColor.green)
            self._table.setItem(r, 3, gitem)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
