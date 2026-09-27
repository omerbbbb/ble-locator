import sys
import asyncio
import argparse

from PyQt6.QtWidgets import QApplication

try:
    import qasync
    _HAS_QASYNC = True
except ImportError:
    _HAS_QASYNC = False

from core.platform import create_scanners, detect
from engine.trilateration import TrilaterationEstimator
from filtering.filter_bank import FilterBank
from filtering.adaptive_kalman import AdaptiveKalmanFilter
from sensor.multi_scanner import MultiScanner
from services.anchor_store import AnchorStore
from services.positioning_service import PositioningService
from storage.json_repository import JsonCalibrationRepository
from traceability.event_bus import EventBus
from ui.main_window import MainWindow


def _parse_args():
    p = argparse.ArgumentParser(description="BLE Locator indoor positioning")
    p.add_argument("--antenna", action="store_true",
                   help="run as a remote antenna (scan + stream to a manager)")
    p.add_argument("--manager", action="store_true",
                   help="run as the manager (skip the role picker)")
    p.add_argument("--manager-host", default="",
                   help="manager IP (antenna mode; omit to auto-discover)")
    p.add_argument("--port", type=int, default=8077, help="manager port")
    p.add_argument("--name", default="", help="antenna display name")
    p.add_argument("--x", type=float, default=0.0, help="antenna x position (m)")
    p.add_argument("--y", type=float, default=0.0, help="antenna y position (m)")
    return p.parse_known_args()[0]


def main():
    args = _parse_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    from ui.theme import dark_palette
    app.setPalette(dark_palette())

    # --- Choose role: Manager or Antenna ---
    role = "antenna" if args.antenna else ("manager" if args.manager else None)
    if role is None:
        from ui.role_dialog import RoleDialog
        dlg = RoleDialog()
        if not dlg.exec() or dlg.choice is None:
            return 0
        choice = dlg.choice
        role = choice.role
        if role == "antenna":
            args.name = choice.name
            args.x, args.y = choice.x, choice.y
            args.manager_host = choice.manager_host

    if role == "antenna":
        return _run_antenna_in(app, args)

    # --- Dependency Injection (manager) ---
    platform_cap = detect()
    scanners = create_scanners(platform_cap)
    scanner = MultiScanner(scanners) if len(scanners) > 1 else scanners[0] if scanners else MultiScanner([])
    repository = JsonCalibrationRepository()
    anchor_store = AnchorStore(repository)
    from filtering.composite_filter import CompositeFilter
    from filtering.median_filter import MedianFilter
    from filtering.hampel_filter import HampelFilter
    filter_bank = FilterBank(lambda: CompositeFilter([
        MedianFilter(window=5),
        HampelFilter(window=7, n_sigmas=2.5),
        AdaptiveKalmanFilter(),
    ]))
    estimator = TrilaterationEstimator()
    tracer = EventBus()
    # tracer.add_listener(LogExplainer())  # uncomment for debug output

    positioning = PositioningService(anchor_store, estimator, filter_bank, tracer)

    # --- Multi-antenna RTLS (manager role) ---
    from antennas.local_antenna import LocalAntenna
    from services.combination_service import CombinationService
    from services.multireceiver_service import MultiReceiverService
    from net.manager_server import ManagerServer

    multireceiver = MultiReceiverService()
    local_antenna = LocalAntenna(scanner, node_id="local", name="This computer")
    manager_server = ManagerServer(multireceiver, port=args.port)
    combination_service = CombinationService(multireceiver)

    window = MainWindow(
        scanner, anchor_store, positioning,
        multireceiver=multireceiver,
        local_antenna=local_antenna,
        manager_server=manager_server,
        combination_service=combination_service,
    )
    window.show()
    window.raise_()
    window.activateWindow()

    if _HAS_QASYNC:
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)
        with loop:
            loop.run_until_complete(_run(app, window, manager_server))
    else:
        import threading

        _bg_loop = asyncio.new_event_loop()

        def run_loop():
            asyncio.set_event_loop(_bg_loop)
            _bg_loop.run_forever()

        t = threading.Thread(target=run_loop, daemon=True)
        t.start()

        if manager_server is not None:
            future = asyncio.run_coroutine_threadsafe(
                manager_server.start(), _bg_loop)
            future.result(timeout=5)
            print(f"[manager] WebSocket server started on port {manager_server.port}")

        window.start_scanning()
        sys.exit(app.exec())


def _run_antenna_in(app, args) -> int:
    """Run antenna mode inside an already-created QApplication."""
    if not _HAS_QASYNC:
        print("antenna mode requires qasync", file=sys.stderr)
        return 1
    from antennas.antenna_app import build_antenna
    win, coro = build_antenna(args)
    win.show()
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        loop.create_task(coro())
        loop.run_forever()
    return 0


async def _run(app: QApplication, window: MainWindow, manager_server=None):
    window.start_scanning()

    advertiser = None
    if manager_server is not None:
        try:
            await manager_server.start()
        except OSError as e:
            print(f"[manager] could not start antenna server: {e}", file=sys.stderr)
        # mDNS is a nice-to-have; never let it crash the app
        try:
            from net.discovery import ManagerAdvertiser
            advertiser = ManagerAdvertiser(port=manager_server.port)
            await advertiser.async_start()
        except Exception as e:
            print(f"[manager] mDNS advertise unavailable: {e}", file=sys.stderr)
            advertiser = None

    close_event = asyncio.Event()
    app.aboutToQuit.connect(close_event.set)
    await close_event.wait()

    if manager_server is not None:
        await manager_server.stop()
    if advertiser is not None:
        try:
            await advertiser.async_stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
