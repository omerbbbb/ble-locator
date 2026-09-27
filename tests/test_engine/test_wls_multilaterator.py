import pytest
from engine.wls_multilaterator import WlsMultilaterator


@pytest.fixture
def wls():
    return WlsMultilaterator()


def test_needs_at_least_2_fixes(wls):
    assert wls.locate([(0, 0, 1.0, 1.0)]) is None
    assert wls.locate([]) is None


def test_locate_with_3_fixes(wls):
    fixes = [
        (0.0, 0.0, 2.0, 1.0),
        (4.0, 0.0, 2.5, 1.0),
        (2.0, 3.0, 1.5, 1.0),
    ]
    result = wls.locate(fixes, room_w=5.0, room_h=4.0)
    assert result is not None
    x, y, unc = result
    assert 0.0 <= x <= 5.0
    assert 0.0 <= y <= 4.0


def test_higher_weight_pulls_solution(wls):
    fixes_equal = [
        (0.0, 0.0, 2.0, 1.0),
        (4.0, 0.0, 2.0, 1.0),
    ]
    fixes_biased = [
        (0.0, 0.0, 2.0, 10.0),
        (4.0, 0.0, 2.0, 1.0),
    ]
    r1 = wls.locate(fixes_equal, room_w=5.0, room_h=4.0)
    r2 = wls.locate(fixes_biased, room_w=5.0, room_h=4.0)
    assert r1 is not None and r2 is not None
    assert r2[0] < r1[0]


def test_uncertainty_returned(wls):
    fixes = [
        (0.0, 0.0, 2.0, 1.0),
        (4.0, 0.0, 2.5, 1.0),
        (2.0, 3.0, 1.5, 1.0),
    ]
    _, _, unc = wls.locate(fixes, room_w=5.0, room_h=4.0)
    assert unc is not None
    assert unc >= 0.0


def test_room_bounds_enforced(wls):
    fixes = [
        (0.0, 0.0, 0.5, 1.0),
        (1.0, 0.0, 0.5, 1.0),
    ]
    result = wls.locate(fixes, room_w=5.0, room_h=4.0)
    if result is not None:
        x, y, _ = result
        assert x >= 0.0
        assert y >= 0.0
        assert x <= 5.0
        assert y <= 4.0
