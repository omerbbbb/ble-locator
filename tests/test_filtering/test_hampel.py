from filtering.hampel_filter import HampelFilter


def test_passes_normal_data():
    hf = HampelFilter(window=7, n_sigmas=2.5)
    values = [-65.0, -64.5, -65.5, -65.0, -64.0, -65.0, -64.5]
    results = [hf.filter(v) for v in values]
    for v, r in zip(values, results):
        assert abs(r - v) < 2.0


def test_rejects_spike():
    hf = HampelFilter(window=7, n_sigmas=2.5)
    for v in [-65.0, -64.5, -65.5, -64.0, -66.0, -65.0]:
        hf.filter(v)
    result = hf.filter(-90.0)
    assert abs(result - (-65.0)) < 2.0


def test_reset():
    hf = HampelFilter()
    hf.filter(-65.0)
    hf.reset()
    assert hf.value is None
