from core.events import TraceEvent
from traceability.event_bus import EventBus


class _Recorder:
    def __init__(self):
        self.events = []

    def on_event(self, event):
        self.events.append(event)


def test_emit_reaches_listener():
    bus = EventBus()
    rec = _Recorder()
    bus.add_listener(rec)
    bus.emit(TraceEvent(layer="test"))
    assert len(rec.events) == 1
    assert rec.events[0].layer == "test"


def test_remove_listener():
    bus = EventBus()
    rec = _Recorder()
    bus.add_listener(rec)
    bus.remove_listener(rec)
    bus.emit(TraceEvent())
    assert len(rec.events) == 0


def test_multiple_listeners():
    bus = EventBus()
    r1, r2 = _Recorder(), _Recorder()
    bus.add_listener(r1)
    bus.add_listener(r2)
    bus.emit(TraceEvent())
    assert len(r1.events) == 1
    assert len(r2.events) == 1
