import math

from engine.distance import (
    compute_distance,
    distance_to_rssi,
    rssi_to_distance,
    rssi_to_distance_two_slope,
    tx_reference,
)


def test_tx_reference_prefers_anchor():
    assert tx_reference(-59.0, 4, -55.0) == -59.0


def test_tx_reference_uses_advertised_minus_offset():
    assert tx_reference(None, 4, -59.0, offset=41.0) == 4 - 41.0


def test_tx_reference_falls_back_to_fixed_default():
    # No anchor, no advertised TX → the stable fixed default (never the raw rssi,
    # never a latched peak).
    assert tx_reference(None, None, -59.0) == -59.0


def test_rssi_at_tx_power_returns_minimum():
    assert rssi_to_distance(-59, -59) == 0.05
    assert rssi_to_distance_two_slope(-59, -59) == 0.05


def test_rssi_above_tx_power_returns_minimum():
    assert rssi_to_distance(-50, -59) == 0.05


def test_single_slope_round_trip():
    for d in [1.5, 2.0, 5.0]:
        rssi = distance_to_rssi(d, -59.0, 2.5)
        d_back = rssi_to_distance(rssi, -59.0, 2.5)
        assert abs(d_back - d) < 0.01, f"Round-trip failed for d={d}"


def test_two_slope_continuity_at_breakpoint():
    tx = -59.0
    d_break = 1.5
    rssi_at_break = tx - 10.0 * 2.0 * math.log10(d_break)
    d_near = rssi_to_distance_two_slope(rssi_at_break + 0.01, tx)
    d_far = rssi_to_distance_two_slope(rssi_at_break - 0.01, tx)
    assert abs(d_near - d_break) < 0.02
    assert abs(d_far - d_break) < 0.02


def test_two_slope_monotonic():
    tx = -59.0
    prev_d = 0
    for rssi in range(-59, -100, -1):
        d = rssi_to_distance_two_slope(rssi, tx)
        assert d >= prev_d, f"Non-monotonic at rssi={rssi}"
        prev_d = d


def test_compute_distance_defaults_to_two_slope():
    d_two = rssi_to_distance_two_slope(-70, -59, n_far=2.5)
    d_compute = compute_distance(-70, -59, 2.5)
    assert abs(d_two - d_compute) < 0.001


def test_compute_distance_single_slope():
    d_single = rssi_to_distance(-70, -59, 2.5)
    d_compute = compute_distance(-70, -59, 2.5, two_slope=False)
    assert abs(d_single - d_compute) < 0.001
