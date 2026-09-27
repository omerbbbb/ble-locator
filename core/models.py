from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class SignalType(Enum):
    BLE = "ble"
    WIFI = "wifi"
    UWB = "uwb"
    UNKNOWN = "unknown"


class EstimationMode(Enum):
    TRILATERATION = "trilateration"  # Least Squares only
    PARTICLE = "particle"            # Particle Filter only
    FUSION = "fusion"                # Trilateration + Particle Filter weighted
    ENSEMBLE = "ensemble"            # All three: Trilateration + PF + Centroid
    CENTROID = "centroid"            # Weighted Centroid only


@dataclass
class SignalReading:
    device_id: str
    name: str
    rssi: int = -100
    timestamp: float = field(default_factory=time.time)
    signal_type: SignalType = SignalType.BLE
    manufacturer: str = ""
    service_uuids: Tuple[str, ...] = ()
    tx_power_adv: Optional[int] = None
    channel: Optional[int] = None
    frequency_mhz: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    # Pre-measured distance (metres) — set by hardware that provides ranging directly
    # (e.g. UWB, ultrasound). When set, RSSI→distance conversion is skipped entirely.
    distance: Optional[float] = None


@dataclass
class Anchor:
    device_id: str
    name: str
    tx_power: float = -59.0
    n: float = 2.5
    x: float = 0.0
    y: float = 0.0
    signal_type: SignalType = SignalType.BLE


@dataclass
class AnchorMeasurement:
    x: float
    y: float
    distance: float


# ── Multi-receiver ("remote antenna") layer ──────────────────────────────
# A SensorNode is any antenna that reports what it sees: the local computer,
# an iPhone app, an ESP32, etc. Each node has a known position in the room
# and contributes observations of the targets around it. The engine fuses
# observations of the same target across nodes to triangulate that target.

@dataclass
class NodeObservation:
    """One node's view of one target device."""
    target_id: str
    name: str
    rssi: int = -100
    signal_type: SignalType = SignalType.BLE
    # Direct hardware distance (UWB/ultrasound). When set, RSSI is not used.
    distance: Optional[float] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class NodeReport:
    """What a single antenna sends to the computer each scan cycle."""
    node_id: str
    name: str
    x: float
    y: float
    observations: List[NodeObservation] = field(default_factory=list)
    # Per-node radio calibration (so each antenna can have its own model).
    tx_power: float = -59.0
    n: float = 2.5
    timestamp: float = field(default_factory=time.time)
    is_local: bool = False


@dataclass
class TargetEstimate:
    """A device located by fusing observations from multiple nodes."""
    target_id: str
    name: str
    x: float
    y: float
    signal_type: SignalType = SignalType.BLE
    num_nodes: int = 0              # how many antennas saw it
    uncertainty_radius: Optional[float] = None
    gdop: Optional[float] = None             # geometry quality (lower = better)
    contributing_nodes: Tuple[str, ...] = () # which antennas located it


@dataclass
class DeviceEstimate:
    device_id: str
    name: str
    raw_rssi: float
    filtered_rssi: float
    distance: float
    is_anchor: bool
    signal_type: SignalType = SignalType.BLE
    angle: Optional[float] = None


@dataclass
class PositionResult:
    devices: List[DeviceEstimate]
    anchors_ui: Dict[str, Tuple[float, float, str]]
    distances: Dict[str, float]
    position: Optional[Tuple[float, float]]
    status: str
    uncertainty_radius: Optional[float] = None
    uncertainty_ellipse: Optional[Tuple[float, float, float]] = None
    # Particle filter output — None when mode is TRILATERATION
    particles: Optional[Any] = None         # np.ndarray shape (N, 2)
    particle_weights: Optional[Any] = None  # np.ndarray shape (N,)
    particle_spread: Optional[float] = None
    estimation_mode: str = "trilateration"


def display_name(device_id: str, name: Optional[str], manufacturer: str = "") -> str:
    if name and name != "Unknown":
        return name
    if manufacturer:
        return f"{manufacturer} ({device_id.replace('-', '')[:6].upper()})"
    return f"Unnamed ({device_id.replace('-', '')[:6].upper()})"
