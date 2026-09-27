"""NLOS (non-line-of-sight) detector for per-device RSSI streams.

Tracks recent RSSI variance over a sliding window. High variance
signals wall reflections or moving obstructions — the path-loss
exponent should be inflated to compensate for the signal bouncing
off surfaces (making the device appear farther than it really is).
"""

from __future__ import annotations

from collections import deque
from typing import Optional


class NLOSDetector:
    VARIANCE_THRESHOLD = 12.0  # dB^2 — higher to avoid false positives in small rooms
    SKEWNESS_THRESHOLD = -0.5
    N_INFLATION_MILD = 1.15
    N_INFLATION_SEVERE = 1.4

    def __init__(self, window: int = 15):
        self._window = max(5, window)
        self._buf: deque[float] = deque(maxlen=self._window)
        self._nlos_level = 0  # 0=LOS, 1=mild, 2=severe

    def feed(self, rssi: float) -> None:
        self._buf.append(rssi)
        if len(self._buf) < 5:
            self._nlos_level = 0
            return
        mean = sum(self._buf) / len(self._buf)
        variance = sum((x - mean) ** 2 for x in self._buf) / len(self._buf)

        skewness = 0.0
        if variance > 0:
            std = variance ** 0.5
            skewness = sum((x - mean) ** 3 for x in self._buf) / (len(self._buf) * std ** 3)

        if variance > self.VARIANCE_THRESHOLD and skewness < self.SKEWNESS_THRESHOLD:
            self._nlos_level = 2
        elif variance > self.VARIANCE_THRESHOLD:
            self._nlos_level = 1
        else:
            self._nlos_level = 0

    @property
    def is_nlos(self) -> bool:
        return self._nlos_level > 0

    def adjusted_n(self, base_n: float) -> float:
        if self._nlos_level == 2:
            return base_n * self.N_INFLATION_SEVERE
        elif self._nlos_level == 1:
            return base_n * self.N_INFLATION_MILD
        return base_n

    def reset(self) -> None:
        self._buf.clear()
        self._nlos_level = 0
