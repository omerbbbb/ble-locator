from filtering.composite_filter import CompositeFilter
from filtering.median_filter import MedianFilter
from filtering.hampel_filter import HampelFilter
from filtering.adaptive_kalman import AdaptiveKalmanFilter


def test_chain_reduces_noise():
    chain = CompositeFilter([
        MedianFilter(window=5),
        HampelFilter(window=7, n_sigmas=2.5),
        AdaptiveKalmanFilter(),
    ])
    import random
    random.seed(42)
    for _ in range(30):
        chain.filter(-65.0 + random.gauss(0, 3.0))
    assert abs(chain.value - (-65.0)) < 2.0


def test_reset_clears_all():
    chain = CompositeFilter([MedianFilter(5), AdaptiveKalmanFilter()])
    chain.filter(-65.0)
    chain.reset()
    assert chain.value is None
