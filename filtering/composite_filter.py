"""CompositeFilter — chain several ISignalFilters in sequence.

Each measurement flows through the filters in order, e.g. Hampel (reject
spikes) → Kalman (smooth). Implements ISignalFilter itself, so it drops into
the existing FilterBank factory unchanged. The default factory in main.py is
NOT modified by this file — callers opt in by passing a different factory.
"""

from __future__ import annotations

from typing import List, Optional

from core.interfaces import ISignalFilter


class CompositeFilter:
    def __init__(self, filters: List[ISignalFilter]):
        if not filters:
            raise ValueError("CompositeFilter needs at least one filter")
        self._filters = filters
        self._value: Optional[float] = None

    def filter(self, measurement: float) -> float:
        v = measurement
        for f in self._filters:
            v = f.filter(v)
        self._value = v
        return v

    def reset(self) -> None:
        for f in self._filters:
            f.reset()
        self._value = None

    @property
    def value(self) -> Optional[float]:
        return self._value
