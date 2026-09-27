"""Multilateration — locate a TARGET from several antennas.

This is the mirror image of trilateration. In trilateration we know the
anchor positions and solve for OUR position. Here we know the antenna
(receiver) positions and each antenna's distance to a target device, and
we solve for the TARGET's position.

The math is identical (a least-squares circle intersection); only the
meaning of the inputs flips. Works with 2+ antennas — with 2, the room
bounds resolve the usual mirror-image ambiguity.

Pure math. No I/O, no platform code.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
from scipy.optimize import least_squares


class Multilaterator:
    """Locate a single target from multiple (x, y, distance) antenna fixes."""

    def locate(
        self,
        fixes: List[Tuple[float, float, float]],
        room_w: Optional[float] = None,
        room_h: Optional[float] = None,
    ) -> Optional[Tuple[float, float, Optional[float]]]:
        """Return (x, y, uncertainty_radius) or None.

        `fixes` is a list of (antenna_x, antenna_y, distance_to_target).
        Needs at least 2 antennas. With exactly 2, the room bounds keep the
        solver on the in-room intersection.
        """
        if len(fixes) < 2:
            return None

        positions = np.array([[fx, fy] for fx, fy, _ in fixes], dtype=float)
        distances = np.array([d for _, _, d in fixes], dtype=float)

        def residuals(point):
            diffs = positions - point
            return np.sqrt((diffs ** 2).sum(axis=1)) - distances

        # Initial guess: distance-weighted centroid of the antennas.
        weights = 1.0 / (distances + 0.01)
        x0 = float(np.average(positions[:, 0], weights=weights))
        y0 = float(np.average(positions[:, 1], weights=weights))
        if room_w is not None:
            x0 = float(np.clip(x0, 0.0, room_w))
        if room_h is not None:
            y0 = float(np.clip(y0, 0.0, room_h))

        lo = [0.0, 0.0]
        hi = [room_w if room_w is not None else np.inf,
              room_h if room_h is not None else np.inf]

        try:
            result = least_squares(
                residuals, x0=[x0, y0], method="trf", bounds=(lo, hi))
        except Exception:
            return None

        if not (result.success or result.cost < 1e6):
            return None

        unc = self._uncertainty(result, len(fixes))
        return float(result.x[0]), float(result.x[1]), unc

    @staticmethod
    def _uncertainty(result, n_fixes: int) -> Optional[float]:
        try:
            J = result.jac
            dof = max(n_fixes - 2, 1)
            sigma_sq = (result.fun ** 2).sum() / dof
            JtJ = J.T @ J
            cov = sigma_sq * np.linalg.inv(JtJ)
            # 1-sigma positional radius
            return float(np.sqrt(np.trace(cov)))
        except (np.linalg.LinAlgError, ValueError):
            return None
