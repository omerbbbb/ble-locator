import math
import random
import time
from typing import Dict, Optional, Tuple

from core.models import SignalReading, SignalType


class MockScanner:
    """Synthetic RSSI generator — no physical hardware needed.

    Place virtual anchors in a room, set a user position, and get_active()
    returns RSSI readings with configurable Gaussian noise.
    """

    def __init__(
        self,
        anchor_positions: Dict[str, Tuple[float, float]],
        user_position: Tuple[float, float] = (4.0, 3.0),
        tx_power: float = -59.0,
        n: float = 2.5,
        noise_std: float = 3.0,
    ):
        self._anchor_positions = anchor_positions
        self._position = user_position
        self._tx_power = tx_power
        self._n = n
        self._noise_std = noise_std
        self._registry: Dict[str, SignalReading] = {}
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._refresh()

    async def stop(self) -> None:
        self._running = False

    def set_position(self, x: float, y: float):
        self._position = (x, y)
        self._refresh()

    def get_active(self, max_age: float = 15.0) -> Dict[str, SignalReading]:
        self._refresh()
        return dict(self._registry)

    def get_reading(self, device_id: str) -> Optional[SignalReading]:
        return self._registry.get(device_id)

    def _refresh(self):
        now = time.time()
        ux, uy = self._position
        for device_id, (ax, ay) in self._anchor_positions.items():
            dist = math.hypot(ax - ux, ay - uy)
            true_rssi = self._tx_power - 10.0 * self._n * math.log10(max(dist, 0.01))
            noisy_rssi = int(true_rssi + random.gauss(0, self._noise_std))
            self._registry[device_id] = SignalReading(
                device_id=device_id,
                name=f"Mock-{device_id[:6]}",
                rssi=max(noisy_rssi, -120),
                timestamp=now,
                signal_type=SignalType.BLE,
            )
