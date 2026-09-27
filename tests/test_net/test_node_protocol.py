import time

import pytest

from core.models import NodeObservation, NodeReport, SignalType
from net.node_protocol import (
    ProtocolError,
    decode,
    encode_ack,
    encode_bye,
    encode_hello,
    encode_ping,
    encode_report,
)


def _sample_report():
    obs = NodeObservation(
        target_id="T1", name="Target-1", rssi=-65,
        signal_type=SignalType.BLE, timestamp=time.time(),
    )
    return NodeReport(
        node_id="N1", name="Antenna-1", x=1.0, y=2.0,
        observations=[obs],
    )


def test_hello_roundtrip():
    report = _sample_report()
    raw = encode_hello(report, platform="macOS")
    msg = decode(raw)
    assert msg["type"] == "hello"
    assert msg["node_id"] == "N1"
    assert msg["x"] == 1.0


def test_report_roundtrip():
    report = _sample_report()
    raw = encode_report(report)
    msg = decode(raw)
    assert msg["type"] == "report"
    assert len(msg["observations"]) == 1
    assert msg["observations"][0]["target_id"] == "T1"


def test_bye_encode():
    msg = decode(encode_bye("N1"))
    assert msg["type"] == "bye"


def test_ack_encode():
    msg = decode(encode_ack("N1"))
    assert msg["type"] == "ack"


def test_ping_encode():
    msg = decode(encode_ping())
    assert msg["type"] == "ping"


def test_decode_bad_json():
    with pytest.raises(ProtocolError):
        decode("{bad")


def test_decode_missing_type():
    with pytest.raises(ProtocolError):
        decode('{"v": 1}')
