import time

import pytest

from core.models import NodeObservation, NodeReport, SignalType
from engine.auto_layout import DirectionHint
from services.auto_layout_service import AutoLayoutService


def _make_report(node_id, name, x, y, observations, now=None):
    now = now or time.time()
    obs = [
        NodeObservation(
            target_id=tid, name=oname, rssi=rssi,
            signal_type=SignalType.BLE, timestamp=now,
        )
        for tid, oname, rssi in observations
    ]
    return NodeReport(
        node_id=node_id, name=name, x=x, y=y,
        observations=obs, timestamp=now,
    )


@pytest.fixture
def svc():
    return AutoLayoutService()


def test_set_and_get_hint(svc):
    svc.set_hint("dev1", "right")
    hints = svc.hints()
    assert "dev1" in hints
    assert hints["dev1"].direction == "right"


def test_remove_hint(svc):
    svc.set_hint("dev1", "right")
    svc.remove_hint("dev1")
    assert "dev1" not in svc.hints()


def test_remove_hint_nonexistent(svc):
    svc.remove_hint("nonexistent")


def test_solve_returns_result(svc):
    now = time.time()
    local = _make_report("mac", "Mac", 2.5, 2.5, [
        ("phone", "iPhone", -55),
        ("watch", "Watch", -65),
    ], now)
    remotes = [
        _make_report("phone", "iPhone", 1.0, 1.0, [
            ("watch", "Watch", -60),
        ], now),
    ]
    svc.set_hint("phone", "right")
    result = svc.solve("mac", local, remotes, 5.0, 5.0)
    assert result is not None
    assert "mac" in result.positions


def test_solve_too_few_pairs(svc):
    now = time.time()
    local = _make_report("mac", "Mac", 2.5, 2.5, [], now)
    result = svc.solve("mac", local, [], 5.0, 5.0)
    assert result is None


def test_get_anchor_measurements_no_result(svc):
    ms = svc.get_anchor_measurements("mac")
    assert ms == []


def test_get_anchor_measurements_after_solve(svc):
    now = time.time()
    local = _make_report("mac", "Mac", 2.5, 2.5, [
        ("phone", "iPhone", -55),
        ("watch", "Watch", -65),
    ], now)
    remotes = [
        _make_report("phone", "iPhone", 1.0, 1.0, [
            ("watch", "Watch", -60),
        ], now),
    ]
    svc.solve("mac", local, remotes, 5.0, 5.0)
    ms = svc.get_anchor_measurements("mac")
    assert len(ms) >= 1
    for m in ms:
        assert m.distance > 0.05


def test_last_result(svc):
    assert svc.last_result is None
    now = time.time()
    local = _make_report("mac", "Mac", 2.5, 2.5, [
        ("phone", "iPhone", -55),
        ("watch", "Watch", -65),
    ], now)
    svc.solve("mac", local, [], 5.0, 5.0)
    assert svc.last_result is not None


def test_device_names(svc):
    now = time.time()
    local = _make_report("mac", "Mac", 2.5, 2.5, [
        ("phone", "iPhone", -55),
    ], now)
    svc.solve("mac", local, [], 5.0, 5.0)
    names = svc.device_names
    assert "phone" in names
    assert names["phone"] == "iPhone"


def test_obs_to_distance_rssi():
    obs = NodeObservation(target_id="t", name="t", rssi=-65)
    d = AutoLayoutService._obs_to_distance(obs, -59.0, 2.5)
    assert d > 0


def test_obs_to_distance_direct():
    obs = NodeObservation(target_id="t", name="t", rssi=-65, distance=2.5)
    d = AutoLayoutService._obs_to_distance(obs, -59.0, 2.5)
    assert d == 2.5


def test_obs_to_distance_direct_clamped():
    obs = NodeObservation(target_id="t", name="t", rssi=-65, distance=0.01)
    d = AutoLayoutService._obs_to_distance(obs, -59.0, 2.5)
    assert d == 0.05
