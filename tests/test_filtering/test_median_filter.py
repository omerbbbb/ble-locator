from filtering.median_filter import MedianFilter


def test_single_value():
    mf = MedianFilter(window=5)
    assert mf.filter(-65.0) == -65.0


def test_median_of_window():
    mf = MedianFilter(window=3)
    mf.filter(-60.0)
    mf.filter(-70.0)
    result = mf.filter(-65.0)
    assert result == -65.0


def test_rejects_outlier():
    mf = MedianFilter(window=5)
    for _ in range(4):
        mf.filter(-65.0)
    result = mf.filter(-90.0)
    assert result == -65.0


def test_reset():
    mf = MedianFilter(window=5)
    mf.filter(-65.0)
    mf.filter(-66.0)
    mf.reset()
    assert mf.value is None
    assert mf.filter(-80.0) == -80.0


def test_value_property():
    mf = MedianFilter()
    assert mf.value is None
    mf.filter(-60.0)
    assert mf.value == -60.0


def test_minimum_window():
    mf = MedianFilter(window=1)
    assert mf._window == 3
