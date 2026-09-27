"""Antenna mode — turn any computer into a remote antenna.

Scans BLE/WiFi and streams NodeReports to a manager. The only UI is a small
status window (the user never interacts with it). Launched via:

    python main.py --antenna [--manager-host HOST] [--name NAME] [--x X --y Y]

If no host is given, it discovers the manager on the LAN via mDNS.
"""

from __future__ import annotations

import asyncio
import platform as _platform
import socket
import sys
import uuid

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from antennas.local_antenna import LocalAntenna
from core.platform import create_scanners
from net import discovery, node_protocol as proto
from net.node_client import NodeClient
from sensor.multi_scanner import MultiScanner


class _StatusWindow(QWidget):
    def __init__(self, node_name: str):
        super().__init__()
        self.setWindowTitle("BLE Locator Antenna")
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        title = QLabel(f"📡 Antenna: {node_name}")
        title.setStyleSheet("font-size:15px;font-weight:bold;")
        self._status = QLabel("Starting…")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-size:12px;color:#94a3b8;")
        hint = QLabel("Keep this window open. This computer is feeding the manager.")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size:11px;color:#64748b;")
        for w in (title, self._status, hint):
            layout.addWidget(w)

    def set_status(self, msg: str):
        self._status.setText(msg)


def run_antenna(args) -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    try:
        import qasync
    except ImportError:
        print("antenna mode requires qasync", file=sys.stderr)
        return 1

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    win, coro = build_antenna(args)
    win.show()

    with loop:
        loop.create_task(coro())
        loop.run_forever()
    return 0


def build_antenna(args):
    """Build the antenna status window + async runner for the shared app/loop.

    Returns (status_window, async_main_coro). The caller runs async_main_coro
    inside its own qasync loop. Used both by run_antenna (CLI) and by the
    launch-time role picker in main.py.
    """
    node_name = args.name or socket.gethostname()
    node_id = f"{node_name}-{uuid.getnode() & 0xffff:04x}"

    scanners = create_scanners()
    multi = MultiScanner(scanners)
    antenna = LocalAntenna(multi, node_id=node_id, name=node_name,
                           x=args.x, y=args.y)

    win = _StatusWindow(node_name)

    async def main_async():
        await multi.start()
        host = args.manager_host
        port = args.port
        if not host:
            win.set_status("Searching for manager on the network…")
            try:
                found = await discovery.async_discover_managers(timeout=2.5)
            except Exception:
                found = []
            if found:
                host, port = found[0]
            else:
                win.set_status("No manager found. Set the manager IP and relaunch.")
                return
        client = NodeClient(
            node_report_factory=antenna.report,
            host=host, port=port,
            platform=_platform.system(),
            send_interval=1.0,
            on_status=win.set_status,
        )
        await client.run()

    return win, main_async
