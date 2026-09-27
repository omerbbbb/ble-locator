import time

from core.models import AnchorMeasurement, SignalReading
from engine.trilateration import TrilaterationEstimator
from filtering.adaptive_kalman import AdaptiveKalmanFilter
from filtering.composite_filter import CompositeFilter
from filtering.filter_bank import FilterBank
from filtering.hampel_filter import HampelFilter
from filtering.median_filter import MedianFilter
from services.anchor_store import AnchorStore
from services.positioning_service import PositioningService


def _make_service(in_memory_repo):
    store = AnchorStore(in_memory_repo)
    fb = FilterBank(lambda: CompositeFilter([
        MedianFilter(5),
        HampelFilter(7, 2.5),
        AdaptiveKalmanFilter(),
    ]))
    return PositioningService(store, TrilaterationEstimator(), fb)


def test_warmup_alpha_schedule(in_memory_repo):
    svc = _make_service(in_memory_repo)
    now = time.time()
    readings = {
        "A1": SignalReading("A1", "a1", rssi=-65, timestamp=now),
        "A2": SignalReading("A2", "a2", rssi=-70, timestamp=now),
        "A3": SignalReading("A3", "a3", rssi=-62, timestamp=now),
    }
    positions = []
    for _ in range(25):
        r = svc.update(readings, 5.0, 4.0)
        if r.position:
            positions.append(r.position)
    assert len(positions) >= 20
    last5 = positions[-5:]
    spread_x = max(p[0] for p in last5) - min(p[0] for p in last5)
    spread_y = max(p[1] for p in last5) - min(p[1] for p in last5)
    assert spread_x < 0.5
    assert spread_y < 0.5


def test_no_anchors_returns_no_position(in_memory_repo):
    svc = _make_service(in_memory_repo)
    now = time.time()
    readings = {"X": SignalReading("X", "unknown", rssi=-70, timestamp=now)}
    result = svc.update(readings, 5.0, 4.0)
    assert result.position is None


def _dev_dist(result, did):
    return next(d.distance for d in result.devices if d.device_id == did)


def test_no_position_mode_gives_distances(in_memory_repo):
    svc = _make_service(in_memory_repo)
    now = time.time()
    readings = {
        "A1": SignalReading("A1", "a1", rssi=-65, timestamp=now),
        "X": SignalReading("X", "stranger", rssi=-80, timestamp=now),
    }
    result = svc.update(readings, 5.0, 4.0, compute_position=False)
    # Distance for every device, but no 2-D fix when position is gated off.
    assert _dev_dist(result, "A1") > 0
    assert _dev_dist(result, "X") > 0
    assert result.position is None


def test_distances_are_smoothed_continuously(in_memory_repo):
    svc = _make_service(in_memory_repo)
    now = time.time()
    readings = {"A1": SignalReading("A1", "a1", rssi=-65, timestamp=now)}
    svc.update(readings, 5.0, 4.0, compute_position=False)
    # The filter chain runs even without a position fix (continuous smoothing).
    assert "A1" in svc._filter_bank._filters
    assert "A1" in svc._nlos


def test_weak_signal_reads_far_no_clamp(in_memory_repo):
    svc = _make_service(in_memory_repo)
    now = time.time()
    # Natural log-distance: a very weak signal reads far, with no room clamp.
    readings = {"X": SignalReading("X", "weak", rssi=-100, timestamp=now)}
    result = svc.update(readings, 5.0, 4.0, compute_position=False)
    diag = (5.0 ** 2 + 4.0 ** 2) ** 0.5
    assert _dev_dist(result, "X") > diag


def test_advertised_tx_power_used(in_memory_repo):
    svc = _make_service(in_memory_repo)
    now = time.time()
    # Same RSSI, different advertised TX power → different (sensible) distance.
    strong_tx = SignalReading("A", "a", rssi=-75, timestamp=now, tx_power_adv=4)
    no_tx = SignalReading("B", "b", rssi=-75, timestamp=now)
    res = svc.update({"A": strong_tx, "B": no_tx}, 8.0, 6.0, compute_position=False)
    # The advertised-TX device uses tx_ref = 4 - 41 = -37 (a far reference), so
    # the same RSSI maps to a different distance than the fixed -59 default.
    assert _dev_dist(res, "A") != _dev_dist(res, "B")


def test_weaker_signal_reads_farther(in_memory_repo):
    svc = _make_service(in_memory_repo)

    def feed(rssi, ticks=8):
        result = None
        for _ in range(ticks):
            result = svc.update(
                {"P": SignalReading("P", "p", rssi=rssi, timestamp=time.time())},
                8.0, 6.0)
        return next(d.distance for d in result.devices if d.device_id == "P")

    # With a fixed reference, a sustained weaker signal must read farther.
    d_close = feed(-55)
    d_far = feed(-80)
    assert d_far > d_close


def test_anchor_keeps_its_calibrated_tx(in_memory_repo):
    svc = _make_service(in_memory_repo)
    now = time.time()
    reading = SignalReading("A1", "a1", rssi=-75, timestamp=now, tx_power_adv=4)
    # A1 is a calibrated anchor (tx_power=-59); advertised TX must be ignored.
    ref = svc._reference_tx("A1", reading, svc._anchors.get("A1"))
    assert ref == -59.0


def test_update_prunes_absent_device_state(in_memory_repo):
    svc = _make_service(in_memory_repo)
    now = time.time()
    svc.update({"A1": SignalReading("A1", "a1", rssi=-65, timestamp=now)}, 5.0, 4.0)
    svc.update({"A2": SignalReading("A2", "a2", rssi=-66, timestamp=now)}, 5.0, 4.0)
    # A1 is an anchor (always retained); a non-anchor would be dropped.
    svc.update({"Z": SignalReading("Z", "z", rssi=-70, timestamp=now)}, 5.0, 4.0)
    svc.update({"A2": SignalReading("A2", "a2", rssi=-66, timestamp=now)}, 5.0, 4.0)
    assert "Z" not in svc._nlos
