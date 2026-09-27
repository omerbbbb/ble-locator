"""Distance A/B tab — per-device distance via Kalman-only vs the full chain."""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.distance_compare_service import DistanceRow


def _fmt(d: float) -> str:
    return f"{d*100:.0f} cm" if d < 1 else f"{d:.2f} m"


class DistanceABView(QWidget):
    device_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QLabel(
            "<b>Distance A/B — filter comparison</b><br>"
            "<span style='color:#9ca3af;font-size:11px;'>"
            "Both columns use the <b>same</b> calibration and clamp — the only "
            "difference is the RSSI filter. <b>Kalman-only</b> reacts faster but "
            "stays noisier; the <b>full chain</b> (Median→Hampel→Kalman) rejects "
            "spikes. Δ is how far the two estimates disagree right now."
            "</span>"
        )
        header.setWordWrap(True)
        header.setStyleSheet("padding:4px;background:#161b22;"
                             "border:1px solid #21262d;border-radius:6px;")
        layout.addWidget(header)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels([
            "Device", "RSSI (dBm)", "Kalman → dist", "Full chain → dist", "Δ",
        ])
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._table.setStyleSheet(
            "QTableWidget{background:#161b22;color:#e2e8f0;gridline-color:#21262d;"
            "font-size:12px;alternate-background-color:#1c2128;}"
            "QHeaderView::section{background:#21262d;color:#93c5fd;padding:6px;"
            "border:1px solid #334155;font-weight:bold;font-size:11px;}"
            "QTableWidget::item{padding:4px;}"
        )
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._table, stretch=1)

    def _on_item_clicked(self, item):
        row = item.row()
        cell = self._table.item(row, 0)
        if cell is not None:
            did = cell.data(Qt.ItemDataRole.UserRole)
            if did:
                self.device_selected.emit(did)

    def set_rows(self, rows: List[DistanceRow], selected_id: Optional[str] = None):
        # Pin the selected (tracked) device to the top so it never jumps while
        # you watch it; the rest follow by strongest signal.
        ordered = sorted(
            rows, key=lambda r: (r.device_id != selected_id, -r.rssi))
        self._table.setRowCount(len(ordered))

        for row, r in enumerate(ordered):
            delta = abs(r.d_kalman - r.d_full)
            vals = [r.name, f"{r.rssi}", _fmt(r.d_kalman), _fmt(r.d_full), _fmt(delta)]
            is_sel = r.device_id == selected_id
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, r.device_id)
                    item.setToolTip(f"UUID: {r.device_id}")
                if col == 4:
                    item.setForeground(QColor("#22c55e") if delta < 0.5
                                       else QColor("#f59e0b") if delta < 1.5
                                       else QColor("#ef4444"))
                if is_sel:
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                    item.setBackground(QColor("#1e3a5f"))
                self._table.setItem(row, col, item)
