import time

import pytest

from core.models import NodeObservation, NodeReport, SignalType
from services.multireceiver_service import MultiReceiverService


def _make_report(node_id, x, y, targets, now=None):
    now = now or time.time()
    obs = [
        NodeObservation(
            target_id=tid, name=name, rssi=rssi,
            signal_type=SignalType.BLE, timestamp=now,
        )
        for tid, name, rssi in targets
    ]
    return NodeReport(
        node_id=node_id, name=f"Node-{node_id}", x=x, y=y,
        observations=obs, timestamp=now, is_local=(node_id == "local"),
    )


@pytest.fixture
def svc():
    return MultiReceiverService()


def test_submit_and_active_nodes(svc):
    now = time.time()
    r = _make_report("n1", 0, 0, [("t1", "Dev", -65)], now)
    svc.submit(r)
    assert len(svc.active_nodes(now)) == 1


def test_active_nodes_expires(svc):
    old = time.time() - 20
    r = _make_report("n1", 0, 0, [("t1", "Dev", -65)], old)
    svc.submit(r)
    assert len(svc.active_nodes()) == 0


def test_recalibrate_clears_filters(svc):
    now = time.time()
    r = _make_report("n1", 0, 0, [("t1", "Dev", -65)], now)
    svc.submit(r)
    svc.collect_target_fixes(now)
    assert len(svc._filters) > 0
    svc.recalibrate()
    assert len(svc._filters) == 0


def test_weight_rssi():
    w = MultiReceiverService._weight(
        _make_report("n1", 0, 0, []),
        NodeObservation(target_id="t", name="t", rssi=-60),
    )
    assert 0.05 <= w <= 1.0


def test_weight_with_distance():
    w = MultiReceiverService._weight(
        _make_report("n1", 0, 0, []),
        NodeObservation(target_id="t", name="t", rssi=-80, distance=2.0),
    )
    assert w == 2.0


def test_weight_very_weak_signal():
    w = MultiReceiverService._weight(
        _make_report("n1", 0, 0, []),
        NodeObservation(target_id="t", name="t", rssi=-100),
    )
    assert w == 0.05


def test_collect_target_fixes(svc):
    now = time.time()
    svc.submit(_make_report("n1", 0, 0, [("t1", "Dev", -65)], now))
    svc.submit(_make_report("n2", 4, 0, [("t1", "Dev", -70)], now))
    fixes = svc.collect_target_fixes(now)
    assert "t1" in fixes
    assert len(fixes["t1"]["fixes"]) == 2


def test_collect_target_fixes_only_nodes(svc):
    now = time.time()
    svc.submit(_make_report("n1", 0, 0, [("t1", "Dev", -65)], now))
    svc.submit(_make_report("n2", 4, 0, [("t1", "Dev", -70)], now))
    fixes = svc.collect_target_fixes(now, only_nodes={"n1"})
    assert len(fixes["t1"]["fixes"]) == 1


def test_locate_targets_needs_2_antennas(svc):
    now = time.time()
    svc.submit(_make_report("n1", 0, 0, [("t1", "Dev", -65)], now))
    results = svc.locate_targets(5.0, 4.0, now)
    assert len(results) == 0


def test_locate_targets_with_2_antennas(svc):
    now = time.time()
    svc.submit(_make_report("n1", 0, 0, [("t1", "Dev", -60)], now))
    svc.submit(_make_report("n2", 4, 0, [("t1", "Dev", -65)], now))
    results = svc.locate_targets(5.0, 4.0, now)
    assert len(results) == 1
    est = results[0]
    assert est.target_id == "t1"
    assert 0 <= est.x <= 5
    assert 0 <= est.y <= 4


def test_locate_targets_3_antennas(svc):
    now = time.time()
    svc.submit(_make_report("n1", 0, 0, [("t1", "Dev", -60)], now))
    svc.submit(_make_report("n2", 4, 0, [("t1", "Dev", -65)], now))
    svc.submit(_make_report("n3", 2, 3, [("t1", "Dev", -62)], now))
    results = svc.locate_targets(5.0, 4.0, now)
    assert len(results) == 1
    assert results[0].num_nodes == 3


def test_estimate_from_fixes_static():
    tagged = [
        ("n1", 0.0, 0.0, 2.0, 1.0),
        ("n2", 4.0, 0.0, 2.5, 1.0),
        ("n3", 2.0, 3.0, 1.5, 1.0),
    ]
    est = MultiReceiverService.estimate_from_fixes(
        tagged, "Dev", "t1", SignalType.BLE, 5.0, 4.0)
    assert est is not None
    assert est.num_nodes == 3
    assert len(est.contributing_nodes) == 3


def test_estimate_from_fixes_too_few():
    tagged = [("n1", 0.0, 0.0, 2.0, 1.0)]
    est = MultiReceiverService.estimate_from_fixes(
        tagged, "Dev", "t1", SignalType.BLE, 5.0, 4.0)
    assert est is None


def test_get_self_measurements(svc):
    now = time.time()
    svc.submit(NodeReport(
        node_id="iphone", name="iPhone", x=3.0, y=2.0,
        observations=[
            NodeObservation(target_id="mac-id", name="Mac's MacBook", rssi=-55, timestamp=now),
        ],
        timestamp=now, is_local=False,
    ))
    ms = svc.get_self_measurements("Mac's MacBook", now)
    assert len(ms) == 1
    assert ms[0].x == 3.0
    assert ms[0].y == 2.0


def test_get_self_measurements_ignores_local(svc):
    now = time.time()
    svc.submit(NodeReport(
        node_id="local", name="Mac", x=0.0, y=0.0,
        observations=[
            NodeObservation(target_id="x", name="Mac's MacBook", rssi=-50, timestamp=now),
        ],
        timestamp=now, is_local=True,
    ))
    ms = svc.get_self_measurements("Mac's MacBook", now)
    assert len(ms) == 0


def test_get_anchor_observations_from_remotes(svc):
    now = time.time()
    svc.submit(NodeReport(
        node_id="iphone", name="iPhone", x=3.0, y=2.0,
        observations=[
            NodeObservation(target_id="A1", name="Watch", rssi=-60, timestamp=now),
            NodeObservation(target_id="mac", name="Mac's MacBook", rssi=-55, timestamp=now),
        ],
        timestamp=now, is_local=False,
    ))
    result = svc.get_anchor_observations_from_remotes({"A1"}, "Mac's MacBook", now)
    assert "A1" in result
    assert "mac" not in result


def test_to_distance_with_direct_distance(svc):
    node = _make_report("n1", 0, 0, [])
    obs = NodeObservation(target_id="t", name="t", rssi=-80, distance=2.5, timestamp=time.time())
    cleaned = svc._clean_value("n1", obs)
    d = svc._to_distance(node, obs, cleaned)
    assert d >= 0.05
