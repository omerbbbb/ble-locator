import time

import pytest

from core.models import Anchor, AnchorMeasurement, EstimationMode, SignalReading, SignalType
from engine.trilateration import TrilaterationEstimator
from filtering.adaptive_kalman import AdaptiveKalmanFilter
from filtering.filter_bank import FilterBank
from services.anchor_store import AnchorStore
from services.positioning_service import PositioningService, _weighted_fuse
from tests.conftest import InMemoryCalibrationRepository


@pytest.fixture
def service():
    data = {
        "A1": Anchor("A1", "Anchor-1", tx_power=-59.0, n=2.5, x=0.0, y=0.0),
        "A2": Anchor("A2", "Anchor-2", tx_power=-59.0, n=2.5, x=4.0, y=0.0),
        "A3": Anchor("A3", "Anchor-3", tx_power=-59.0, n=2.5, x=2.0, y=3.0),
    }
    repo = InMemoryCalibrationRepository(data)
    store = AnchorStore(repo)
    return PositioningService(
        anchors=store,
        estimator=TrilaterationEstimator(),
        filter_bank=FilterBank(AdaptiveKalmanFilter),
    )


def _readings(now=None):
    now = now or time.time()
    return {
        "A1": SignalReading("A1", "Anchor-1", rssi=-65, timestamp=now),
        "A2": SignalReading("A2", "Anchor-2", rssi=-70, timestamp=now),
        "A3": SignalReading("A3", "Anchor-3", rssi=-62, timestamp=now),
    }


def test_modes_trilateration(service):
    service.mode = EstimationMode.TRILATERATION
    result = service.update(_readings(), 5.0, 4.0)
    assert result.position is not None
    assert result.estimation_mode == "trilateration"


def test_modes_particle(service):
    service.mode = EstimationMode.PARTICLE
    for _ in range(5):
        result = service.update(_readings(), 5.0, 4.0)
    assert result.estimation_mode == "particle"


def test_modes_fusion(service):
    service.mode = EstimationMode.FUSION
    for _ in range(5):
        result = service.update(_readings(), 5.0, 4.0)
    assert result.estimation_mode == "fusion"


def test_modes_ensemble(service):
    service.mode = EstimationMode.ENSEMBLE
    for _ in range(5):
        result = service.update(_readings(), 5.0, 4.0)
    assert result.estimation_mode == "ensemble"


def test_modes_centroid(service):
    service.mode = EstimationMode.CENTROID
    result = service.update(_readings(), 5.0, 4.0)
    assert result.estimation_mode == "centroid"
    assert result.position is not None


def test_extra_measurements(service):
    extra = [AnchorMeasurement(x=1.0, y=1.0, distance=1.5)]
    result = service.update(_readings(), 5.0, 4.0, extra_measurements=extra)
    assert result.position is not None


def test_stale_readings_excluded(service):
    old = time.time() - 30
    readings = {
        "A1": SignalReading("A1", "Anchor-1", rssi=-65, timestamp=old),
        "A2": SignalReading("A2", "Anchor-2", rssi=-70, timestamp=old),
        "A3": SignalReading("A3", "Anchor-3", rssi=-62, timestamp=old),
    }
    result = service.update(readings, 5.0, 4.0)
    assert result.position is None


def test_status_with_position(service):
    result = service.update(_readings(), 5.0, 4.0)
    assert "Position:" in result.status


def test_status_without_position(service):
    repo = InMemoryCalibrationRepository({})
    store = AnchorStore(repo)
    svc = PositioningService(
        anchors=store, estimator=TrilaterationEstimator(),
        filter_bank=FilterBank(AdaptiveKalmanFilter),
    )
    now = time.time()
    result = svc.update({"X": SignalReading("X", "Dev", rssi=-70, timestamp=now)}, 5.0, 4.0)
    assert "Need" in result.status or "Scanning" in result.status


def test_nlos_detector_created(service):
    service.update(_readings(), 5.0, 4.0)
    assert len(service._nlos) == 3


def test_device_estimates_populated(service):
    result = service.update(_readings(), 5.0, 4.0)
    assert len(result.devices) == 3
    for de in result.devices:
        assert de.distance > 0
        assert de.is_anchor is True


def test_position_in_room_bounds(service):
    for _ in range(10):
        result = service.update(_readings(), 5.0, 4.0)
    if result.position is not None:
        x, y = result.position
        assert -0.5 <= x <= 5.5
        assert -0.5 <= y <= 4.5


def test_direct_distance_reading(service):
    now = time.time()
    readings = {
        "A1": SignalReading("A1", "Anchor-1", rssi=-65, timestamp=now, distance=1.5),
        "A2": SignalReading("A2", "Anchor-2", rssi=-70, timestamp=now, distance=2.0),
        "A3": SignalReading("A3", "Anchor-3", rssi=-62, timestamp=now, distance=1.0),
    }
    result = service.update(readings, 5.0, 4.0)
    assert result.position is not None
    assert result.distances["A1"] == 1.5


def test_weighted_fuse_fn():
    result = _weighted_fuse([((1.0, 2.0), 0.5), ((3.0, 4.0), 2.0)])
    assert result is not None
    assert result[0] < 2.0


def test_weighted_fuse_none():
    assert _weighted_fuse([]) is None
    assert _weighted_fuse([(None, 1.0)]) is None
