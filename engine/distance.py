import math


MIN_DISTANCE = 0.05


def rssi_to_distance(rssi: float, tx_power: float, n: float = 2.5) -> float:
    if rssi >= tx_power:
        return MIN_DISTANCE
    exponent = (tx_power - rssi) / (10.0 * n)
    return max(MIN_DISTANCE, 10.0 ** exponent)


def rssi_to_distance_two_slope(
    rssi: float, tx_power: float,
    n_near: float = 2.0, n_far: float = 3.0, d_break: float = 1.5,
) -> float:
    if rssi >= tx_power:
        return MIN_DISTANCE
    rssi_at_break = tx_power - 10.0 * n_near * math.log10(d_break)
    if rssi >= rssi_at_break:
        return max(MIN_DISTANCE, 10.0 ** ((tx_power - rssi) / (10.0 * n_near)))
    return max(MIN_DISTANCE,
               d_break * (10.0 ** ((rssi_at_break - rssi) / (10.0 * n_far))))


def compute_distance(
    rssi: float, tx_power: float, n: float = 2.5,
    two_slope: bool = True,
) -> float:
    if two_slope:
        return rssi_to_distance_two_slope(rssi, tx_power, n_far=n)
    return rssi_to_distance(rssi, tx_power, n)


def distance_to_rssi(distance: float, tx_power: float, n: float = 2.5) -> float:
    if distance <= 0:
        distance = 0.01
    return tx_power - 10.0 * n * math.log10(distance)


# Free-space path loss at 1 m, 2.4 GHz (~40 dB). Converts an advertised BLE
# TX-power level (radio dBm at source) into the expected RSSI at 1 m.
TX_OFFSET_1M = 41.0


def tx_reference(anchor_tx, tx_power_adv, default_tx,
                 offset: float = TX_OFFSET_1M) -> float:
    """Per-device RSSI-at-1m reference for the distance formula.

    Priority: calibrated anchor → advertised TX power (converted to RSSI@1m) →
    a fixed default. Deliberately stable — no per-device "peak" latch, which
    made bursty BLE RSSI inflate distances.
    """
    if anchor_tx is not None:
        return float(anchor_tx)
    if tx_power_adv is not None:
        return float(tx_power_adv) - offset
    return float(default_tx)
