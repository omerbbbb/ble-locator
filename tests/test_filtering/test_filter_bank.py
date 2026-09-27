from filtering.filter_bank import FilterBank
from filtering.kalman_filter import KalmanFilter


def test_creates_filter_on_first_apply():
    bank = FilterBank(KalmanFilter)
    result = bank.apply("dev1", -65.0)
    assert result == -65.0


def test_separate_filters_per_device():
    bank = FilterBank(KalmanFilter)
    bank.apply("dev1", -60.0)
    bank.apply("dev2", -80.0)
    v1 = bank.apply("dev1", -60.0)
    v2 = bank.apply("dev2", -80.0)
    assert abs(v1 - (-60.0)) < 1.0
    assert abs(v2 - (-80.0)) < 1.0


def test_reset_device():
    bank = FilterBank(KalmanFilter)
    bank.apply("dev1", -60.0)
    bank.apply("dev1", -61.0)
    bank.reset_device("dev1")
    result = bank.apply("dev1", -70.0)
    assert result == -70.0


def test_reset_device_nonexistent():
    bank = FilterBank(KalmanFilter)
    bank.reset_device("nonexistent")


def test_reset_all():
    bank = FilterBank(KalmanFilter)
    bank.apply("dev1", -60.0)
    bank.apply("dev2", -70.0)
    bank.reset_all()
    r1 = bank.apply("dev1", -80.0)
    assert r1 == -80.0


def test_median_filter():
    from filtering.median_filter import MedianFilter
    bank = FilterBank(lambda: MedianFilter(window=3))
    r = bank.apply("dev1", -60.0)
    assert r == -60.0


def test_retain_drops_absent_devices():
    bank = FilterBank(KalmanFilter)
    bank.apply("keep", -60.0)
    bank.apply("drop", -70.0)
    bank.retain({"keep"})
    # "drop" was evicted → its filter is fresh again on next use
    assert bank.apply("drop", -90.0) == -90.0
    # "keep" retained its filter state (won't snap to a far new value)
    assert abs(bank.apply("keep", -90.0) - (-90.0)) > 1.0


def test_retain_empty_clears_all():
    bank = FilterBank(KalmanFilter)
    bank.apply("a", -60.0)
    bank.apply("b", -70.0)
    bank.retain(set())
    assert bank.apply("a", -80.0) == -80.0
