from typing import List, Optional, Tuple

import numpy as np
from scipy.optimize import least_squares

from core.models import AnchorMeasurement


class TrilaterationEstimator:
    def __init__(self):
        self._last_uncertainty_radius: Optional[float] = None
        self._last_uncertainty_ellipse: Optional[Tuple[float, float, float]] = None

    def estimate(
        self,
        anchors: List[AnchorMeasurement],
        room_w: Optional[float] = None,
        room_h: Optional[float] = None,
    ) -> Optional[Tuple[float, float]]:
        if len(anchors) < 3:
            self._last_uncertainty_radius = None
            self._last_uncertainty_ellipse = None
            return None

        positions = np.array([[a.x, a.y] for a in anchors])
        distances = np.array([a.distance for a in anchors])

        def residuals(point):
            diffs = positions - point
            return np.sqrt((diffs ** 2).sum(axis=1)) - distances

        weights = 1.0 / (distances + 0.01)
        x0 = np.average(positions[:, 0], weights=weights)
        y0 = np.average(positions[:, 1], weights=weights)

        # Clamp initial guess inside room so solver starts in a valid region.
        if room_w is not None:
            x0 = float(np.clip(x0, 0.0, room_w))
        if room_h is not None:
            y0 = float(np.clip(y0, 0.0, room_h))

        # Use TRF (Trust Region Reflective) so we can pass hard room bounds.
        # LM doesn't support bounds. TRF keeps the solver inside the room,
        # which prevents the ellipse from blowing up outside the walls.
        lo = [0.0, 0.0]
        hi = [room_w if room_w is not None else np.inf,
              room_h if room_h is not None else np.inf]
        result = least_squares(residuals, x0=[x0, y0], method="trf", bounds=(lo, hi))
        if not (result.success or result.cost < 1e6):
            self._last_uncertainty_radius = None
            self._last_uncertainty_ellipse = None
            return None

        self._compute_uncertainty(result, len(anchors))
        return float(result.x[0]), float(result.x[1])

    def _compute_uncertainty(self, result, n_anchors: int):
        try:
            J = result.jac
            n_params = 2
            dof = max(n_anchors - n_params, 1)
            sigma_sq = (result.fun ** 2).sum() / dof
            JtJ = J.T @ J
            cov = sigma_sq * np.linalg.inv(JtJ)
            eigenvalues, eigenvectors = np.linalg.eigh(cov)
            eigenvalues = np.abs(eigenvalues)
            semi_a = float(np.sqrt(eigenvalues[1]) * 2.45)
            semi_b = float(np.sqrt(eigenvalues[0]) * 2.45)
            angle = float(np.arctan2(eigenvectors[1, 1], eigenvectors[0, 1]))
            self._last_uncertainty_radius = float(np.sqrt(sigma_sq))
            self._last_uncertainty_ellipse = (semi_a, semi_b, angle)
        except (np.linalg.LinAlgError, ValueError):
            self._last_uncertainty_radius = None
            self._last_uncertainty_ellipse = None

    @property
    def uncertainty_radius(self) -> Optional[float]:
        return self._last_uncertainty_radius

    @property
    def uncertainty_ellipse(self) -> Optional[Tuple[float, float, float]]:
        return self._last_uncertainty_ellipse
