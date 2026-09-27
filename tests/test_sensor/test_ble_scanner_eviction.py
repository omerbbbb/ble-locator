import time

from core.models import SignalReading
from sensor.ble_scanner import BLEScannerImpl


def test_get_active_evicts_long_dead_entries():
    scanner = BLEScannerImpl()
    now = time.time()
    scanner._registry = {
        "fresh": SignalReading("fresh", "f", rssi=-60, timestamp=now),
        "recent": SignalReading("recent", "r", rssi=-70, timestamp=now - 20),
        "dead": SignalReading("dead", "d", rssi=-80,
                              timestamp=now - (BLEScannerImpl.EVICT_AGE + 10)),
    }
    active = scanner.get_active(max_age=15.0)
    # Only the fresh one is "active" for display.
    assert set(active) == {"fresh"}
    # The long-dead entry is purged from the registry entirely (bounded memory).
    assert "dead" not in scanner._registry
    # The merely-stale-but-not-ancient one is kept for later.
    assert "recent" in scanner._registry
