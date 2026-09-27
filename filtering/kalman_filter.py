from typing import Optional


class KalmanFilter:
    """1D Kalman filter for smoothing a noisy signal stream.

    High R/Q ratio → smoother but slower to respond.
    Low R/Q ratio  → faster but noisier.
    """

    def __init__(self, process_noise: float = 0.005, measurement_noise: float = 6.0):
        self.Q = process_noise
        self.R = measurement_noise
        self._x: Optional[float] = None
        self._P: float = 1.0

    def filter(self, measurement: float) -> float:
        if self._x is None:
            self._x = measurement
            return self._x

        x_pred = self._x
        P_pred = self._P + self.Q

        K = P_pred / (P_pred + self.R)
        self._x = x_pred + K * (measurement - x_pred)
        self._P = (1 - K) * P_pred
        return self._x

    def reset(self):
        self._x = None
        self._P = 1.0

    @property
    def value(self) -> Optional[float]:
        return self._x
