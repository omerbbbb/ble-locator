from typing import List

from core.events import TraceEvent
from core.interfaces import ITraceListener


class EventBus:
    def __init__(self):
        self._listeners: List[ITraceListener] = []

    def emit(self, event: TraceEvent) -> None:
        for listener in self._listeners:
            listener.on_event(event)

    def add_listener(self, listener: ITraceListener) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: ITraceListener) -> None:
        self._listeners.remove(listener)
