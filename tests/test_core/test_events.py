from core.events import (
    DistanceEstimatedEvent,
    NoPositionEvent,
    PositionEstimatedEvent,
    PositionSmoothedEvent,
    SignalFilteredEvent,
    SignalReceivedEvent,
    TraceEvent,
)


def test_trace_event_defaults():
    e = TraceEvent()
    assert e.timestamp > 0
    assert e.layer == ""


def test_signal_received():
    e = SignalReceivedEvent(device_id="d1", device_name="Dev", rssi=-65)
    assert e.layer == "sensor"
    assert e.rssi == -65


def test_signal_filtered():
    e = SignalFilteredEvent(device_id="d1", raw_rssi=-70.0, filtered_rssi=-67.0)
    assert e.layer == "filtering"


def test_distance_estimated():
    e = DistanceEstimatedEvent(
        device_id="d1", filtered_rssi=-65.0, distance=2.0, tx_power=-59.0, n=2.5)
    assert e.layer == "engine"
    assert e.distance == 2.0


def test_position_estimated():
    e = PositionEstimatedEvent(x=1.0, y=2.0, num_anchors=3)
    assert e.layer == "engine"


def test_position_smoothed():
    e = PositionSmoothedEvent(
        raw_x=1.0, raw_y=2.0, smoothed_x=1.1, smoothed_y=2.1)
    assert e.layer == "engine"


def test_no_position():
    e = NoPositionEvent(reason="no anchors", num_anchors=0)
    assert e.layer == "engine"
    assert e.reason == "no anchors"
