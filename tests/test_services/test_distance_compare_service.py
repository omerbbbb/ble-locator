import statistics
import time

from core.models import SignalReading
from services.anchor_store import AnchorStore
from services.distance_compare_service import DistanceCompareService


def _svc(in_memory_repo):
    return DistanceCompareService(AnchorStore(in_memory_repo))


def _row(rows, did):
    return next(r for r in rows if r.device_id == did)


def test_steady_signal_converges_equal(in_memory_repo):
    svc = _svc(in_memory_repo)
    last = None
    for _ in range(20):
        rows = svc.update(
            {"X": SignalReading("X", "x", rssi=-70, timestamp=time.time())},
            8.0, 6.0)
        last = _row(rows, "X")
    # Same calibration, steady input → both chains agree closely.
    assert abs(last.d_kalman - last.d_full) < 0.3


def test_full_chain_rejects_spikes_better(in_memory_repo):
    svc = _svc(in_memory_repo)
    # A clean -70 baseline with periodic strong spikes to -40.
    seq = [-70, -70, -40, -70, -70, -40, -70, -70, -40, -70, -70, -40] * 2
    dk, df = [], []
    for rssi in seq:
        rows = svc.update(
            {"X": SignalReading("X", "x", rssi=rssi, timestamp=time.time())},
            8.0, 6.0)
        r = _row(rows, "X")
        dk.append(r.d_kalman)
        df.append(r.d_full)
    # The full chain (median+hampel) is steadier than Kalman-only under spikes.
    assert statistics.pstdev(df) < statistics.pstdev(dk)


def test_reset_clears_state(in_memory_repo):
    svc = _svc(in_memory_repo)
    for _ in range(5):
        svc.update({"X": SignalReading("X", "x", rssi=-55, timestamp=time.time())},
                   8.0, 6.0)
    svc.reset()
    assert svc._kalman._filters == {}
    assert svc._full._filters == {}


def test_update_prunes_absent_devices(in_memory_repo):
    svc = _svc(in_memory_repo)
    svc.update({"X": SignalReading("X", "x", rssi=-60, timestamp=time.time())},
               8.0, 6.0)
    svc.update({"Y": SignalReading("Y", "y", rssi=-60, timestamp=time.time())},
               8.0, 6.0)
    assert "X" not in svc._kalman._filters
    assert "X" not in svc._full._filters


def test_weak_signal_reads_far(in_memory_repo):
    svc = _svc(in_memory_repo)
    rows = svc.update(
        {"W": SignalReading("W", "w", rssi=-100, timestamp=time.time())}, 5.0, 4.0)
    r = _row(rows, "W")
    # Natural log-distance, no clamp — a very weak signal is genuinely far.
    assert r.d_kalman > 5.0
    assert r.d_full > 5.0
