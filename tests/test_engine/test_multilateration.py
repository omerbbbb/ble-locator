import pytest
from engine.multilateration import Multilaterator


@pytest.fixture
def ml():
    return Multilaterator()


def test_needs_at_least_2(ml):
    assert ml.locate([(0, 0, 1.0)]) is None
    assert ml.locate([]) is None


def test_locate_with_3_antennas(ml):
    fixes = [
        (0.0, 0.0, 2.0),
        (4.0, 0.0, 2.5),
        (2.0, 3.0, 1.5),
    ]
    result = ml.locate(fixes, room_w=5.0, room_h=4.0)
    assert result is not None
    x, y, unc = result
    assert 0.0 <= x <= 5.0
    assert 0.0 <= y <= 4.0


def test_locate_with_2_antennas(ml):
    fixes = [
        (0.0, 0.0, 2.0),
        (4.0, 0.0, 2.5),
    ]
    result = ml.locate(fixes, room_w=5.0, room_h=4.0)
    assert result is not None


def test_room_bounds_clamp(ml):
    fixes = [
        (0.0, 0.0, 0.3),
        (0.5, 0.0, 0.3),
        (0.25, 0.5, 0.3),
    ]
    result = ml.locate(fixes, room_w=5.0, room_h=4.0)
    if result is not None:
        x, y, _ = result
        assert x >= 0.0
        assert y >= 0.0


def test_uncertainty_populated(ml):
    fixes = [
        (0.0, 0.0, 2.0),
        (4.0, 0.0, 2.5),
        (2.0, 3.0, 1.5),
    ]
    _, _, unc = ml.locate(fixes, room_w=5.0, room_h=4.0)
    assert unc is not None
    assert unc >= 0.0


def test_no_room_bounds(ml):
    fixes = [
        (0.0, 0.0, 2.0),
        (4.0, 0.0, 2.5),
        (2.0, 3.0, 1.5),
    ]
    result = ml.locate(fixes)
    assert result is not None
