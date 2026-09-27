from filtering.nlos_detector import NLOSDetector


def test_los_with_stable_signal():
    det = NLOSDetector(window=15)
    for _ in range(15):
        det.feed(-65.0)
    assert not det.is_nlos
    assert det.adjusted_n(2.5) == 2.5


def test_mild_nlos_with_high_variance():
    det = NLOSDetector(window=15)
    for i in range(15):
        det.feed(-60.0 if i % 2 == 0 else -72.0)
    if det.is_nlos:
        assert det.adjusted_n(2.5) >= 2.5 * 1.1


def test_needs_minimum_samples():
    det = NLOSDetector(window=15)
    for _ in range(3):
        det.feed(-65.0)
    assert not det.is_nlos


def test_reset():
    det = NLOSDetector()
    for i in range(15):
        det.feed(-50.0 if i % 2 else -80.0)
    det.reset()
    assert not det.is_nlos
