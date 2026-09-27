import json
import time

import pytest

from core.models import NodeObservation, NodeReport, SignalType
from net.node_protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    decode,
    encode_ack,
    encode_bye,
    encode_hello,
    encode_ping,
    encode_pong,
    encode_report,
    observations_from_report,
    report_from_hello,
    _signal_type,
)


def _sample_report():
    now = time.time()
    return NodeReport(
        node_id="iphone-1",
        name="iPhone",
        x=1.5,
        y=2.5,
        observations=[
            NodeObservation(
                target_id="t1", name="Watch", rssi=-65,
                signal_type=SignalType.BLE, timestamp=now,
            ),
            NodeObservation(
                target_id="t2", name="Speaker", rssi=-70,
                signal_type=SignalType.WIFI, distance=3.5, timestamp=now,
            ),
        ],
        tx_power=-55.0,
        n=2.8,
        timestamp=now,
    )


def test_encode_pong():
    raw = encode_pong()
    msg = json.loads(raw)
    assert msg["type"] == "pong"
    assert msg["v"] == PROTOCOL_VERSION


def test_report_encode_decode():
    report = _sample_report()
    raw = encode_report(report)
    msg = decode(raw)
    assert msg["type"] == "report"
    assert msg["node_id"] == "iphone-1"
    assert len(msg["observations"]) == 2


def test_observations_from_report_roundtrip():
    report = _sample_report()
    raw = encode_report(report)
    msg = decode(raw)
    obs = observations_from_report(msg)
    assert len(obs) == 2
    assert obs[0].target_id == "t1"
    assert obs[0].rssi == -65
    assert obs[1].distance == 3.5
    assert obs[1].signal_type == SignalType.WIFI


def test_observations_from_report_missing_timestamp():
    msg = {
        "type": "report",
        "observations": [
            {"target_id": "t1", "name": "Dev", "rssi": -60, "signal_type": "ble"},
        ],
    }
    obs = observations_from_report(msg)
    assert len(obs) == 1
    assert obs[0].timestamp > 0


def test_observations_from_report_empty():
    msg = {"type": "report", "observations": []}
    obs = observations_from_report(msg)
    assert obs == []


def test_report_from_hello_full():
    msg = {
        "type": "hello",
        "node_id": "n1",
        "name": "My Phone",
        "x": 1.0,
        "y": 2.0,
        "tx_power": -55.0,
        "n": 3.0,
        "is_local": True,
    }
    r = report_from_hello(msg)
    assert r.node_id == "n1"
    assert r.name == "My Phone"
    assert r.x == 1.0
    assert r.tx_power == -55.0
    assert r.is_local is True


def test_report_from_hello_defaults():
    msg = {"type": "hello", "node_id": "n1"}
    r = report_from_hello(msg)
    assert r.name == "n1"
    assert r.x == 0.0
    assert r.tx_power == -59.0
    assert r.n == 2.5
    assert r.is_local is False


def test_signal_type_valid():
    assert _signal_type("ble") == SignalType.BLE
    assert _signal_type("wifi") == SignalType.WIFI
    assert _signal_type("uwb") == SignalType.UWB


def test_signal_type_invalid():
    assert _signal_type("zigbee") == SignalType.UNKNOWN
    assert _signal_type("") == SignalType.UNKNOWN


def test_decode_not_dict():
    with pytest.raises(ProtocolError):
        decode('"just a string"')


def test_decode_list():
    with pytest.raises(ProtocolError):
        decode('[1, 2, 3]')
