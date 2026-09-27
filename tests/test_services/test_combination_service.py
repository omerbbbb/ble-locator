import time

import pytest

from core.models import NodeObservation, NodeReport, SignalType
from services.combination_service import CombinationResult, CombinationService, _score
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
        observations=obs, timestamp=now,
    )


@pytest.fixture
def svc():
    mrs = MultiReceiverService()
    return CombinationService(mrs), mrs


def test_list_targets_empty(svc):
    cs, _ = svc
    assert cs.list_targets() == []


def test_list_targets_needs_2_antennas(svc):
    cs, mrs = svc
    now = time.time()
    mrs.submit(_make_report("n1", 0, 0, [("t1", "Dev", -65)], now))
    assert cs.list_targets(now) == []


def test_list_targets_with_2(svc):
    cs, mrs = svc
    now = time.time()
    mrs.submit(_make_report("n1", 0, 0, [("t1", "Dev", -65)], now))
    mrs.submit(_make_report("n2", 4, 0, [("t1", "Dev", -70)], now))
    targets = cs.list_targets(now)
    assert len(targets) == 1
    assert targets[0][0] == "t1"


def test_compare_empty(svc):
    cs, _ = svc
    assert cs.compare("nonexistent", 5.0, 4.0) == []


def test_compare_with_3_antennas(svc):
    cs, mrs = svc
    now = time.time()
    mrs.submit(_make_report("n1", 0, 0, [("t1", "Dev", -60)], now))
    mrs.submit(_make_report("n2", 4, 0, [("t1", "Dev", -65)], now))
    mrs.submit(_make_report("n3", 2, 3, [("t1", "Dev", -62)], now))
    results = cs.compare("t1", 5.0, 4.0, now)
    assert len(results) > 0
    assert isinstance(results[0], CombinationResult)
    assert results[0].gdop is None or results[0].gdop >= 0


def test_compare_sorted_by_score(svc):
    cs, mrs = svc
    now = time.time()
    mrs.submit(_make_report("n1", 0, 0, [("t1", "Dev", -60)], now))
    mrs.submit(_make_report("n2", 4, 0, [("t1", "Dev", -65)], now))
    mrs.submit(_make_report("n3", 2, 3, [("t1", "Dev", -62)], now))
    results = cs.compare("t1", 5.0, 4.0, now)
    if len(results) >= 2:
        scores = [_score(r.estimate) for r in results]
        assert scores == sorted(scores)


def test_score_missing_gdop():
    from core.models import TargetEstimate
    est = TargetEstimate(target_id="t", name="t", x=1, y=1, gdop=None, uncertainty_radius=None)
    s = _score(est)
    assert s > 1e6


def test_score_good_gdop():
    from core.models import TargetEstimate
    est = TargetEstimate(target_id="t", name="t", x=1, y=1, gdop=1.0, uncertainty_radius=0.5)
    s = _score(est)
    assert s < 20
