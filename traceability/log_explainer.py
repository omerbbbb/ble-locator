import sys
from typing import TextIO

from core.events import (
    DistanceEstimatedEvent,
    NoPositionEvent,
    PositionEstimatedEvent,
    PositionSmoothedEvent,
    SignalFilteredEvent,
    SignalReceivedEvent,
    TraceEvent,
)


class LogExplainer:
    """Translates system events into human-readable text.

    Output goes to any file-like object (stdout, a log file, or a UI widget
    that implements write()).
    """

    def __init__(self, output: TextIO = sys.stdout):
        self._out = output

    def on_event(self, event: TraceEvent) -> None:
        msg = self._format(event)
        if msg:
            self._out.write(msg + "\n")
            self._out.flush()

    def _format(self, event: TraceEvent) -> str:
        if isinstance(event, SignalReceivedEvent):
            return (
                f"[Sensor]  Received signal from '{event.device_name}' "
                f"(ID: {event.device_id[:8]}..): RSSI = {event.rssi} dBm"
            )
        if isinstance(event, SignalFilteredEvent):
            return (
                f"[Filter]  Device {event.device_id[:8]}..  "
                f"raw={event.raw_rssi:.1f} → filtered={event.filtered_rssi:.1f} dBm"
            )
        if isinstance(event, DistanceEstimatedEvent):
            return (
                f"[Engine]  Device {event.device_id[:8]}..  "
                f"RSSI={event.filtered_rssi:.1f} → distance={event.distance:.2f} m  "
                f"(tx={event.tx_power}, n={event.n})"
            )
        if isinstance(event, PositionEstimatedEvent):
            return (
                f"[Engine]  Position estimated: ({event.x:.2f}, {event.y:.2f})  "
                f"using {event.num_anchors} anchors"
            )
        if isinstance(event, PositionSmoothedEvent):
            return (
                f"[Engine]  Smoothed: ({event.raw_x:.2f},{event.raw_y:.2f}) "
                f"→ ({event.smoothed_x:.2f},{event.smoothed_y:.2f})"
            )
        if isinstance(event, NoPositionEvent):
            return (
                f"[Engine]  No position: {event.reason}  "
                f"({event.num_anchors} anchors available)"
            )
        return ""
