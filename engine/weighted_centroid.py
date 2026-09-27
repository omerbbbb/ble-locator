"""Weighted centroid estimator — the simplest possible indoor positioning.

Computes: pos = Σ(anchor_pos / distance) / Σ(1 / distance)

Advantages:
  - Never diverges, always stays inside the convex hull of anchors
  - Works with 1 anchor (returns that anchor's position)
  - Zero tuning parameters
  - Very fast — no optimisation loop

Disadvantages:
  - Biased toward the mean of anchor positions when distances are similar
  - Less accurate than trilateration when geometry is good
  - Good as a stable baseline to compare against
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from core.models import AnchorMeasurement


class WeightedCentroidEstimator:
    def estimate(
        self,
        anchors: List[AnchorMeasurement],
        room_w: Optional[float] = None,
        room_h: Optional[float] = None,
    ) -> Optional[Tuple[float, float]]:
        if not anchors:
            return None
        x_num = y_num = w_sum = 0.0
        for a in anchors:
            w = 1.0 / max(a.distance, 0.01)
            x_num += a.x * w
            y_num += a.y * w
            w_sum += w
        return x_num / w_sum, y_num / w_sum
