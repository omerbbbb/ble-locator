"""Wire protocol between an antenna and the manager.

Plain JSON messages over a WebSocket. This module is the single source of
truth for the format — the future iPhone (Swift) app must produce the same
JSON. Keep it dependency-free and stable; bump PROTOCOL_VERSION on changes.

Message envelope (every message):
    {"v": 1, "type": "<hello|report|bye|ack|ping|pong>", ...}

hello  (antenna → manager): announces a node and its fixed position.
    {"v":1,"type":"hello","node_id","name","x","y","tx_power","n",
     "platform","is_local":false}

report (antenna → manager): one scan cycle of observations.
    {"v":1,"type":"report","node_id","timestamp",
     "observations":[{"target_id","name","rssi","signal_type",
                      "distance"|null,"timestamp"}, ...]}

bye    (antenna → manager): graceful disconnect.   {"v":1,"type":"bye","node_id"}
ack    (manager → antenna): accepted hello.        {"v":1,"type":"ack","node_id"}
ping/pong: keepalive heartbeat.                    {"v":1,"type":"ping"}
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict

from core.models import NodeObservation, NodeReport, SignalType

PROTOCOL_VERSION = 1
DEFAULT_PORT = 8077
SERVICE_TYPE = "_blelocator._tcp.local."   # mDNS service name


# ── encode ───────────────────────────────────────────────────────────────

def encode_hello(report: NodeReport, platform: str = "") -> str:
    return json.dumps({
        "v": PROTOCOL_VERSION,
        "type": "hello",
        "node_id": report.node_id,
        "name": report.name,
        "x": report.x,
        "y": report.y,
        "tx_power": report.tx_power,
        "n": report.n,
        "platform": platform,
        "is_local": report.is_local,
    })


def encode_report(report: NodeReport) -> str:
    return json.dumps({
        "v": PROTOCOL_VERSION,
        "type": "report",
        "node_id": report.node_id,
        "timestamp": report.timestamp,
        "observations": [_obs_to_dict(o) for o in report.observations],
    })


def encode_bye(node_id: str) -> str:
    return json.dumps({"v": PROTOCOL_VERSION, "type": "bye", "node_id": node_id})


def encode_ack(node_id: str) -> str:
    return json.dumps({"v": PROTOCOL_VERSION, "type": "ack", "node_id": node_id})


def encode_ping() -> str:
    return json.dumps({"v": PROTOCOL_VERSION, "type": "ping"})


def encode_pong() -> str:
    return json.dumps({"v": PROTOCOL_VERSION, "type": "pong"})


def _obs_to_dict(o: NodeObservation) -> Dict[str, Any]:
    return {
        "target_id": o.target_id,
        "name": o.name,
        "rssi": o.rssi,
        "signal_type": o.signal_type.value,
        "distance": o.distance,
        "timestamp": o.timestamp,
    }


# ── decode ───────────────────────────────────────────────────────────────

class ProtocolError(ValueError):
    pass


def decode(raw: str) -> Dict[str, Any]:
    """Parse a message envelope. Raises ProtocolError on malformed input."""
    try:
        msg = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        raise ProtocolError(f"bad json: {e}") from e
    if not isinstance(msg, dict) or "type" not in msg:
        raise ProtocolError("missing message type")
    return msg


def _signal_type(value: str) -> SignalType:
    try:
        return SignalType(value)
    except ValueError:
        return SignalType.UNKNOWN


def report_from_hello(msg: Dict[str, Any]) -> NodeReport:
    """Build an (observation-less) NodeReport carrying a node's identity/pos."""
    return NodeReport(
        node_id=str(msg["node_id"]),
        name=str(msg.get("name", msg["node_id"])),
        x=float(msg.get("x", 0.0)),
        y=float(msg.get("y", 0.0)),
        tx_power=float(msg.get("tx_power", -59.0)),
        n=float(msg.get("n", 2.5)),
        is_local=bool(msg.get("is_local", False)),
    )


def observations_from_report(msg: Dict[str, Any]) -> list[NodeObservation]:
    now = time.time()
    out = []
    for o in msg.get("observations", []):
        ts = float(o.get("timestamp") or 0.0) or now
        out.append(NodeObservation(
            target_id=str(o["target_id"]),
            name=str(o.get("name", o["target_id"])),
            rssi=int(o.get("rssi", -100)),
            signal_type=_signal_type(o.get("signal_type", "ble")),
            distance=(float(o["distance"]) if o.get("distance") is not None else None),
            timestamp=ts,
        ))
    return out
