from __future__ import annotations

import time
from typing import TYPE_CHECKING, Dict, Optional

from PyQt6.QtCore import QMimeData, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDrag
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.models import Anchor, SignalType, display_name

if TYPE_CHECKING:
    from core.models import SignalReading
    from services.anchor_store import AnchorStore


def rssi_color(rssi: int) -> str:
    if rssi >= -60:
        return "#27ae60"
    elif rssi >= -75:
        return "#f39c12"
    else:
        return "#e74c3c"


class AnchorDialog(QDialog):
    def __init__(self, reading: "SignalReading", anchor: Optional[Anchor], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Anchor")
        self.reading = reading

        layout = QFormLayout(self)

        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(0, 100)
        self.x_spin.setSingleStep(0.1)
        self.x_spin.setSuffix(" m")

        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(0, 100)
        self.y_spin.setSingleStep(0.1)
        self.y_spin.setSuffix(" m")

        self.tx_spin = QDoubleSpinBox()
        self.tx_spin.setRange(-120, 0)
        self.tx_spin.setSingleStep(1)
        self.tx_spin.setSuffix(" dBm")

        self.n_spin = QDoubleSpinBox()
        self.n_spin.setRange(1.0, 5.0)
        self.n_spin.setSingleStep(0.1)
        self.n_spin.setDecimals(1)

        if anchor:
            self.x_spin.setValue(anchor.x)
            self.y_spin.setValue(anchor.y)
            self.tx_spin.setValue(anchor.tx_power)
            self.n_spin.setValue(anchor.n)
        else:
            # Default to 1 m in from the (0,0) corner so a first anchor doesn't
            # silently land exactly in the corner.
            self.x_spin.setValue(1.0)
            self.y_spin.setValue(1.0)
            if reading.tx_power_adv is not None:
                self.tx_spin.setValue(reading.tx_power_adv - 41)
            else:
                self.tx_spin.setValue(reading.rssi)
            self.n_spin.setValue(2.5)

        layout.addRow("X position (0,0 = top-left corner):", self.x_spin)
        layout.addRow("Y position:", self.y_spin)
        layout.addRow("Tx Power (RSSI at 1m):", self.tx_spin)
        layout.addRow("Path-loss exponent n:", self.n_spin)

        if reading.tx_power_adv is not None:
            rssi_1m = reading.tx_power_adv - 41
            src = f"Estimated RSSI at 1m: {rssi_1m} dBm (from TX power {reading.tx_power_adv} dBm)"
        else:
            src = "No BLE TX power advertised — using current RSSI as estimate"
        hint = QLabel(src)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addRow(hint)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Set as Anchor")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addRow(btn_row)


SIGNAL_TYPE_ICON = {
    SignalType.BLE: "📶",
    SignalType.WIFI: "📡",
    SignalType.UWB: "🎯",
    SignalType.UNKNOWN: "❓",
}


class DevicePanel(QWidget):
    anchor_changed = pyqtSignal()
    device_selected = pyqtSignal(str)
    filter_changed = pyqtSignal()

    def __init__(self, store: "AnchorStore", parent=None):
        super().__init__(parent)
        self._store = store
        self._readings: Dict[str, "SignalReading"] = {}
        self._items: Dict[str, QListWidgetItem] = {}
        self._distances: Dict[str, float] = {}
        self._nlos_levels: Dict[str, int] = {}
        self._signal_filter: Optional[SignalType] = None
        self._rssi_threshold: int = -95
        self._sort_mode: str = "off"  # "off" | "signal" | "name"
        self._hidden_count: int = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        self._filter_all = QPushButton("All")
        self._filter_ble = QPushButton("BLE")
        self._filter_wifi = QPushButton("WiFi")
        for btn, st in [(self._filter_all, None),
                        (self._filter_ble, SignalType.BLE),
                        (self._filter_wifi, SignalType.WIFI)]:
            btn.setCheckable(True)
            btn.setFixedHeight(24)
            btn.setStyleSheet(
                "QPushButton{background:#21262d;color:#e2e8f0;border:1px solid #334155;"
                "border-radius:4px;padding:0 8px;font-size:11px;}"
                "QPushButton:checked{background:#1f6feb;border-color:#1f6feb;}"
            )
            btn.clicked.connect(lambda checked, s=st: self._set_filter(s))
            filter_row.addWidget(btn)
        self._filter_all.setChecked(True)
        filter_row.addStretch()

        self._sort_combo = QComboBox()
        self._sort_combo.addItems(["Sort: Off", "Sort: Signal", "Sort: A–Z"])
        self._sort_combo.setFixedHeight(24)
        self._sort_combo.setStyleSheet(
            "QComboBox{background:#21262d;color:#e2e8f0;border:1px solid #334155;"
            "border-radius:4px;padding:0 6px;font-size:11px;}"
            "QComboBox::drop-down{border:none;}"
        )
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        filter_row.addWidget(self._sort_combo)
        layout.addLayout(filter_row)

        # RSSI threshold — hide weak/far devices (declutters neighbours + phantoms)
        thr_row = QHBoxLayout()
        self._thr_label = QLabel(f"Hide weaker than {self._rssi_threshold} dBm")
        self._thr_label.setStyleSheet("color:#9ca3af;font-size:11px;")
        self._thr_slider = QSlider(Qt.Orientation.Horizontal)
        self._thr_slider.setRange(-100, -40)
        self._thr_slider.setValue(self._rssi_threshold)
        self._thr_slider.valueChanged.connect(self._on_threshold_changed)
        thr_row.addWidget(self._thr_label)
        thr_row.addWidget(self._thr_slider)
        layout.addLayout(thr_row)

        dev_group = QGroupBox("Nearby Devices")
        dev_layout = QVBoxLayout(dev_group)

        howto = QLabel(
            "<b>Drag</b> a device onto the Position Map in its "
            "rough direction. Distance is auto-computed from signal. "
            "Need <b>3+ anchors</b> for positioning."
        )
        howto.setWordWrap(True)
        howto.setStyleSheet("color: #9ca3af; font-size: 11px; padding: 2px;")
        dev_layout.addWidget(howto)

        self._list = QListWidget()
        self._list.setDragEnabled(True)
        self._list.setDefaultDropAction(Qt.DropAction.CopyAction)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.startDrag = self._start_drag
        dev_layout.addWidget(self._list)

        set_btn = QPushButton("Set as Anchor / Configure")
        set_btn.clicked.connect(self._on_set_anchor)
        dev_layout.addWidget(set_btn)

        remove_btn = QPushButton("Remove Anchor")
        remove_btn.clicked.connect(self._on_remove_anchor)
        dev_layout.addWidget(remove_btn)

        layout.addWidget(dev_group)

        legend = QLabel(
            "<b>Signal strength (RSSI):</b><br>"
            "<span style='color:#27ae60;'>●</span> Green = strong / close&nbsp;&nbsp;"
            "<span style='color:#f39c12;'>●</span> Orange = medium<br>"
            "<span style='color:#e74c3c;'>●</span> Red = weak / far&nbsp;&nbsp;&nbsp;&nbsp;"
            "⚓ = anchor&nbsp;&nbsp;〰️ = echo/unstable<br>"
            "<i>Echo (multipath) makes one device's distance jump — it does "
            "NOT create extra devices. Seeing many devices = address "
            "randomisation + neighbours; raise the slider to hide far ones. "
            "New devices take ~1–2 s to settle before they appear.</i>"
        )
        legend.setWordWrap(True)
        legend.setStyleSheet("font-size: 11px; padding: 4px;"
                             "background:#11161d; border:1px solid #2a2a3e; border-radius:4px;")
        layout.addWidget(legend)

        self._anchor_label = QLabel("Anchors: 0 (need ≥3)")
        self._anchor_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._anchor_label)

    def set_distances(self, distances: Dict[str, float]):
        self._distances = distances

    def set_nlos_levels(self, levels: Dict[str, int]):
        self._nlos_levels = levels

    def rssi_threshold(self) -> int:
        return self._rssi_threshold

    def set_hidden_count(self, n: int):
        self._hidden_count = max(0, n)
        self._refresh_threshold_label()

    def _refresh_threshold_label(self):
        txt = f"Hide weaker than {self._rssi_threshold} dBm"
        if self._hidden_count:
            txt += f"  ·  {self._hidden_count} hidden"
        self._thr_label.setText(txt)

    def _on_threshold_changed(self, value: int):
        self._rssi_threshold = value
        self._refresh_threshold_label()
        self.filter_changed.emit()

    def _on_item_clicked(self, item: QListWidgetItem):
        device_id = item.data(Qt.ItemDataRole.UserRole)
        if device_id:
            self.device_selected.emit(device_id)

    def _on_sort_changed(self, index: int):
        self._sort_mode = ("off", "signal", "name")[index]
        self.update_readings(self._readings)

    def _reorder(self, visible: Dict[str, "SignalReading"]):
        """Reorder the list by the active sort mode (anchors pinned first),
        with an early-out and selection preserved."""
        if self._sort_mode == "signal":
            key = lambda did: (not self._store.is_anchor(did), -visible[did].rssi)
        else:  # name
            key = lambda did: (not self._store.is_anchor(did),
                               display_name(did, visible[did].name,
                                            getattr(visible[did], 'manufacturer', '')).lower())
        ordered = sorted(visible, key=key)

        # Early-out if already in the desired order — avoids per-tick churn.
        current = [self._list.item(i).data(Qt.ItemDataRole.UserRole)
                   for i in range(self._list.count())]
        if current == ordered:
            return

        keep = self._selected_device_id()
        for target, did in enumerate(ordered):
            item = self._items.get(did)
            if item is None:
                continue
            cur = self._list.row(item)
            if cur != target:
                self._list.takeItem(cur)
                self._list.insertItem(target, item)
        if keep and keep in self._items:
            self._list.setCurrentItem(self._items[keep])

    def set_selected(self, device_id: Optional[str]):
        """Highlight a device in the list (selection driven from the radar)."""
        if device_id and device_id in self._items:
            self._list.setCurrentItem(self._items[device_id])

    def _set_filter(self, signal_type: Optional[SignalType]):
        self._signal_filter = signal_type
        self._filter_all.setChecked(signal_type is None)
        self._filter_ble.setChecked(signal_type == SignalType.BLE)
        self._filter_wifi.setChecked(signal_type == SignalType.WIFI)
        self.update_readings(self._readings)

    def update_readings(self, readings: Dict[str, "SignalReading"]):
        self._readings = readings
        now = time.time()

        visible = readings
        if self._signal_filter is not None:
            visible = {did: r for did, r in readings.items()
                       if r.signal_type == self._signal_filter}

        for device_id in list(self._items.keys()):
            if device_id not in visible:
                self._list.takeItem(self._list.row(self._items[device_id]))
                del self._items[device_id]

        for device_id, r in visible.items():
            is_anchor = self._store.is_anchor(device_id)
            stale = is_anchor and (now - r.timestamp > 5.0)
            prefix = "⚓ " if is_anchor else "    "
            suffix = "  ⏳stale" if stale else ""
            if self._nlos_levels.get(device_id, 0) > 0:
                suffix += "  〰️echo"
            sig_icon = SIGNAL_TYPE_ICON.get(r.signal_type, "")
            dist_m = self._distances.get(device_id)
            dist_str = ""
            if dist_m is not None:
                dist_str = f"  ({dist_m:.1f}m)" if dist_m >= 1 else f"  ({dist_m*100:.0f}cm)"
            mfr = getattr(r, 'manufacturer', '')
            dname = display_name(device_id, r.name, mfr)
            label = f"{prefix}{sig_icon} {dname}    {r.rssi} dBm{dist_str}{suffix}"

            item = self._items.get(device_id)
            if item is None:
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, device_id)
                item.setToolTip(f"UUID: {device_id}")
                self._items[device_id] = item
                self._list.addItem(item)
            else:
                if item.text() != label:
                    item.setText(label)
                item.setToolTip(f"UUID: {device_id}")

            color = QColor("#7f8c8d") if stale else QColor(rssi_color(r.rssi))
            item.setForeground(color)
            item.setBackground(QColor("#16241a") if is_anchor else QColor(0, 0, 0, 0))

        if self._sort_mode != "off":
            self._reorder(visible)

        n_anchors = len(self._store.all())
        status = f"Anchors: {n_anchors}"
        if n_anchors < 3:
            status += f" (need {3 - n_anchors} more)"
        self._anchor_label.setText(status)

    def _start_drag(self, supported_actions):
        item = self._list.currentItem()
        if item is None:
            return
        device_id = item.data(Qt.ItemDataRole.UserRole)
        if not device_id:
            return
        drag = QDrag(self._list)
        mime = QMimeData()
        mime.setText(device_id)
        mime.setData("application/x-blelocator-device", device_id.encode())
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

    def _selected_device_id(self) -> Optional[str]:
        item = self._list.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _on_item_double_clicked(self, item: QListWidgetItem):
        self._open_anchor_dialog(item.data(Qt.ItemDataRole.UserRole))

    def _on_set_anchor(self):
        device_id = self._selected_device_id()
        if device_id:
            self._open_anchor_dialog(device_id)

    def _open_anchor_dialog(self, device_id: str):
        if device_id not in self._readings:
            return
        reading = self._readings[device_id]
        dlg = AnchorDialog(reading, self._store.get(device_id), self)
        if dlg.exec():
            self._store.set(Anchor(
                device_id=device_id,
                name=display_name(device_id, reading.name),
                tx_power=dlg.tx_spin.value(),
                n=dlg.n_spin.value(),
                x=dlg.x_spin.value(),
                y=dlg.y_spin.value(),
            ))
            self.anchor_changed.emit()
            self.update_readings(self._readings)

    def _on_remove_anchor(self):
        device_id = self._selected_device_id()
        if device_id and self._store.is_anchor(device_id):
            self._store.remove(device_id)
            self.anchor_changed.emit()
            self.update_readings(self._readings)
