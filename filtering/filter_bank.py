from typing import Callable, Dict, Optional

from core.interfaces import ISignalFilter


class FilterBank:
    """Manages one ISignalFilter per device, created on demand via a factory."""

    def __init__(self, filter_factory: Callable[[], ISignalFilter]):
        self._factory = filter_factory
        self._filters: Dict[str, ISignalFilter] = {}

    def apply(self, device_id: str, measurement: float) -> float:
        if device_id not in self._filters:
            self._filters[device_id] = self._factory()
        return self._filters[device_id].filter(measurement)

    def reset_device(self, device_id: str):
        filt = self._filters.get(device_id)
        if filt is not None:
            filt.reset()

    def reset_all(self):
        for filt in self._filters.values():
            filt.reset()
        self._filters.clear()

    def retain(self, active_ids):
        """Drop per-device filters whose id is not in active_ids (bound memory)."""
        for device_id in [d for d in self._filters if d not in active_ids]:
            del self._filters[device_id]
