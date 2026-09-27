"""Particle filter for indoor position tracking.

Maintains N particles (candidate positions) scattered across the room.
Each 1-second tick:
  1. Predict  — add motion noise (random walk), clamp to room walls
  2. Weight   — each particle is scored by how well it explains the measured
                distances from anchors (Gaussian likelihood)
  3. Resample — particles that explained the data well get more copies;
                unlikely ones die. Done when N_eff < N/2 (systematic method).
  4. Estimate — weighted centroid of surviving particles.

Advantages over trilateration for closed rooms:
  - Room walls are hard constraints (particles can't be outside)
  - Handles non-Gaussian multipath noise better
  - Works with 2 anchors (trilateration needs 3)
  - The particle cloud is a natural confidence visualisation
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from core.models import AnchorMeasurement


class ParticleFilter:
    # How far a person typically moves in one second (metres).
    # Lower = smoother but slower to react to real movement.
    MOTION_SIGMA: float = 0.03

    MEAS_SIGMA: float = 0.8

    def __init__(self, n_particles: int = 800):
        self._n = n_particles
        self._particles: Optional[np.ndarray] = None  # shape (N, 2)
        self._weights: Optional[np.ndarray] = None    # shape (N,)
        self._room_w: float = 0.0
        self._room_h: float = 0.0

    # ── public ────────────────────────────────────────────────────────────────

    def update(
        self,
        anchors: List[AnchorMeasurement],
        room_w: float,
        room_h: float,
    ) -> Optional[Tuple[float, float]]:
        """Run one tick. Returns estimated (x, y) or None if no anchors."""
        if not anchors:
            return None

        if (self._particles is None
                or self._room_w != room_w
                or self._room_h != room_h):
            self._initialize(room_w, room_h)

        self._predict()
        self._weight(anchors)

        n_eff = 1.0 / float(np.dot(self._weights, self._weights))
        if n_eff < self._n * 0.5:
            self._resample()

        x_est = float(np.dot(self._weights, self._particles[:, 0]))
        y_est = float(np.dot(self._weights, self._particles[:, 1]))
        return x_est, y_est

    def reset(self) -> None:
        self._particles = None
        self._weights = None
        self._room_w = 0.0
        self._room_h = 0.0

    @property
    def spread(self) -> float:
        """Weighted position spread in metres — confidence indicator.
        Low spread = particles agree = high confidence."""
        if self._particles is None or self._weights is None:
            return float("inf")
        w = self._weights
        px, py = self._particles[:, 0], self._particles[:, 1]
        mx = float(np.dot(w, px))
        my = float(np.dot(w, py))
        return float(np.sqrt(np.dot(w, (px - mx) ** 2 + (py - my) ** 2)))

    def snapshot(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Returns (particles copy, weights copy) for UI rendering, or None."""
        if self._particles is None:
            return None
        return self._particles.copy(), self._weights.copy()

    # ── private ───────────────────────────────────────────────────────────────

    def _initialize(self, room_w: float, room_h: float) -> None:
        self._room_w = room_w
        self._room_h = room_h
        self._particles = np.column_stack([
            np.random.uniform(0.0, room_w, self._n),
            np.random.uniform(0.0, room_h, self._n),
        ])
        self._weights = np.ones(self._n) / self._n

    def _predict(self) -> None:
        """Random walk + wall clamping."""
        noise = np.random.normal(0.0, self.MOTION_SIGMA, self._particles.shape)
        self._particles += noise
        self._particles[:, 0] = np.clip(self._particles[:, 0], 0.0, self._room_w)
        self._particles[:, 1] = np.clip(self._particles[:, 1], 0.0, self._room_h)

    def _wall_proximity(self) -> np.ndarray:
        """Factor [0,1] — 1.0 at wall, 0.0 at ≥WALL_MARGIN from any wall."""
        margin = 0.3
        dx_left = np.clip(margin - self._particles[:, 0], 0, margin)
        dx_right = np.clip(self._particles[:, 0] - (self._room_w - margin), 0, margin)
        dy_bot = np.clip(margin - self._particles[:, 1], 0, margin)
        dy_top = np.clip(self._particles[:, 1] - (self._room_h - margin), 0, margin)
        return np.maximum(np.maximum(dx_left, dx_right),
                          np.maximum(dy_bot, dy_top)) / margin

    def _weight(self, anchors: List[AnchorMeasurement]) -> None:
        """Score each particle by Gaussian likelihood given anchor distances."""
        wall_factor = self._wall_proximity()
        log_w = np.zeros(self._n)
        for anchor in anchors:
            dx = self._particles[:, 0] - anchor.x
            dy = self._particles[:, 1] - anchor.y
            pred = np.sqrt(dx ** 2 + dy ** 2)
            corrected_dist = anchor.distance * (1.0 + 0.15 * wall_factor)
            log_w += -0.5 * ((pred - corrected_dist) / self.MEAS_SIGMA) ** 2

        log_w -= log_w.max()
        self._weights = np.exp(log_w)
        self._weights /= self._weights.sum()

    def _resample(self) -> None:
        """Systematic resampling — O(N), lower variance than multinomial."""
        cumsum = np.cumsum(self._weights)
        positions = (np.arange(self._n) + np.random.uniform()) / self._n
        indices = np.searchsorted(cumsum, positions)
        self._particles = self._particles[indices].copy()
        self._weights = np.ones(self._n) / self._n
