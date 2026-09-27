"""Render README screenshots headlessly from the real UI widgets.

Runs the actual RoomCanvas and DistanceRadar widgets with sample data using the
Qt offscreen platform (no display needed) and saves PNGs to docs/screenshots/.
    .venv/bin/python docs/render_screenshots.py
"""
import math, os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
from core.models import DeviceEstimate, SignalType
from ui.theme import dark_palette
from ui.room_canvas import RoomCanvas
from ui.distance_radar import DistanceRadar

OUT = ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

app = QApplication(sys.argv)
app.setStyle("Fusion")
app.setPalette(dark_palette())

def grab(widget, w, h, name):
    widget.resize(w, h)
    widget.show()
    app.processEvents()
    widget.grab().save(str(OUT / name))
    print("wrote", OUT / name)

# ── Position Map: 3 anchors, a position fix, uncertainty ellipse ──
canvas = RoomCanvas()
canvas.room_w, canvas.room_h = 5.0, 4.0
anchors = {"A1": (0.5, 0.5, "Beacon"), "A2": (4.5, 0.6, "Apple Watch"), "A3": (2.5, 3.5, "AirPods")}
canvas.set_anchors(anchors)
canvas.set_distances({"A1": 2.1, "A2": 2.4, "A3": 1.6})
canvas.set_uncertainty((0.35, 0.22, 0.4))
canvas.set_particles(None, None)
canvas.set_position(2.3, 1.9)
grab(canvas, 960, 620, "position_map.png")

# ── Distance Radar: a handful of devices at different ranges ──
radar = DistanceRadar()
def dev(i, name, rssi, d, anchor=False, ang=None):
    return DeviceEstimate(device_id=f"dev-{i}", name=name, raw_rssi=rssi, filtered_rssi=rssi,
                          distance=d, is_anchor=anchor, signal_type=SignalType.BLE, angle=ang)
devices = [
    dev(1, "iPhone",      -58, 0.9,  ang=0.4),
    dev(2, "Apple Watch", -64, 1.6,  True, ang=2.2),
    dev(3, "AirPods",     -70, 2.7,  ang=3.6),
    dev(4, "Beacon",      -62, 1.3,  True, ang=5.1),
    dev(5, "Unnamed",     -79, 4.3,  ang=1.3),
    dev(6, "Smart TV",    -74, 3.4,  ang=4.4),
]
radar.set_selected("dev-1")
radar.set_devices(devices)
grab(radar, 960, 620, "distance_radar.png")
