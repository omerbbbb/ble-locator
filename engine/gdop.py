"""GDOP — Geometric Dilution of Precision.

Given the antenna positions and an estimated target position, GDOP measures
how the *geometry* amplifies ranging error into position error. Low GDOP
(good): antennas surround the target from varied angles. High GDOP (bad):
antennas are nearly collinear or clustered, so small distance errors blow up
into large position errors.

Used to (a) reject hopeless geometries and (b) rank antenna combinations.

Pure math.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np


def gdop(
    antennas: List[Tuple[float, float]],
    target: Tuple[float, float],
) -> Optional[float]:
    """Return the GDOP scalar, or None if the geometry is degenerate.

    Smaller is better. ≲2 is good, 2–5 usable, >5 poor, >10 unreliable.
    """
    if len(antennas) < 2:
        return None

    rows = []
    for ax, ay in antennas:
        dx = target[0] - ax
        dy = target[1] - ay
        d = math.hypot(dx, dy)
        if d < 1e-6:
            continue
        rows.append([dx / d, dy / d])

    if len(rows) < 2:
        return None

    G = np.array(rows)
    try:
        cov = np.linalg.inv(G.T @ G)
    except np.linalg.LinAlgError:
        return None  # collinear → singular

    trace = float(np.trace(cov))
    if trace <= 0 or not math.isfinite(trace):
        return None
    return math.sqrt(trace)


def is_usable_geometry(
    antennas: List[Tuple[float, float]],
    target: Tuple[float, float],
    max_gdop: float = 10.0,
) -> bool:
    g = gdop(antennas, target)
    return g is not None and g <= max_gdop
