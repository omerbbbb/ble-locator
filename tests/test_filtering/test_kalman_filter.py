from filtering.kalman_filter import KalmanFilter


def test_first_measurement_passthrough():
    kf = KalmanFilter()
    assert kf.filter(-65.0) == -65.0


def test_convergence():
    kf = KalmanFilter()
    for _ in range(50):
        kf.filter(-60.0)
    assert abs(kf.filter(-60.0) - (-60.0)) < 0.1


def test_noise_reduction():
    import random
    random.seed(42)
    kf = KalmanFilter()
    true_val = -65.0
    outputs = []
    for _ in range(100):
        noisy = true_val + random.gauss(0, 3)
        outputs.append(kf.filter(noisy))
    tail_var = sum((x - true_val) ** 2 for x in outputs[-20:]) / 20
    assert tail_var < 3 ** 2


def test_reset():
    kf = KalmanFilter()
    kf.filter(-60.0)
    kf.filter(-61.0)
    kf.reset()
    assert kf.value is None
    assert kf._P == 1.0
    assert kf.filter(-70.0) == -70.0


def test_value_property():
    kf = KalmanFilter()
    assert kf.value is None
    kf.filter(-65.0)
    assert kf.value == -65.0


def test_custom_params():
    kf = KalmanFilter(process_noise=0.1, measurement_noise=1.0)
    assert kf.Q == 0.1
    assert kf.R == 1.0
