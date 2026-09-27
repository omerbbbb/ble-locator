import io

from core.events import (
    DistanceEstimatedEvent,
    NoPositionEvent,
    PositionEstimatedEvent,
    PositionSmoothedEvent,
    SignalFilteredEvent,
    SignalReceivedEvent,
    TraceEvent,
)
from traceability.log_explainer import LogExplainer


def test_signal_received():
    buf = io.StringIO()
    le = LogExplainer(output=buf)
    le.on_event(SignalReceivedEvent(
        device_id="AABBCCDD-1234", device_name="Watch", rssi=-65))
    out = buf.getvalue()
    assert "[Sensor]" in out
    assert "Watch" in out
    assert "-65" in out


def test_signal_filtered():
    buf = io.StringIO()
    le = LogExplainer(output=buf)
    le.on_event(SignalFilteredEvent(
        device_id="AABBCCDD-1234", raw_rssi=-70.0, filtered_rssi=-67.5))
    out = buf.getvalue()
    assert "[Filter]" in out
    assert "-70.0" in out
    assert "-67.5" in out


def test_distance_estimated():
    buf = io.StringIO()
    le = LogExplainer(output=buf)
    le.on_event(DistanceEstimatedEvent(
        device_id="AABBCCDD-1234", filtered_rssi=-65.0,
        distance=2.34, tx_power=-59.0, n=2.5))
    out = buf.getvalue()
    assert "[Engine]" in out
    assert "2.34" in out


def test_position_estimated():
    buf = io.StringIO()
    le = LogExplainer(output=buf)
    le.on_event(PositionEstimatedEvent(x=1.5, y=2.3, num_anchors=3))
    out = buf.getvalue()
    assert "1.50" in out
    assert "2.30" in out
    assert "3" in out


def test_position_smoothed():
    buf = io.StringIO()
    le = LogExplainer(output=buf)
    le.on_event(PositionSmoothedEvent(
        raw_x=1.5, raw_y=2.3, smoothed_x=1.48, smoothed_y=2.28))
    out = buf.getvalue()
    assert "Smoothed" in out
    assert "1.48" in out


def test_no_position():
    buf = io.StringIO()
    le = LogExplainer(output=buf)
    le.on_event(NoPositionEvent(reason="not enough anchors", num_anchors=1))
    out = buf.getvalue()
    assert "No position" in out
    assert "1" in out


def test_unknown_event():
    buf = io.StringIO()
    le = LogExplainer(output=buf)
    le.on_event(TraceEvent())
    out = buf.getvalue()
    assert out == ""
