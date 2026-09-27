from core.models import AnchorMeasurement
from engine.weighted_centroid import WeightedCentroidEstimator


def test_empty_returns_none():
    assert WeightedCentroidEstimator().estimate([]) is None


def test_single_anchor_returns_anchor_pos():
    est = WeightedCentroidEstimator()
    pos = est.estimate([AnchorMeasurement(x=3.0, y=4.0, distance=1.0)])
    assert pos == (3.0, 4.0)


def test_closer_anchor_pulls_harder():
    est = WeightedCentroidEstimator()
    m = [
        AnchorMeasurement(x=0.0, y=0.0, distance=1.0),
        AnchorMeasurement(x=4.0, y=0.0, distance=3.0),
    ]
    x, y = est.estimate(m)
    assert x < 2.0
    assert abs(y) < 0.01


def test_equal_distances_gives_centroid():
    est = WeightedCentroidEstimator()
    m = [
        AnchorMeasurement(x=0.0, y=0.0, distance=2.0),
        AnchorMeasurement(x=4.0, y=0.0, distance=2.0),
        AnchorMeasurement(x=2.0, y=3.0, distance=2.0),
    ]
    x, y = est.estimate(m)
    assert abs(x - 2.0) < 0.01
    assert abs(y - 1.0) < 0.01


def test_very_small_distance_clamped():
    est = WeightedCentroidEstimator()
    m = [
        AnchorMeasurement(x=1.0, y=1.0, distance=0.001),
        AnchorMeasurement(x=5.0, y=5.0, distance=3.0),
    ]
    x, y = est.estimate(m)
    assert abs(x - 1.0) < 0.2
    assert abs(y - 1.0) < 0.2
