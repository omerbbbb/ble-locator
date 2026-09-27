from core.models import AnchorMeasurement
from engine.trilateration import TrilaterationEstimator


def test_needs_at_least_3_anchors():
    est = TrilaterationEstimator()
    two = [AnchorMeasurement(0, 0, 1), AnchorMeasurement(4, 0, 1)]
    assert est.estimate(two) is None


def test_estimate_with_3_anchors(sample_measurements):
    est = TrilaterationEstimator()
    pos = est.estimate(sample_measurements, room_w=5, room_h=4)
    assert pos is not None
    x, y = pos
    assert 0 <= x <= 5
    assert 0 <= y <= 4


def test_uncertainty_populated_after_estimate(sample_measurements):
    est = TrilaterationEstimator()
    est.estimate(sample_measurements, room_w=5, room_h=4)
    assert est.uncertainty_radius is not None
    assert est.uncertainty_ellipse is not None


def test_room_bounds_enforced():
    est = TrilaterationEstimator()
    measurements = [
        AnchorMeasurement(0, 0, 0.1),
        AnchorMeasurement(1, 0, 2.0),
        AnchorMeasurement(0, 1, 2.0),
    ]
    pos = est.estimate(measurements, room_w=3, room_h=3)
    if pos is not None:
        assert 0 <= pos[0] <= 3
        assert 0 <= pos[1] <= 3
