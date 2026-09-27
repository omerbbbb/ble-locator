from core.models import (
    Anchor,
    AnchorMeasurement,
    DeviceEstimate,
    EstimationMode,
    NodeObservation,
    NodeReport,
    PositionResult,
    SignalReading,
    SignalType,
    TargetEstimate,
    display_name,
)


def test_signal_type_values():
    assert SignalType.BLE.value == "ble"
    assert SignalType.WIFI.value == "wifi"
    assert SignalType.UWB.value == "uwb"
    assert SignalType.UNKNOWN.value == "unknown"


def test_estimation_mode_values():
    assert EstimationMode.TRILATERATION.value == "trilateration"
    assert EstimationMode.PARTICLE.value == "particle"
    assert EstimationMode.FUSION.value == "fusion"
    assert EstimationMode.ENSEMBLE.value == "ensemble"
    assert EstimationMode.CENTROID.value == "centroid"


def test_signal_reading_defaults():
    sr = SignalReading(device_id="d1", name="Dev")
    assert sr.rssi == -100
    assert sr.signal_type == SignalType.BLE
    assert sr.distance is None
    assert sr.timestamp > 0


def test_anchor_defaults():
    a = Anchor(device_id="a1", name="Anchor")
    assert a.tx_power == -59.0
    assert a.n == 2.5
    assert a.x == 0.0


def test_node_observation_with_distance():
    o = NodeObservation(target_id="t1", name="t", distance=2.5)
    assert o.distance == 2.5
    assert o.rssi == -100


def test_node_report_defaults():
    r = NodeReport(node_id="n1", name="N", x=0, y=0)
    assert r.observations == []
    assert r.tx_power == -59.0
    assert r.is_local is False


def test_target_estimate():
    te = TargetEstimate(
        target_id="t1", name="Dev", x=1.0, y=2.0,
        num_nodes=3, gdop=1.5, contributing_nodes=("n1", "n2", "n3"),
    )
    assert te.num_nodes == 3
    assert te.gdop == 1.5


def test_display_name_with_name():
    assert display_name("abc", "Watch") == "Watch"


def test_display_name_unknown():
    result = display_name("abc-def-123", None)
    assert "Unnamed" in result


def test_display_name_with_manufacturer():
    result = display_name("abc-def", None, manufacturer="Apple")
    assert "Apple" in result


def test_display_name_unknown_name():
    result = display_name("abc", "Unknown", manufacturer="Sony")
    assert "Sony" in result
