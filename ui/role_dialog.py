"""Launch-time role picker — Manager or Antenna?

One app, two roles. The manager shows the full UI + fuses data. An antenna
just scans and streams to a manager. Shown at startup unless a role was
forced on the command line (--antenna / --manager).
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass
class RoleChoice:
    role: str                       # "manager" or "antenna"
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    manager_host: str = ""


class RoleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BLE Locator — choose role")
        self.setMinimumWidth(380)
        self._choice: Optional[RoleChoice] = None

        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        title = QLabel("What should this computer be?")
        title.setStyleSheet("font-size:15px;font-weight:bold;")
        outer.addWidget(title)

        # Manager button
        mgr_btn = QPushButton("🖥️  Be the Manager\nShow the map, fuse all antennas")
        mgr_btn.setStyleSheet(
            "QPushButton{background:#1f6feb;color:white;border:none;"
            "border-radius:8px;padding:12px;font-size:13px;text-align:left;}"
            "QPushButton:hover{background:#388bfd;}")
        mgr_btn.clicked.connect(self._choose_manager)
        outer.addWidget(mgr_btn)

        # Antenna section
        ant_btn = QPushButton("📡  Be an Antenna\nJust scan and feed a manager")
        ant_btn.setStyleSheet(
            "QPushButton{background:#21262d;color:#e2e8f0;border:1px solid #334155;"
            "border-radius:8px;padding:12px;font-size:13px;text-align:left;}"
            "QPushButton:hover{background:#2d333b;}")
        ant_btn.clicked.connect(self._toggle_antenna_form)
        outer.addWidget(ant_btn)

        # Antenna details (hidden until "Be an Antenna" is clicked)
        self._form_box = QWidget()
        form = QFormLayout(self._form_box)
        form.setContentsMargins(8, 4, 8, 4)

        self._name = QLineEdit(socket.gethostname())
        form.addRow("Name:", self._name)

        self._x = QDoubleSpinBox(); self._x.setRange(0, 100); self._x.setDecimals(2)
        self._y = QDoubleSpinBox(); self._y.setRange(0, 100); self._y.setDecimals(2)
        xy = QHBoxLayout()
        xy_w = QWidget(); xy_w.setLayout(xy)
        xy.addWidget(QLabel("x")); xy.addWidget(self._x)
        xy.addWidget(QLabel("y")); xy.addWidget(self._y)
        form.addRow("Position (m):", xy_w)

        self._host = QLineEdit()
        self._host.setPlaceholderText("auto-discover on WiFi (leave blank)")
        form.addRow("Manager IP:", self._host)

        start_btn = QPushButton("Start antenna")
        start_btn.setStyleSheet(
            "QPushButton{background:#238636;color:white;border:none;"
            "border-radius:6px;padding:8px;font-size:12px;}"
            "QPushButton:hover{background:#2ea043;}")
        start_btn.clicked.connect(self._choose_antenna)
        form.addRow(start_btn)

        self._form_box.setVisible(False)
        outer.addWidget(self._form_box)

    def _choose_manager(self):
        self._choice = RoleChoice(role="manager")
        self.accept()

    def _toggle_antenna_form(self):
        self._form_box.setVisible(not self._form_box.isVisible())
        self.adjustSize()

    def _choose_antenna(self):
        self._choice = RoleChoice(
            role="antenna",
            name=self._name.text().strip() or socket.gethostname(),
            x=self._x.value(), y=self._y.value(),
            manager_host=self._host.text().strip(),
        )
        self.accept()

    @property
    def choice(self) -> Optional[RoleChoice]:
        return self._choice
