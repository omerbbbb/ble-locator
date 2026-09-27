from __future__ import annotations

from typing import Callable, Dict, List, Optional, Protocol, Tuple, runtime_checkable

from core.events import TraceEvent
from core.models import Anchor, AnchorMeasurement, SignalReading


@runtime_checkable
class ISignalScanner(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def get_active(self, max_age: float = 15.0) -> Dict[str, SignalReading]: ...
    def get_reading(self, device_id: str) -> Optional[SignalReading]: ...


@runtime_checkable
class ISignalFilter(Protocol):
    def filter(self, measurement: float) -> float: ...
    def reset(self) -> None: ...
    @property
    def value(self) -> Optional[float]: ...


@runtime_checkable
class IPositionEstimator(Protocol):
    def estimate(self, anchors: List[AnchorMeasurement]) -> Optional[Tuple[float, float]]: ...


@runtime_checkable
class ICalibrationRepository(Protocol):
    def load(self) -> Dict[str, Anchor]: ...
    def save(self, anchors: Dict[str, Anchor]) -> None: ...


@runtime_checkable
class ITraceListener(Protocol):
    def on_event(self, event: TraceEvent) -> None: ...


@runtime_checkable
class ITraceabilityService(Protocol):
    def emit(self, event: TraceEvent) -> None: ...
    def add_listener(self, listener: ITraceListener) -> None: ...
