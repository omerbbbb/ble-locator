from typing import Dict, List, Optional

from core.interfaces import ISignalScanner
from core.models import SignalReading


class MultiScanner:
    """Aggregates readings from multiple ISignalScanner instances.

    Implements ISignalScanner itself, so the rest of the system doesn't need
    to know it's talking to more than one radio.
    """

    def __init__(self, scanners: List[ISignalScanner]):
        self._scanners = scanners

    async def start(self) -> None:
        for s in self._scanners:
            await s.start()

    async def stop(self) -> None:
        for s in self._scanners:
            await s.stop()

    def get_active(self, max_age: float = 15.0) -> Dict[str, SignalReading]:
        combined: Dict[str, SignalReading] = {}
        for s in self._scanners:
            combined.update(s.get_active(max_age))
        return combined

    def get_reading(self, device_id: str) -> Optional[SignalReading]:
        for s in self._scanners:
            r = s.get_reading(device_id)
            if r is not None:
                return r
        return None
