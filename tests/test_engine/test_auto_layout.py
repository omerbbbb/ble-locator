import pytest
from engine.auto_layout import (
    AutoLayoutResult,
    DIRECTION_ANGLES,
    DirectionHint,
    PairwiseDistance,
    solve_layout,
    _collect_ids,
    _distances_from,
)


def test_direction_angles_exist():
    expected = {"right", "lower-right", "below", "lower-left",
                "left", "upper-left", "above", "upper-right"}
    assert set(DIRECTION_ANGLES.keys()) == expected


def test_direction_hint_angle():
    h = DirectionHint("dev1", "right")
    assert h.angle == 0.0
    h2 = DirectionHint("dev2", "nonexistent")
    assert h2.angle == 0.0


def test_pairwise_distance():
    p = PairwiseDistance("a", "b", 2.5, weight=0.8)
    assert p.id_a == "a"
    assert p.distance == 2.5
    assert p.weight == 0.8


def test_collect_ids():
    pairs = [
        PairwiseDistance("mac", "phone", 1.0),
        PairwiseDistance("mac", "watch", 2.0),
        PairwiseDistance("phone", "watch", 1.5),
    ]
    ids = _collect_ids("mac", pairs)
    assert ids[0] == "mac"
    assert set(ids) == {"mac", "phone", "watch"}


def test_distances_from():
    pairs = [
        PairwiseDistance("mac", "phone", 1.0),
        PairwiseDistance("mac", "watch", 2.0),
        PairwiseDistance("phone", "watch", 1.5),
    ]
    d = _distances_from("mac", pairs)
    assert d == {"phone": 1.0, "watch": 2.0}


def test_solve_layout_needs_2_devices():
    pairs = [PairwiseDistance("mac", "phone", 1.0)]
    result = solve_layout("mac", pairs, {}, 5.0, 5.0)
    assert result is not None


def test_solve_layout_too_few_pairs():
    result = solve_layout("mac", [], {}, 5.0, 5.0)
    assert result is None


def test_solve_layout_with_hints():
    pairs = [
        PairwiseDistance("mac", "phone", 1.5),
        PairwiseDistance("mac", "watch", 2.0),
        PairwiseDistance("phone", "watch", 1.8),
    ]
    hints = {
        "phone": DirectionHint("phone", "right"),
        "watch": DirectionHint("watch", "above"),
    }
    result = solve_layout("mac", pairs, hints, 5.0, 5.0)
    assert result is not None
    assert "mac" in result.positions
    assert "phone" in result.positions
    assert "watch" in result.positions
    mac_x, mac_y = result.positions["mac"]
    assert abs(mac_x - 2.5) < 0.1
    assert abs(mac_y - 2.5) < 0.1


def test_solve_layout_positions_in_room():
    pairs = [
        PairwiseDistance("mac", "a", 1.0),
        PairwiseDistance("mac", "b", 1.5),
    ]
    result = solve_layout("mac", pairs, {}, 5.0, 5.0)
    assert result is not None
    for pos in result.positions.values():
        assert 0.0 <= pos[0] <= 5.0
        assert 0.0 <= pos[1] <= 5.0


def test_auto_layout_result():
    r = AutoLayoutResult({"a": (1.0, 2.0)}, residual=0.05)
    assert r.positions == {"a": (1.0, 2.0)}
    assert r.residual == 0.05
