"""Hampel filter — robust outlier (spike) removal for an RSSI stream.

Keeps a sliding window, and replaces any sample that deviates from the window
median by more than `n_sigmas` robust standard deviations (estimated from the
Median Absolute Deviation) with the median. Unlike a mean filter it does not
let a single huge spike drag the output, and unlike Kalman it actively rejects
outliers rather than smoothing them in. Implements ISignalFilter so it slots
into the existing FilterBank.
"""

from __future__ import annotations

from collections import deque
from statistics import median
from typing import Optional

# MAD → std for normally distributed data
_MAD_TO_SIGMA = 1.4826


class HampelFilter:
    def __init__(self, window: int = 7, n_sigmas: float = 3.0):
        self._window = max(3, window)
        self._n = n_sigmas
        self._buf: deque[float] = deque(maxlen=self._window)
        self._value: Optional[float] = None

    def filter(self, measurement: float) -> float:
        self._buf.append(measurement)
        if len(self._buf) < 3:
            self._value = measurement
            return measurement

        med = median(self._buf)
        mad = median([abs(x - med) for x in self._buf])
        sigma = _MAD_TO_SIGMA * mad

        if sigma > 0 and abs(measurement - med) > self._n * sigma:
            out = med            # spike → replace with the robust centre
        else:
            out = measurement

        self._value = out
        return out

    def reset(self) -> None:
        self._buf.clear()
        self._value = None

    @property
    def value(self) -> Optional[float]:
        return self._value
