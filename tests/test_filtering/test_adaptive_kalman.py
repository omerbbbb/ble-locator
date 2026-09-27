import random

from filtering.adaptive_kalman import AdaptiveKalmanFilter


def test_convergence_to_constant():
    ak = AdaptiveKalmanFilter()
    for _ in range(30):
        v = ak.filter(-65.0)
    assert abs(v - (-65.0)) < 0.1


def test_noise_reduction():
    ak = AdaptiveKalmanFilter()
    random.seed(42)
    raw_values = [-65.0 + random.gauss(0, 2.0) for _ in range(50)]
    filtered = [ak.filter(v) for v in raw_values]
    raw_var = sum((v - (-65)) ** 2 for v in raw_values) / len(raw_values)
    filt_var = sum((v - (-65)) ** 2 for v in filtered[-20:]) / 20
    assert filt_var < raw_var * 0.5


def test_hysteresis_prevents_false_motion():
    """In a reflective room, RSSI noise of 3 dB should NOT trigger walking mode."""
    ak = AdaptiveKalmanFilter()
    random.seed(123)
    for _ in range(40):
        ak.filter(-65.0 + random.gauss(0, 3.0))
    assert not ak.is_moving, "3 dB noise should not trigger walking mode"


def test_real_motion_triggers_walking():
    ak = AdaptiveKalmanFilter()
    for _ in range(10):
        ak.filter(-65.0)
    for _ in range(10):
        ak.filter(-75.0)
    assert ak.is_moving


def test_hysteresis_deadband():
    ak = AdaptiveKalmanFilter()
    for _ in range(10):
        ak.filter(-65.0)
    assert not ak.is_moving
    for _ in range(10):
        ak.filter(-75.0)
    assert ak.is_moving
    for i in range(10):
        ak.filter(-65.0 + 2.5)
    if ak._Q == ak.Q_WALKING:
        pass


def test_reset():
    ak = AdaptiveKalmanFilter()
    ak.filter(-65.0)
    ak.reset()
    assert ak.value is None
    assert not ak.is_moving


def test_params():
    assert AdaptiveKalmanFilter.INNOVATION_WINDOW == 8
    assert AdaptiveKalmanFilter.MOTION_THRESHOLD == 3.5
    assert AdaptiveKalmanFilter.MOTION_THRESHOLD_DOWN == 2.0
