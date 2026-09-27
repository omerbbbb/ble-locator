import time

import pytest

from core.models import Anchor, SignalReading, SignalType
from services.anchor_store import AnchorStore
from services.pane_positioner import PanePositioner, weighted_fuse
from tests.conftest import InMemoryCalibrationRepository


@pytest.fixture
def anchors():
    data = {
        "A1": Anchor("A1", "Anchor-1", tx_power=-59.0, n=2.5, x=0.0, y=0.0),
        "A2": Anchor("A2", "Anchor-2", tx_power=-59.0, n=2.5, x=4.0, y=0.0),
        "A3": Anchor("A3", "Anchor-3", tx_power=-59.0, n=2.5, x=2.0, y=3.0),
    }
    repo = InMemoryCalibrationRepository(data)
    return AnchorStore(repo)


@pytest.fixture
def positioner(anchors):
    return PanePositioner(anchors)


def _make_readings(now=None):
    now = now or time.time()
    return {
        "A1": SignalReading("A1", "Anchor-1", rssi=-65, timestamp=now),
        "A2": SignalReading("A2", "Anchor-2", rssi=-70, timestamp=now),
        "A3": SignalReading("A3", "Anchor-3", rssi=-62, timestamp=now),
    }


def test_update_returns_position(positioner):
    readings = _make_readings()
    pos, anchors_ui, distances, particles, pw = positioner.update(readings, 5.0, 4.0)
    assert pos is not None
    assert len(anchors_ui) == 3
    assert len(distances) == 3


def test_update_no_anchors():
    repo = InMemoryCalibrationRepository({})
    store = AnchorStore(repo)
    pp = PanePositioner(store)
    now = time.time()
    readings = {"X": SignalReading("X", "Unknown", rssi=-70, timestamp=now)}
    pos, anchors_ui, distances, particles, pw = pp.update(readings, 5.0, 4.0)
    assert pos is None
    assert len(anchors_ui) == 0


def test_smoothing_converges(positioner):
    positions = []
    for _ in range(20):
        pos, *_ = positioner.update(_make_readings(), 5.0, 4.0)
        if pos is not None:
            positions.append(pos)
    assert len(positions) > 5
    dx = abs(positions[-1][0] - positions[-2][0])
    dy = abs(positions[-1][1] - positions[-2][1])
    assert dx < 0.1
    assert dy < 0.1


def test_reset(positioner):
    positioner.update(_make_readings(), 5.0, 4.0)
    positioner.reset()
    assert positioner._pos_smooth is None


def test_algorithm_centroid(positioner):
    positioner.algorithm = "centroid"
    pos, *_ = positioner.update(_make_readings(), 5.0, 4.0)
    assert pos is not None


def test_algorithm_particle(positioner):
    positioner.algorithm = "particle"
    for _ in range(5):
        pos, _, _, particles, pw = positioner.update(_make_readings(), 5.0, 4.0)
    assert particles is not None


def test_algorithm_fusion(positioner):
    positioner.algorithm = "fusion"
    for _ in range(5):
        pos, *_ = positioner.update(_make_readings(), 5.0, 4.0)
    assert pos is not None


def test_algorithm_ensemble(positioner):
    positioner.algorithm = "ensemble"
    for _ in range(5):
        pos, *_ = positioner.update(_make_readings(), 5.0, 4.0)
    assert pos is not None


def test_uncertainty_trilateration(positioner):
    positioner.update(_make_readings(), 5.0, 4.0)
    unc = positioner.uncertainty
    assert unc is None or unc >= 0.0


def test_uncertainty_particle(positioner):
    positioner.algorithm = "particle"
    for _ in range(5):
        positioner.update(_make_readings(), 5.0, 4.0)
    unc = positioner.uncertainty
    assert unc is None or unc >= 0.0


def test_uncertainty_fusion(positioner):
    positioner.algorithm = "fusion"
    for _ in range(5):
        positioner.update(_make_readings(), 5.0, 4.0)
    unc = positioner.uncertainty
    assert unc is None or unc >= 0.0


def test_signal_filter_ble(positioner):
    positioner.signal_filter = "ble"
    now = time.time()
    readings = {
        "A1": SignalReading("A1", "Anchor-1", rssi=-65, timestamp=now, signal_type=SignalType.BLE),
        "W1": SignalReading("W1", "Wifi-1", rssi=-60, timestamp=now, signal_type=SignalType.WIFI),
    }
    positioner.update(readings, 5.0, 4.0)


def test_signal_filter_wifi(positioner):
    positioner.signal_filter = "wifi"
    positioner.update(_make_readings(), 5.0, 4.0)


# --- weighted_fuse ---

def test_weighted_fuse_empty():
    assert weighted_fuse([]) is None


def test_weighted_fuse_all_none():
    assert weighted_fuse([(None, 1.0), (None, 2.0)]) is None


def test_weighted_fuse_single():
    result = weighted_fuse([((2.0, 3.0), 1.0)])
    assert result is not None
    assert abs(result[0] - 2.0) < 0.01
    assert abs(result[1] - 3.0) < 0.01


def test_weighted_fuse_lower_unc_wins():
    result = weighted_fuse([
        ((0.0, 0.0), 0.1),
        ((4.0, 0.0), 2.0),
    ])
    assert result is not None
    assert result[0] < 2.0
