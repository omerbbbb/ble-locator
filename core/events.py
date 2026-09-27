from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TraceEvent:
    timestamp: float = field(default_factory=time.time)
    layer: str = ""


@dataclass
class SignalReceivedEvent(TraceEvent):
    device_id: str = ""
    device_name: str = ""
    rssi: int = 0
    layer: str = "sensor"


@dataclass
class SignalFilteredEvent(TraceEvent):
    device_id: str = ""
    raw_rssi: float = 0.0
    filtered_rssi: float = 0.0
    layer: str = "filtering"


@dataclass
class DistanceEstimatedEvent(TraceEvent):
    device_id: str = ""
    filtered_rssi: float = 0.0
    distance: float = 0.0
    tx_power: float = 0.0
    n: float = 0.0
    layer: str = "engine"


@dataclass
class PositionEstimatedEvent(TraceEvent):
    x: float = 0.0
    y: float = 0.0
    num_anchors: int = 0
    layer: str = "engine"


@dataclass
class PositionSmoothedEvent(TraceEvent):
    raw_x: float = 0.0
    raw_y: float = 0.0
    smoothed_x: float = 0.0
    smoothed_y: float = 0.0
    layer: str = "engine"


@dataclass
class NoPositionEvent(TraceEvent):
    reason: str = ""
    num_anchors: int = 0
    layer: str = "engine"
