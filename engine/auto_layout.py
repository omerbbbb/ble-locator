"""Auto-layout — solve device positions from pairwise BLE distances + hints.

Instead of manually placing each anchor at exact (x,y) coordinates, the user
gives rough direction hints ("Apple Watch is to my upper-left") and the system
computes actual positions from measured RSSI distances.

Algorithm:
1. Fix the Mac (manager) at the room centre.
2. For each device with a direction hint, place an initial guess along that
   direction at the measured distance.
3. Run least-squares optimisation minimising the difference between predicted
   pairwise distances and measured pairwise distances.
4. Clamp results inside room bounds.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import least_squares

# Direction hint → unit vector angle (radians, 0 = right, pi/2 = down in room)
DIRECTION_ANGLES: Dict[str, float] = {
    "right":       0.0,
    "lower-right": math.pi / 4,
    "below":       math.pi / 2,
    "lower-left":  3 * math.pi / 4,
    "left":        math.pi,
    "upper-left":  5 * math.pi / 4,
    "above":       3 * math.pi / 2,
    "upper-right": 7 * math.pi / 4,
}


class PairwiseDistance:
    __slots__ = ("id_a", "id_b", "distance", "weight")

    def __init__(self, id_a: str, id_b: str, distance: float, weight: float = 1.0):
        self.id_a = id_a
        self.id_b = id_b
        self.distance = distance
        self.weight = weight


class DirectionHint:
    __slots__ = ("device_id", "direction", "angle")

    def __init__(self, device_id: str, direction: str):
        self.device_id = device_id
        self.direction = direction
        self.angle = DIRECTION_ANGLES.get(direction, 0.0)


class AutoLayoutResult:
    __slots__ = ("positions", "residual")

    def __init__(self, positions: Dict[str, Tuple[float, float]], residual: float):
        self.positions = positions
        self.residual = residual


def solve_layout(
    self_id: str,
    pairwise: List[PairwiseDistance],
    hints: Dict[str, DirectionHint],
    room_w: float,
    room_h: float,
) -> Optional[AutoLayoutResult]:
    """Compute 2D positions from pairwise distances + direction hints.

    *self_id* is fixed at room centre.  Every other device gets an initial
    guess from its hint direction + measured distance to self, then a
    least-squares solver minimises the total pairwise-distance error.
    """
    device_ids = _collect_ids(self_id, pairwise)
    if len(device_ids) < 2:
        return None

    id_to_idx = {did: i for i, did in enumerate(device_ids)}
    n = len(device_ids)
    self_idx = id_to_idx[self_id]
    cx, cy = room_w / 2.0, room_h / 2.0

    # Build initial positions
    x0 = np.zeros(n * 2)
    x0[self_idx * 2] = cx
    x0[self_idx * 2 + 1] = cy

    dist_to_self = _distances_from(self_id, pairwise)

    for did in device_ids:
        if did == self_id:
            continue
        idx = id_to_idx[did]
        d = dist_to_self.get(did, 1.5)
        hint = hints.get(did)
        if hint is not None:
            angle = hint.angle
        else:
            angle = (idx - self_idx) * (2 * math.pi / max(n - 1, 1))
        x0[idx * 2] = np.clip(cx + d * math.cos(angle), 0.05, room_w - 0.05)
        x0[idx * 2 + 1] = np.clip(cy + d * math.sin(angle), 0.05, room_h - 0.05)

    # Build pair indices + target distances + weights
    pair_a, pair_b, target_d, w = [], [], [], []
    for p in pairwise:
        ia = id_to_idx.get(p.id_a)
        ib = id_to_idx.get(p.id_b)
        if ia is None or ib is None:
            continue
        pair_a.append(ia)
        pair_b.append(ib)
        target_d.append(p.distance)
        w.append(p.weight)

    if not pair_a:
        return None

    pair_a = np.array(pair_a)
    pair_b = np.array(pair_b)
    target_d = np.array(target_d)
    sqrt_w = np.sqrt(np.array(w))

    def residuals(params):
        pts = params.reshape(-1, 2)
        dx = pts[pair_a, 0] - pts[pair_b, 0]
        dy = pts[pair_a, 1] - pts[pair_b, 1]
        pred = np.sqrt(dx ** 2 + dy ** 2)
        return sqrt_w * (pred - target_d)

    lo = np.zeros(n * 2)
    hi = np.full(n * 2, max(room_w, room_h))
    for i in range(n):
        hi[i * 2] = room_w
        hi[i * 2 + 1] = room_h
    # Pin self at centre
    lo[self_idx * 2] = cx - 0.01
    hi[self_idx * 2] = cx + 0.01
    lo[self_idx * 2 + 1] = cy - 0.01
    hi[self_idx * 2 + 1] = cy + 0.01

    try:
        result = least_squares(residuals, x0, method="trf", bounds=(lo, hi))
    except Exception:
        return None

    pts = result.x.reshape(-1, 2)
    positions = {did: (float(pts[i, 0]), float(pts[i, 1]))
                 for did, i in id_to_idx.items()}
    return AutoLayoutResult(positions, float(result.cost))


def _collect_ids(self_id: str, pairwise: List[PairwiseDistance]) -> List[str]:
    seen = {self_id}
    order = [self_id]
    for p in pairwise:
        for did in (p.id_a, p.id_b):
            if did not in seen:
                seen.add(did)
                order.append(did)
    return order


def _distances_from(
    device_id: str, pairwise: List[PairwiseDistance]
) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for p in pairwise:
        if p.id_a == device_id:
            out[p.id_b] = p.distance
        elif p.id_b == device_id:
            out[p.id_a] = p.distance
    return out
