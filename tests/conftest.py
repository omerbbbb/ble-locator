from __future__ import annotations

from typing import Dict

import pytest

from core.models import Anchor, AnchorMeasurement, SignalReading, SignalType


class InMemoryCalibrationRepository:
    def __init__(self, initial: Dict[str, Anchor] | None = None):
        self._data: Dict[str, Anchor] = dict(initial or {})

    def load(self) -> Dict[str, Anchor]:
        return dict(self._data)

    def save(self, anchors: Dict[str, Anchor]) -> None:
        self._data = dict(anchors)


@pytest.fixture
def sample_anchors() -> Dict[str, Anchor]:
    return {
        "A1": Anchor("A1", "Anchor-1", tx_power=-59.0, n=2.5, x=0.0, y=0.0),
        "A2": Anchor("A2", "Anchor-2", tx_power=-59.0, n=2.5, x=4.0, y=0.0),
        "A3": Anchor("A3", "Anchor-3", tx_power=-59.0, n=2.5, x=2.0, y=3.0),
    }


@pytest.fixture
def sample_measurements() -> list[AnchorMeasurement]:
    return [
        AnchorMeasurement(x=0.0, y=0.0, distance=2.0),
        AnchorMeasurement(x=4.0, y=0.0, distance=2.5),
        AnchorMeasurement(x=2.0, y=3.0, distance=1.5),
    ]


@pytest.fixture
def sample_readings() -> Dict[str, SignalReading]:
    import time
    now = time.time()
    return {
        "A1": SignalReading("A1", "Anchor-1", rssi=-65, timestamp=now),
        "A2": SignalReading("A2", "Anchor-2", rssi=-70, timestamp=now),
        "A3": SignalReading("A3", "Anchor-3", rssi=-62, timestamp=now),
    }


@pytest.fixture
def in_memory_repo(sample_anchors):
    return InMemoryCalibrationRepository(sample_anchors)
