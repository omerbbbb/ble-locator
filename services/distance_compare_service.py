"""Distance A/B — estimate each device's distance two ways for comparison.

Column A uses an **Adaptive Kalman filter only**; column B uses the **full
chain** (Median → Hampel → Kalman) the app normally runs. Both convert the
filtered RSSI to a distance with the *same* per-device calibration and the same
room clamp, so the only difference the user sees is the RSSI filter itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from core.models import SignalReading, display_name
from engine.distance import rssi_to_distance, tx_reference
from filtering.adaptive_kalman import AdaptiveKalmanFilter
from filtering.composite_filter import CompositeFilter
from filtering.filter_bank import FilterBank
from filtering.hampel_filter import HampelFilter
from filtering.median_filter import MedianFilter
from services.anchor_store import AnchorStore

DEFAULT_N = 2.5
DEFAULT_TX = -59.0


@dataclass
class DistanceRow:
    device_id: str
    name: str
    rssi: int
    d_kalman: float
    d_full: float


class DistanceCompareService:
    def __init__(self, anchors: AnchorStore):
        self._anchors = anchors
        self._kalman = FilterBank(AdaptiveKalmanFilter)
        self._full = FilterBank(lambda: CompositeFilter([
            MedianFilter(5),
            HampelFilter(7, 2.5),
            AdaptiveKalmanFilter(),
        ]))

    def update(
        self,
        readings: Dict[str, SignalReading],
        room_w: float,
        room_h: float,
    ) -> List[DistanceRow]:
        rows: List[DistanceRow] = []
        for device_id, reading in readings.items():
            raw = reading.rssi
            anchor = self._anchors.get(device_id)
            tx = tx_reference(
                anchor.tx_power if anchor is not None else None,
                reading.tx_power_adv,
                DEFAULT_TX,
            )
            n = anchor.n if anchor is not None else DEFAULT_N

            fk = self._kalman.apply(device_id, raw)
            ff = self._full.apply(device_id, raw)
            d_kalman = rssi_to_distance(fk, tx, n)
            d_full = rssi_to_distance(ff, tx, n)

            rows.append(DistanceRow(
                device_id=device_id,
                name=display_name(device_id, reading.name,
                                  getattr(reading, 'manufacturer', '')),
                rssi=raw,
                d_kalman=d_kalman,
                d_full=d_full,
            ))

        # Bound memory: keep filter state only for devices still present.
        keep = set(readings.keys())
        self._kalman.retain(keep)
        self._full.retain(keep)

        return rows

    def reset(self):
        self._kalman.reset_all()
        self._full.reset_all()
