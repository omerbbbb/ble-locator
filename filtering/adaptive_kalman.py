from __future__ import annotations

from collections import deque
from typing import Optional


class AdaptiveKalmanFilter:
    Q_STATIONARY = 0.05
    Q_WALKING = 4.0
    R = 3.0
    INNOVATION_WINDOW = 8
    MOTION_THRESHOLD = 3.5
    MOTION_THRESHOLD_DOWN = 2.0

    def __init__(self):
        self._x: Optional[float] = None
        self._P: float = 1.0
        self._innovations: deque[float] = deque(maxlen=self.INNOVATION_WINDOW)
        self._Q: float = self.Q_STATIONARY

    def filter(self, measurement: float) -> float:
        if self._x is None:
            self._x = measurement
            return self._x

        P_pred = self._P + self._Q
        innovation = abs(measurement - self._x)
        self._innovations.append(innovation)

        if len(self._innovations) >= 3:
            avg_inn = sum(self._innovations) / len(self._innovations)
            if avg_inn > self.MOTION_THRESHOLD:
                self._Q = self.Q_WALKING
            elif avg_inn < self.MOTION_THRESHOLD_DOWN:
                self._Q = self.Q_STATIONARY

        K = P_pred / (P_pred + self.R)
        self._x = self._x + K * (measurement - self._x)
        self._P = (1 - K) * P_pred
        return self._x

    @property
    def is_moving(self) -> bool:
        return self._Q == self.Q_WALKING

    def reset(self):
        self._x = None
        self._P = 1.0
        self._innovations.clear()
        self._Q = self.Q_STATIONARY

    @property
    def value(self) -> Optional[float]:
        return self._x
