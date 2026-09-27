"""Moving median pre-filter for RSSI streams.

More robust than a moving average for multipath spikes — a single
outlier cannot drag the output. Window of 5 balances responsiveness
and robustness for short-range indoor BLE.
"""

from __future__ import annotations

from collections import deque
from statistics import median
from typing import Optional


class MedianFilter:
    def __init__(self, window: int = 5):
        self._window = max(3, window)
        self._buf: deque[float] = deque(maxlen=self._window)
        self._value: Optional[float] = None

    def filter(self, measurement: float) -> float:
        self._buf.append(measurement)
        self._value = median(self._buf)
        return self._value

    def reset(self) -> None:
        self._buf.clear()
        self._value = None

    @property
    def value(self) -> Optional[float]:
        return self._value
