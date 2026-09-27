"""WLS Multilaterator — locate a target with per-antenna reliability weights.

Same geometry as engine/multilateration.Multilaterator, but each fix carries a
weight reflecting how much to trust that antenna (stable, strong signal → high
weight; weak/erratic → low weight). The residual for each antenna is scaled by
sqrt(weight), so the solver leans on the trustworthy antennas.

Kept as a SEPARATE class so the plain Multilaterator keeps behaving identically.

Pure math.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
from scipy.optimize import least_squares


class WlsMultilaterator:
    def locate(
        self,
        fixes: List[Tuple[float, float, float, float]],
        room_w: Optional[float] = None,
        room_h: Optional[float] = None,
    ) -> Optional[Tuple[float, float, Optional[float]]]:
        """`fixes` = list of (antenna_x, antenna_y, distance, weight).

        Returns (x, y, uncertainty_radius) or None. Needs ≥2 fixes.
        """
        if len(fixes) < 2:
            return None

        positions = np.array([[fx, fy] for fx, fy, _, _ in fixes], dtype=float)
        distances = np.array([d for _, _, d, _ in fixes], dtype=float)
        weights = np.array([max(w, 1e-6) for _, _, _, w in fixes], dtype=float)
        sqrt_w = np.sqrt(weights)

        def residuals(point):
            diffs = positions - point
            pred = np.sqrt((diffs ** 2).sum(axis=1))
            return sqrt_w * (pred - distances)

        # weighted initial guess
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

        return float(result.x[0]), float(result.x[1]), self._uncertainty(result, len(fixes))

    @staticmethod
    def _uncertainty(result, n_fixes: int) -> Optional[float]:
        try:
            J = result.jac
            dof = max(n_fixes - 2, 1)
            sigma_sq = (result.fun ** 2).sum() / dof
            cov = sigma_sq * np.linalg.inv(J.T @ J)
            return float(np.sqrt(np.trace(cov)))
        except (np.linalg.LinAlgError, ValueError):
            return None
