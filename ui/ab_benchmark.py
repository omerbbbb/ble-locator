"""Benchmark tab: comparison table + accuracy-over-time chart.

Records positioning snapshots over time and displays a clear summary table
showing how the system is performing. Each row shows a snapshot configuration
with its accuracy metrics.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from PyQt6.QtCore import QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import DeviceEstimate, PositionResult, SignalType

HISTORY_LEN = 120
COLORS = ["#3b82f6", "#ef4444", "#22c55e", "#f59e0b", "#a855f7"]


class _AccuracyChart(QWidget):
    """Draws uncertainty radius over time for each tracked configuration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(140)
        self._series: Dict[str, Deque[float]] = {}
        self._color_map: Dict[str, str] = {}
        self._ci = 0

    def add_point(self, label: str, uncertainty: float):
        if label not in self._series:
            self._series[label] = deque(maxlen=HISTORY_LEN)
            self._color_map[label] = COLORS[self._ci % len(COLORS)]
            self._ci += 1
        self._series[label].append(uncertainty)
        self.update()

    def clear(self):
        self._series.clear()
        self._color_map.clear()
        self._ci = 0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        m = 45
        cw, ch = w - m - 10, h - 2 * m + 20

        painter.fillRect(0, 0, w, h, QColor("#0d1117"))

        if not self._series:
            painter.setPen(QColor("#6b7280"))
            painter.setFont(QFont("Helvetica", 12))
            painter.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                             "Waiting for position data...\n"
                             "Set 3+ anchors to start tracking accuracy")
            painter.end()
            return

        painter.setPen(QPen(QColor("#334155"), 1))
        painter.drawLine(m, m - 10, m, h - m + 10)
        painter.drawLine(m, h - m + 10, w - 10, h - m + 10)

        all_vals = [v for s in self._series.values() for v in s]
        if not all_vals:
            painter.end()
            return
        y_max = max(max(all_vals), 0.3)

        # Y-axis labels
        painter.setPen(QColor("#475569"))
        painter.setFont(QFont("Helvetica", 8))
        for i in range(5):
            val = y_max * i / 4
            y = h - m + 10 - int(i / 4 * ch)
            painter.setPen(QPen(QColor("#1e293b"), 1))
            painter.drawLine(m, y, w - 10, y)
            painter.setPen(QColor("#475569"))
            painter.drawText(QRect(0, y - 8, m - 4, 16),
                             Qt.AlignmentFlag.AlignRight, f"{val:.2f}m")

        # Title
        painter.setPen(QColor("#93c5fd"))
        painter.setFont(QFont("Helvetica", 10, QFont.Weight.Bold))
        painter.drawText(QRect(m, 2, cw, 18), Qt.AlignmentFlag.AlignLeft,
                         "Solver confidence over time (internal — not measured error)")

        # Data series
        for label, series in self._series.items():
            if len(series) < 2:
                continue
            color = QColor(self._color_map[label])
            points = list(series)
            n = len(points)
            painter.setPen(QPen(color, 2))
            for i in range(1, n):
                x1 = m + int((i - 1) / max(n - 1, 1) * cw)
                x2 = m + int(i / max(n - 1, 1) * cw)
                y1 = h - m + 10 - int(points[i - 1] / max(y_max, 0.01) * ch)
                y2 = h - m + 10 - int(points[i] / max(y_max, 0.01) * ch)
                painter.drawLine(x1, y1, x2, y2)

            # Legend
            painter.setFont(QFont("Helvetica", 9))
            last_y = h - m + 10 - int(points[-1] / max(y_max, 0.01) * ch)
            painter.drawText(QPointF(m + cw + 4, last_y + 4), label)

        painter.end()


class ABBenchmark(QWidget):
    """Benchmark tab with explanation, comparison table, and accuracy chart."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header with explanation
        header = QLabel(
            "<b>Solver Confidence Dashboard</b><br>"
            "<span style='color:#9ca3af;font-size:11px;'>"
            "This tracks the solver's <b>internal confidence</b> over time — "
            "<i>not</i> measured error against a known position (the app has no "
            "ground truth). Each row shows the latest snapshot: active devices "
            "and anchors, the estimated position, and the <b>uncertainty</b> "
            "(the solver's own residual/spread; lower = more self-consistent). "
            "Treat it as a stability indicator, not verified accuracy."
            "</span>"
        )
        header.setWordWrap(True)
        header.setStyleSheet("padding: 4px; background: #161b22;"
                             "border: 1px solid #21262d; border-radius: 6px;")
        layout.addWidget(header)

        # Controls
        ctrl_row = QHBoxLayout()
        clear_btn = QPushButton("Clear History")
        clear_btn.setFixedHeight(26)
        clear_btn.setStyleSheet(
            "QPushButton{background:#21262d;color:#e2e8f0;border:1px solid #334155;"
            "border-radius:4px;padding:0 10px;font-size:11px;}"
            "QPushButton:hover{background:#334155;}"
        )
        clear_btn.clicked.connect(self._clear)
        ctrl_row.addWidget(clear_btn)
        ctrl_row.addStretch()

        self._sample_label = QLabel("Samples: 0")
        self._sample_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        ctrl_row.addWidget(self._sample_label)
        layout.addLayout(ctrl_row)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Table with clear column headers
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "Configuration",
            "Visible Devices",
            "Active Anchors",
            "Position X (m)",
            "Position Y (m)",
            "Uncertainty (m)",
            "Last Updated",
        ])
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._table.setStyleSheet(
            "QTableWidget{background:#161b22;color:#e2e8f0;gridline-color:#21262d;"
            "font-size:12px;}"
            "QHeaderView::section{background:#21262d;color:#93c5fd;padding:6px;"
            "border:1px solid #334155;font-weight:bold;font-size:11px;}"
            "QTableWidget::item{padding:4px;}"
        )
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(self._table.styleSheet() +
            "QTableWidget{alternate-background-color:#1c2128;}")
        splitter.addWidget(self._table)

        self._chart = _AccuracyChart()
        splitter.addWidget(self._chart)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter, stretch=1)

        self._rows: Dict[str, int] = {}
        self._sample_count = 0

    def _clear(self):
        self._table.setRowCount(0)
        self._rows.clear()
        self._chart.clear()
        self._sample_count = 0
        self._sample_label.setText("Samples: 0")

    def record(self, config_label: str, result: PositionResult):
        n_dev = len(result.devices)
        n_anc = len(result.anchors_ui)
        pos_x = f"{result.position[0]:.2f}" if result.position else "—"
        pos_y = f"{result.position[1]:.2f}" if result.position else "—"

        if result.uncertainty_radius is not None:
            # Colour (set below) conveys tight/medium/loose; no ✅ "verified"
            # framing — this is confidence, not measured accuracy.
            unc = f"{result.uncertainty_radius:.3f}"
        else:
            unc = "—"

        ts = time.strftime("%H:%M:%S")

        if config_label not in self._rows:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._rows[config_label] = row
        row = self._rows[config_label]

        vals = [config_label, str(n_dev), str(n_anc), pos_x, pos_y, unc, ts]
        for col, v in enumerate(vals):
            item = QTableWidgetItem(v)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            if col == 5 and result.uncertainty_radius is not None:
                if result.uncertainty_radius < 0.5:
                    item.setForeground(QColor("#22c55e"))
                elif result.uncertainty_radius < 1.5:
                    item.setForeground(QColor("#f59e0b"))
                else:
                    item.setForeground(QColor("#ef4444"))
            self._table.setItem(row, col, item)

        self._sample_count += 1
        self._sample_label.setText(f"Samples: {self._sample_count}")

        if result.uncertainty_radius is not None:
            self._chart.add_point(config_label, result.uncertainty_radius)
