from __future__ import annotations

import asyncio
import math
import socket
from typing import Dict, List, Optional

from PyQt6.QtCore import QTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.interfaces import ISignalScanner
from core.models import Anchor, AnchorMeasurement, EstimationMode, NodeReport, PositionResult, SignalReading, SignalType, display_name
from services.anchor_store import AnchorStore
from services.auto_layout_service import AutoLayoutService
from services.distance_compare_service import DistanceCompareService
from services.positioning_service import PositioningService
from ui.ab_benchmark import ABBenchmark
from ui.ab_split import ABSplitView
from ui.distance_ab_view import DistanceABView
from ui.antenna_view import AntennaView
from ui.antenna_net_panel import AntennaNetPanel
from ui.camera_view import CameraView
from ui.charts import RSSIChart
from ui.combination_view import CombinationView
from ui.device_panel import DevicePanel
from ui.distance_radar import DistanceRadar
from ui.room_canvas import RoomCanvas
from ui.auto_layout_view import AutoLayoutView
from ui.rtls_targets_view import RtlsTargetsView

_DEFAULT_TX_POWER = -59.0
_FSPL_1M = 41  # free-space path loss at 1m for BLE 2.4 GHz


def _auto_tx_power(reading: SignalReading) -> float:
    if reading.tx_power_adv is not None:
        rssi_at_1m = float(reading.tx_power_adv) - _FSPL_1M
        return rssi_at_1m
    return _DEFAULT_TX_POWER


class MainWindow(QMainWindow):
    UPDATE_INTERVAL = 1.0
    ACTIVE_WINDOW = 15.0

    def __init__(
        self,
        scanner: ISignalScanner,
        anchors: AnchorStore,
        positioning: PositioningService,
        multireceiver=None,
        local_antenna=None,
        manager_server=None,
        combination_service=None,
    ):
        super().__init__()
        from core.version import get_version
        self.setWindowTitle(f"BLE Locator — Indoor Positioning System  (v{get_version()})")
        self.resize(1200, 750)

        self._scanner = scanner
        self._anchors = anchors
        self._positioning = positioning
        self._timer: Optional[QTimer] = None
        self._tick_count = 0
        self._last_result: Optional[PositionResult] = None
        self._measuring = False
        self._selected_device: Optional[str] = None
        # device_id -> consecutive fresh advertisements (persistence filter)
        self._seen_streak: Dict[str, int] = {}
        self._seen_last_ts: Dict[str, float] = {}

        # Multi-antenna RTLS (optional — present only in manager mode)
        self._multireceiver = multireceiver
        self._local_antenna = local_antenna
        self._local_hostname = socket.gethostname().replace(".local", "")
        self._manager_server = manager_server
        self._combination_service = combination_service
        self._auto_layout_service = None

        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._canvas = RoomCanvas()
        self._radar = DistanceRadar()
        self._ab_split = ABSplitView(self._anchors)
        self._antenna = AntennaView()
        self._benchmark = ABBenchmark()
        self._camera_view = CameraView(self._anchors)
        self._dist_compare = DistanceCompareService(self._anchors)
        self._dist_ab = DistanceABView()

        # Algorithm mode selector
        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 4)
        mode_label = QLabel("Algorithm:")
        mode_label.setStyleSheet("color:#9ca3af;font-size:12px;")
        self._mode_combo = QComboBox()
        self._mode_combo.addItems([
            "Trilateration (Least Squares)",
            "Particle Filter",
            "Fusion (T + PF)",
            "Ensemble (all four)",
            "Weighted Centroid",
        ])
        self._mode_combo.setStyleSheet(
            "QComboBox{background:#1f2937;color:#e2e8f0;border:1px solid #334155;"
            "border-radius:6px;padding:3px 8px;font-size:12px;}"
            "QComboBox::drop-down{border:none;}"
        )
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(mode_label)
        mode_row.addWidget(self._mode_combo)

        # View mode toggle — starts with Mac only, adds iPhone/Combined when connected
        mode_row.addSpacing(20)
        view_label = QLabel("View:")
        view_label.setStyleSheet("color:#9ca3af;font-size:12px;")
        self._view_combo = QComboBox()
        self._view_combo.addItems(["Mac only"])
        self._view_combo.setStyleSheet(
            "QComboBox{background:#1f2937;color:#e2e8f0;border:1px solid #334155;"
            "border-radius:6px;padding:3px 8px;font-size:12px;}"
            "QComboBox::drop-down{border:none;}"
        )
        mode_row.addWidget(view_label)
        mode_row.addWidget(self._view_combo)
        self._iphone_view_added = False

        mode_row.addSpacing(20)
        self._antenna_status_label = QLabel("📡 No antennas")
        self._antenna_status_label.setStyleSheet(
            "color:#ef4444;font-size:12px;font-weight:bold;"
            "padding:2px 8px;background:#1c1c1c;border:1px solid #334155;border-radius:6px;"
        )
        mode_row.addWidget(self._antenna_status_label)

        mode_row.addSpacing(10)
        self._measure_btn = QPushButton("▶ Start Measurement")
        self._measure_btn.clicked.connect(self._on_toggle_measure)
        mode_row.addWidget(self._measure_btn)

        reset_btn = QPushButton("Reset")
        reset_btn.setStyleSheet(
            "QPushButton{background:#7f1d1d;color:#fca5a5;border:1px solid #991b1b;"
            "border-radius:6px;padding:3px 10px;font-size:11px;font-weight:bold;}"
            "QPushButton:hover{background:#991b1b;}"
        )
        reset_btn.clicked.connect(self._on_reset_measurements)
        mode_row.addWidget(reset_btn)
        self._refresh_measure_btn()

        mode_row.addStretch()
        left_layout.addLayout(mode_row)

        caption = QLabel(
            "ℹ️ One Mac antenna measures distance (how far) reliably. The 2-D "
            "X/Y on the map is inferred from anchor geometry — trust the "
            "distance more than the exact dot."
        )
        caption.setWordWrap(True)
        caption.setStyleSheet("color:#94a3b8;font-size:11px;padding:1px 4px 3px 4px;")
        left_layout.addWidget(caption)

        self._views = QTabWidget()
        self._views.addTab(self._canvas, "Position Map")
        self._views.addTab(self._radar, "Distance Radar")
        self._views.addTab(self._dist_ab, "Distance A/B")
        self._views.addTab(self._ab_split, "A/B Compare")
        self._views.addTab(self._antenna, "Signal Quality")
        self._views.addTab(self._camera_view, "Camera AR")
        self._views.addTab(self._benchmark, "Benchmark")

        # Multi-antenna internals (manager mode only) — no extra tabs
        self._rtls_view = None
        self._antenna_net = None
        self._combo_view = None
        self._auto_layout_view = None
        if self._multireceiver is not None:
            self._rtls_view = RtlsTargetsView()
            self._antenna_net = AntennaNetPanel()
            self._antenna_net.layout_changed.connect(self._on_antenna_layout_changed)
            self._auto_layout_view = AutoLayoutView()
            self._auto_layout_view.hints_changed.connect(self._on_hints_changed)
            if self._combination_service is not None:
                self._combo_view = CombinationView()

        self._canvas.device_dropped.connect(self._on_device_dropped)
        self._canvas.anchor_reaimed.connect(self._on_anchor_reaimed)
        self._view_combo.currentIndexChanged.connect(self._on_view_changed)
        self._view_mode = 0  # 0=Mac, 1=iPhone, 2=Combined
        self._radar.anchor_placed.connect(self._on_radar_anchor_placed)
        self._radar.device_selected.connect(self._on_device_selected)
        self._dist_ab.device_selected.connect(self._on_device_selected)
        left_layout.addWidget(self._views, stretch=3)

        chart_label = QLabel("RSSI over Time")
        chart_label.setStyleSheet("color: #9ca3af; padding: 2px 4px;")
        left_layout.addWidget(chart_label)

        self._chart = RSSIChart()
        left_layout.addWidget(self._chart, stretch=1)

        self._panel = DevicePanel(self._anchors)
        self._panel.anchor_changed.connect(self._on_anchor_changed)
        self._panel.device_selected.connect(self._on_device_selected)
        self._panel.filter_changed.connect(self._on_filter_changed)
        self._panel.setMinimumWidth(260)

        splitter = QSplitter()
        splitter.addWidget(left_widget)
        splitter.addWidget(self._panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([820, 360])
        root.addWidget(splitter)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Starting scan…")

    def start_scanning(self):
        asyncio.ensure_future(self._scanner.start())
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(int(self.UPDATE_INTERVAL * 1000))

    def stop_scanning(self):
        if self._timer is not None:
            self._timer.stop()
        asyncio.ensure_future(self._scanner.stop())

    def _tick(self):
        # view_mode: 0=Mac only, 1=iPhone only, 2=Combined
        use_mac = self._view_mode != 1
        use_iphone = self._view_mode != 0

        readings = {}
        if use_mac:
            readings = self._scanner.get_active(self.ACTIVE_WINDOW)
            for device_id in self._anchors.all():
                if device_id not in readings:
                    r = self._scanner.get_reading(device_id)
                    if r is not None:
                        readings[device_id] = r

        if self._view_mode == 1 and self._multireceiver is not None:
            readings = self._iphone_readings()

        # Persistence tracking — phantoms from address rotation appear briefly.
        self._update_seen_streaks(readings)

        # Per-device distances are always smoothed by the full filter chain
        # (continuous). The 2-D position fix only runs while measuring.
        extra = None
        if self._measuring and use_iphone and self._multireceiver is not None:
            extra = self._multireceiver.get_self_measurements(
                self._local_hostname) or None

            if use_mac and extra:
                anchor_ids = set(self._anchors.all().keys())
                iphone_dists = self._multireceiver.get_anchor_observations_from_remotes(
                    anchor_ids, self._local_hostname)
                corrections = self._cross_validate(readings, iphone_dists, extra[0].distance)
                if corrections:
                    extra.extend(corrections)

        result = self._positioning.update(
            readings, self._canvas.room_w, self._canvas.room_h,
            extra_measurements=extra, compute_position=self._measuring)

        self._last_result = result
        self._apply(result, readings)

        if self._multireceiver is not None:
            self._update_rtls()

        self._tick_count += 1

    _TRIANGLE_TOLERANCE = 1.12
    _MIN_CORRECTION_DELTA = 0.25

    def _cross_validate(self, readings, iphone_dists, mac_iphone_dist):
        """Use triangle inequality to bound Mac-anchor distances.

        When Mac's BLE distance to an anchor exceeds the triangle upper bound
        (mac_iphone_dist + iphone_anchor_dist), add a corrective measurement
        clamped to the bound so the solver pulls toward a consistent estimate.
        """
        if not iphone_dists:
            return []
        from engine.distance import compute_distance
        corrections = []
        for device_id, d_iphone in iphone_dists.items():
            anchor = self._anchors.get(device_id)
            if anchor is None:
                continue
            reading = readings.get(device_id)
            if reading is None:
                continue
            tx = anchor.tx_power or PositioningService.DEFAULT_TX_POWER
            n = anchor.n or PositioningService.DEFAULT_PATH_LOSS_N
            filtered = self._positioning._filter_bank.apply(device_id, reading.rssi)
            d_mac = compute_distance(filtered, tx, n)
            upper = mac_iphone_dist + d_iphone
            if (d_mac > upper * self._TRIANGLE_TOLERANCE
                    and (d_mac - upper) > self._MIN_CORRECTION_DELTA):
                corrections.append(AnchorMeasurement(
                    x=anchor.x, y=anchor.y, distance=upper))
        return corrections

    def _update_rtls(self):
        """Feed the local antenna in, then refresh the multi-antenna views."""
        room_w, room_h = self._canvas.room_w, self._canvas.room_h

        # 1) submit the local computer's own scan as antenna #1
        if self._local_antenna is not None:
            if self._antenna_net is not None:
                pos = self._antenna_net.positions().get(self._local_antenna.node_id)
                if pos is not None:
                    self._local_antenna.set_position(*pos)
            self._multireceiver.submit(self._local_antenna.report(self.ACTIVE_WINDOW))

        # 2) apply manager-side antenna positions edited in the panel
        included = None
        if self._antenna_net is not None:
            for nid, (x, y) in self._antenna_net.positions().items():
                if self._manager_server is not None:
                    self._manager_server.set_node_position(nid, x, y)
            included = self._antenna_net.included_nodes() or None

        # 3) build the antenna roster for the panel
        roster = self._antenna_roster()
        if self._antenna_net is not None:
            self._antenna_net.sync(roster)

        # 4) compute fused targets
        per_target = self._multireceiver.collect_target_fixes(only_nodes=included)
        targets = self._multireceiver.locate_targets(
            room_w, room_h, only_nodes=included)

        if self._rtls_view is not None:
            antennas_ui = {nid: (info["x"], info["y"], info["name"])
                           for nid, info in roster.items()
                           if included is None or nid in included}
            self._rtls_view.update_view(room_w, room_h, antennas_ui,
                                        per_target, targets)

        # 5) combination comparison for the selected target
        if self._combo_view is not None and self._combination_service is not None:
            self._combo_view.set_targets(self._combination_service.list_targets())
            tid = self._combo_view.selected_target
            if tid:
                res = self._combination_service.compare(tid, room_w, room_h)
                self._combo_view.set_results(res)

        # 6) update antenna connection status + view toggle
        if self._manager_server is not None:
            connected = self._manager_server.connected_nodes()
            n_ant = len(connected)
            if n_ant > 0:
                names = ", ".join(n.name for n in connected.values())
                self._antenna_status_label.setText(f"📡 {n_ant} antenna: {names}")
                self._antenna_status_label.setStyleSheet(
                    "color:#22c55e;font-size:12px;font-weight:bold;"
                    "padding:2px 8px;background:#0f2918;border:1px solid #22c55e;border-radius:6px;"
                )
                if not self._iphone_view_added:
                    self._view_combo.addItems(["iPhone only", "Combined"])
                    self._iphone_view_added = True
            else:
                self._antenna_status_label.setText("📡 No antennas")
                self._antenna_status_label.setStyleSheet(
                    "color:#ef4444;font-size:12px;font-weight:bold;"
                    "padding:2px 8px;background:#1c1c1c;border:1px solid #334155;border-radius:6px;"
                )
                if self._iphone_view_added:
                    self._view_combo.setCurrentIndex(0)
                    while self._view_combo.count() > 1:
                        self._view_combo.removeItem(1)
                    self._iphone_view_added = False

    def _antenna_roster(self) -> dict:
        """{node_id: {name, is_local, x, y, count, last_seen}} for all antennas."""
        import time as _t
        roster = {}
        now = _t.time()
        # local
        if self._local_antenna is not None:
            la = self._local_antenna
            rep = la.report(self.ACTIVE_WINDOW)
            roster[la.node_id] = {
                "name": la.name, "is_local": True, "x": la.x, "y": la.y,
                "count": len(rep.observations), "last_seen": now}
        # remote (from the server)
        if self._manager_server is not None:
            for nid, node in self._manager_server.connected_nodes().items():
                last = self._multireceiver._nodes.get(nid)
                count = len(last.observations) if last else 0
                roster[nid] = {
                    "name": node.name, "is_local": False,
                    "x": node.x, "y": node.y,
                    "count": count, "last_seen": node.last_seen}
        return roster

    def _iphone_readings(self) -> Dict[str, SignalReading]:
        import time as _t
        now = _t.time()
        readings: Dict[str, SignalReading] = {}
        if self._manager_server is None:
            return readings
        for nid in self._manager_server.connected_nodes():
            node = self._multireceiver._nodes.get(nid)
            if node is None:
                continue
            for obs in node.observations:
                if now - obs.timestamp > self.ACTIVE_WINDOW:
                    continue
                readings[obs.target_id] = SignalReading(
                    device_id=obs.target_id,
                    name=obs.name or "",
                    rssi=obs.rssi,
                    signal_type=obs.signal_type,
                    timestamp=obs.timestamp,
                    distance=obs.distance,
                    tx_power_adv=obs.tx_power_adv if hasattr(obs, 'tx_power_adv') else None,
                )
        return readings

    @pyqtSlot(str, float, float)
    def _on_device_dropped(self, device_id: str, dir_x: float, dir_y: float):
        """A device was dragged from the list and dropped on the Position Map.

        dir_x, dir_y are screen-relative direction components:
          positive dir_x = right, positive dir_y = up in room.
        We place the anchor at that direction + BLE-computed distance from centre.
        """
        readings = self._scanner.get_active(self.ACTIVE_WINDOW)
        reading = readings.get(device_id) or self._scanner.get_reading(device_id)
        if reading is None:
            print(f"[DROP] no reading for {device_id}")
            return

        from engine.distance import rssi_to_distance
        existing = self._anchors.get(device_id)
        tx = existing.tx_power if existing else _auto_tx_power(reading)
        n = existing.n if existing else self._positioning.DEFAULT_PATH_LOSS_N
        dist = rssi_to_distance(reading.rssi, tx, n)

        length = math.sqrt(dir_x * dir_x + dir_y * dir_y)
        if length < 1.0:
            dir_x, dir_y = 1.0, 0.0
            length = 1.0

        cx = self._canvas.room_w / 2.0
        cy = self._canvas.room_h / 2.0
        ax = cx + (dir_x / length) * dist
        ay = cy + (dir_y / length) * dist
        ax = max(0.05, min(self._canvas.room_w - 0.05, ax))
        ay = max(0.05, min(self._canvas.room_h - 0.05, ay))

        name = display_name(device_id, reading.name)
        print(f"[DROP] {name}: screen_dir=({dir_x:+.0f},{dir_y:+.0f}) "
              f"rssi={reading.rssi} tx={tx:.0f} dist={dist:.1f}m -> anchor=({ax:.1f},{ay:.1f}) "
              f"room=({self._canvas.room_w},{self._canvas.room_h})")

        self._anchors.set(Anchor(
            device_id=device_id, name=name,
            tx_power=tx, n=n, x=ax, y=ay,
        ))
        self._panel.anchor_changed.emit()
        self._panel.update_readings(self._scanner.get_active(self.ACTIVE_WINDOW))

    @pyqtSlot(str, float, float)
    def _on_anchor_reaimed(self, device_id: str, dir_x: float, dir_y: float):
        """Re-aim an existing anchor — keep BLE distance, change direction."""
        existing = self._anchors.get(device_id)
        if existing is None:
            return
        readings = self._scanner.get_active(self.ACTIVE_WINDOW)
        reading = readings.get(device_id) or self._scanner.get_reading(device_id)
        if reading is None:
            return

        from engine.distance import rssi_to_distance
        dist = rssi_to_distance(reading.rssi, existing.tx_power, existing.n)

        length = math.sqrt(dir_x * dir_x + dir_y * dir_y)
        if length < 1.0:
            return
        cx = self._canvas.room_w / 2.0
        cy = self._canvas.room_h / 2.0
        ax = cx + (dir_x / length) * dist
        ay = cy + (dir_y / length) * dist
        ax = max(0.05, min(self._canvas.room_w - 0.05, ax))
        ay = max(0.05, min(self._canvas.room_h - 0.05, ay))

        self._anchors.set(Anchor(
            device_id=device_id, name=existing.name,
            tx_power=existing.tx_power, n=existing.n, x=ax, y=ay,
        ))

    @pyqtSlot(int)
    def _on_view_changed(self, index: int):
        self._view_mode = index

    @pyqtSlot()
    def _on_antenna_layout_changed(self):
        if self._multireceiver is not None:
            self._multireceiver.recalibrate()

    @pyqtSlot()
    def _on_hints_changed(self):
        if self._auto_layout_view is None or self._auto_layout_service is None:
            return
        hints = self._auto_layout_view.get_hints()
        self._auto_layout_service._hints.clear()
        for did, direction in hints.items():
            self._auto_layout_service.set_hint(did, direction)

    def _update_auto_layout(self, room_w: float, room_h: float):
        if self._auto_layout_view is None:
            return
        import time as _t
        from engine.distance import rssi_to_distance

        if self._auto_layout_service is None:
            self._auto_layout_service = AutoLayoutService()

        mac_id = self._local_hostname
        now = _t.time()

        # Build Mac distances from current scan
        mac_distances: dict = {}
        if self._local_antenna is not None:
            rep = self._local_antenna.report(self.ACTIVE_WINDOW)
            for obs in rep.observations:
                if now - obs.timestamp > 10:
                    continue
                dist = rssi_to_distance(float(obs.rssi), rep.tx_power, rep.n)
                mac_distances[obs.target_id] = (dist, obs.name)

        # Build iPhone distances from remote antenna reports
        iphone_id = None
        iphone_distances: dict = {}
        remote_reports: list = []
        if self._manager_server is not None:
            for nid, node in self._manager_server.connected_nodes().items():
                remote_node = self._multireceiver._nodes.get(nid)
                if remote_node is None:
                    continue
                iphone_id = nid
                for obs in remote_node.observations:
                    if now - obs.timestamp > 10:
                        continue
                    dist = rssi_to_distance(
                        float(obs.rssi), remote_node.tx_power, remote_node.n)
                    iphone_distances[obs.target_id] = (dist, obs.name)
                remote_reports.append(remote_node)

        # Solve combined auto-layout
        local_report = None
        if self._local_antenna is not None:
            local_report = self._local_antenna.report(self.ACTIVE_WINDOW)
        combined_positions = None
        if local_report is not None:
            hints = self._auto_layout_view.get_hints()
            for did, direction in hints.items():
                self._auto_layout_service.set_hint(did, direction)
            result = self._auto_layout_service.solve(
                mac_id, local_report, remote_reports, room_w, room_h)
            if result is not None:
                combined_positions = result.positions

        device_names = dict(self._auto_layout_service.device_names)
        device_names[mac_id] = "Mac"

        self._auto_layout_view.update_view(
            room_w, room_h, mac_id,
            mac_distances, iphone_id, iphone_distances,
            combined_positions, device_names)

    def _apply(self, result: PositionResult, readings: Dict[str, SignalReading]):
        self._canvas.set_anchors(result.anchors_ui)
        self._canvas.set_distances(result.distances)
        self._canvas.set_uncertainty(result.uncertainty_ellipse)
        self._canvas.set_particles(result.particles, result.particle_weights)
        if result.position is not None:
            self._canvas.set_position(*result.position)
        else:
            self._canvas.clear_position()

        visible_devices = [d for d in result.devices
                           if self._is_visible(d.device_id, d.raw_rssi)]
        self._radar.set_selected(self._selected_device)
        self._radar.set_devices(visible_devices)
        self._ab_split.set_readings(readings, self._canvas.room_w, self._canvas.room_h)
        self._antenna.set_devices(result.devices)
        self._camera_view.set_result(
            result.position, result.anchors_ui, result.distances,
            self._canvas.room_w, self._canvas.room_h,
            devices=result.devices)

        if self._measuring and self._tick_count % 3 == 0:
            n_ble = sum(1 for d in result.devices if d.signal_type == SignalType.BLE)
            n_wifi = sum(1 for d in result.devices if d.signal_type == SignalType.WIFI)
            view_names = ["Mac", "iPhone", "Combined"]
            view = view_names[self._view_mode] if self._view_mode < len(view_names) else "Mac"
            label = f"{view} ({n_ble} BLE + {n_wifi} WiFi)"
            self._benchmark.record(label, result)

        for d in result.devices:
            if d.is_anchor:
                self._chart.add_reading(d.device_id, d.raw_rssi, d.filtered_rssi, d.name)

        all_dists = {d.device_id: d.distance for d in result.devices
                     if d.distance is not None}
        self._panel.set_distances(all_dists)
        self._panel.set_nlos_levels(self._positioning.nlos_levels())
        visible = self._visible_readings(readings)
        self._panel.set_hidden_count(len(readings) - len(visible))
        self._panel.update_readings(visible)

        # Distance A/B — Kalman-only vs full chain, fed live every tick.
        ab_rows = self._dist_compare.update(
            visible, self._canvas.room_w, self._canvas.room_h)
        self._dist_ab.set_rows(ab_rows, self._selected_device)

        status = result.status
        if self._manager_server is not None:
            n_ant = len(self._manager_server.connected_nodes())
            if n_ant:
                names = ", ".join(n.name for n in
                                 self._manager_server.connected_nodes().values())
                status = f"📡 {n_ant} antenna{'s' if n_ant > 1 else ''} ({names})  |  {status}"
        self._status.showMessage(status)

    @pyqtSlot(int)
    def _on_mode_changed(self, index: int):
        modes = [
            EstimationMode.TRILATERATION,
            EstimationMode.PARTICLE,
            EstimationMode.FUSION,
            EstimationMode.ENSEMBLE,
            EstimationMode.CENTROID,
        ]
        self._positioning.mode = modes[index]
        # Reset smoothed position so the new algorithm starts fresh
        self._positioning._pos_smooth = None

    @pyqtSlot()
    def _on_reset_measurements(self):
        self._positioning.reset()
        self._dist_compare.reset()
        self._measuring = False
        self._last_result = None
        self._tick_count = 0
        self._seen_streak.clear()
        self._selected_device = None
        self._radar.set_selected(None)
        self._panel.set_selected(None)
        self._canvas.clear_position()
        self._chart.clear_history()
        self._refresh_measure_btn()
        self._status.showMessage("Reset — press Start to begin a fresh measurement.")

    # ── measurement session ─────────────────────────────────────────────
    MIN_STREAK = 2  # fresh advertisements before a device is shown (phantom guard)

    @pyqtSlot()
    def _on_toggle_measure(self):
        if self._measuring:
            self._measuring = False
            self._status.showMessage("Measurement stopped — showing frozen result.")
        else:
            # Fresh collection every time Start is pressed.
            self._positioning.reset()
            self._dist_compare.reset()
            self._last_result = None
            self._canvas.clear_position()
            self._chart.clear_history()
            self._measuring = True
            self._status.showMessage("Measuring… stay still for a few seconds.")
        self._refresh_measure_btn()

    def _refresh_measure_btn(self):
        if self._measuring:
            self._measure_btn.setText("■ Stop")
            self._measure_btn.setStyleSheet(
                "QPushButton{background:#7f1d1d;color:#fecaca;border:1px solid #b91c1c;"
                "border-radius:6px;padding:3px 12px;font-size:12px;font-weight:bold;}"
                "QPushButton:hover{background:#991b1b;}"
            )
        else:
            self._measure_btn.setText("▶ Start Measurement")
            self._measure_btn.setStyleSheet(
                "QPushButton{background:#14532d;color:#bbf7d0;border:1px solid #16a34a;"
                "border-radius:6px;padding:3px 12px;font-size:12px;font-weight:bold;}"
                "QPushButton:hover{background:#166534;}"
            )

    # ── device visibility (persistence + RSSI threshold + type filter) ──
    def _update_seen_streaks(self, readings: Dict[str, SignalReading]):
        """Count consecutive fresh advertisements per device; drop the gone ones."""
        for did, r in readings.items():
            prev = self._seen_last_ts.get(did)
            if prev is None or r.timestamp > prev:
                self._seen_streak[did] = self._seen_streak.get(did, 0) + 1
                self._seen_last_ts[did] = r.timestamp
        gone = [d for d in self._seen_streak if d not in readings]
        for d in gone:
            self._seen_streak.pop(d, None)
            self._seen_last_ts.pop(d, None)

    def _is_visible(self, device_id: str, rssi: float) -> bool:
        # Anchors and the selected device are always shown.
        if self._anchors.is_anchor(device_id) or device_id == self._selected_device:
            return True
        if rssi < self._panel.rssi_threshold():
            return False
        if self._seen_streak.get(device_id, 0) < self.MIN_STREAK:
            return False
        return True

    def _visible_readings(self, readings: Dict[str, SignalReading]
                          ) -> Dict[str, SignalReading]:
        return {did: r for did, r in readings.items()
                if self._is_visible(did, r.rssi)}

    @pyqtSlot(str)
    def _on_device_selected(self, device_id: str):
        self._selected_device = device_id or None
        self._radar.set_selected(self._selected_device)
        self._panel.set_selected(self._selected_device)

    @pyqtSlot()
    def _on_filter_changed(self):
        # Re-render immediately so the slider feels responsive while idle.
        if self._last_result is not None:
            self._apply(self._last_result,
                        self._scanner.get_active(self.ACTIVE_WINDOW))
        else:
            self._panel.update_readings(
                self._visible_readings(self._scanner.get_active(self.ACTIVE_WINDOW)))

    def _on_anchor_changed(self):
        anchors_ui = {did: (a.x, a.y, a.name)
                      for did, a in self._anchors.all().items()}
        self._canvas.set_anchors(anchors_ui)
        self._chart.clear_history()

    @pyqtSlot(str, float, float)
    def _on_radar_anchor_placed(self, device_id: str, angle: float, distance: float):
        # Prefer RSSI-derived distance over the drag distance — user's drag only
        # supplies the direction (angle); the signal strength determines how far.
        rssi_dist = (
            self._last_result.distances.get(device_id)
            if self._last_result and self._last_result.distances
            else None
        )
        d = rssi_dist if rssi_dist is not None else distance

        # Place anchor relative to current position estimate if available,
        # otherwise fall back to room centre.
        if self._last_result and self._last_result.position:
            cx, cy = self._last_result.position
        else:
            cx = self._canvas.room_w / 2.0
            cy = self._canvas.room_h / 2.0

        x = min(max(cx + d * math.cos(angle), 0.0), self._canvas.room_w)
        y = min(max(cy + d * math.sin(angle), 0.0), self._canvas.room_h)

        existing = self._anchors.get(device_id)
        reading = self._scanner.get_reading(device_id)
        if existing:
            name = existing.name
        elif reading:
            name = display_name(device_id, reading.name)
        else:
            name = "Anchor"
        tx = existing.tx_power if existing else _auto_tx_power(reading)
        n = existing.n if existing else PositioningService.DEFAULT_PATH_LOSS_N
        self._anchors.set(Anchor(
            device_id=device_id, name=name, tx_power=tx, n=n, x=x, y=y))
        self._on_anchor_changed()

    def closeEvent(self, event):
        self._camera_view.stop()
        self.stop_scanning()
        super().closeEvent(event)
