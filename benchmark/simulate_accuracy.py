"""Simulated distance-accuracy benchmark for BLE Locator.

*** SIMULATED — this is NOT a physical measurement. ***

It answers two questions that are properties of the *algorithms*, independent of
any particular room:

  1. How much does the full filter chain (Median → Hampel → Kalman) reduce
     distance error compared with a Kalman filter alone, under realistic indoor
     BLE noise (log-normal shadowing + occasional multipath spikes)?
  2. Why do different devices (iPhone vs watch vs beacon) read differently at
     the same true distance when a single fixed RSSI@1m reference is used?

Device "profiles" below are ILLUSTRATIVE ASSUMPTIONS about each device's true
RSSI at 1 m — they are not measured values. Real-room numbers must come from
`benchmark/measure_real.py`.

Reproduce:   .venv/bin/python -m benchmark.simulate_accuracy
Outputs:     docs/benchmark/SIMULATED_ACCURACY.md  +  simulated_accuracy.csv
"""

from __future__ import annotations

import csv
import math
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.distance import rssi_to_distance  # noqa: E402
from filtering.adaptive_kalman import AdaptiveKalmanFilter  # noqa: E402
from filtering.composite_filter import CompositeFilter  # noqa: E402
from filtering.hampel_filter import HampelFilter  # noqa: E402
from filtering.median_filter import MedianFilter  # noqa: E402

# ── Model parameters (documented in the output) ─────────────────────────────
N_PATH_LOSS = 2.5            # indoor path-loss exponent used by the app
TRUE_DISTANCES = [0.5, 1.0, 2.0, 3.0, 4.0]   # metres
SAMPLES = 60                 # 60 s at 1 Hz per (device, distance)
WARMUP = 15                  # ignore the first 15 s (filter convergence)
SHADOW_SIGMA_DB = 3.5        # log-normal shadowing, dB
SPIKE_PROB = 0.08            # chance per sample of a multipath event
SPIKES_DB = (-12.0, -9.0, +7.0)   # deep fade, fade, constructive burst
SEED = 42

# Assumed RSSI@1m per device class. ILLUSTRATIVE, not measured.
DEVICE_PROFILES = {
    "Beacon-like": -59.0,
    "Watch-like":  -64.0,
    "iPhone-like": -72.0,
}
FIXED_REFERENCE = -59.0      # the app's default when a device is uncalibrated

OUT_DIR = ROOT / "docs" / "benchmark"


def simulate_rssi(rng: random.Random, tx_1m: float, d: float) -> float:
    mean = tx_1m - 10.0 * N_PATH_LOSS * math.log10(d)
    r = rng.gauss(mean, SHADOW_SIGMA_DB)
    if rng.random() < SPIKE_PROB:
        r += rng.choice(SPIKES_DB)
    return r


def kalman_only():
    return AdaptiveKalmanFilter()


def full_chain():
    return CompositeFilter([MedianFilter(5), HampelFilter(7, 2.5), AdaptiveKalmanFilter()])


def run_one(rng, tx_1m, true_d, tx_ref):
    """Return (mae_raw, mae_kalman, mae_full, mean_full_estimate)."""
    fk, ff = kalman_only(), full_chain()
    err_raw, err_k, err_f, est_f = [], [], [], []
    for i in range(SAMPLES):
        r = simulate_rssi(rng, tx_1m, true_d)
        rk = fk.filter(r)
        rf = ff.filter(r)
        if i < WARMUP:
            continue
        d_raw = rssi_to_distance(r, tx_ref, N_PATH_LOSS)
        d_k = rssi_to_distance(rk, tx_ref, N_PATH_LOSS)
        d_f = rssi_to_distance(rf, tx_ref, N_PATH_LOSS)
        err_raw.append(abs(d_raw - true_d))
        err_k.append(abs(d_k - true_d))
        err_f.append(abs(d_f - true_d))
        est_f.append(d_f)
    return (statistics.mean(err_raw), statistics.mean(err_k),
            statistics.mean(err_f), statistics.mean(est_f))


def main() -> None:
    rng = random.Random(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []

    # Table 1 — filter comparison with a PERFECT per-device reference.
    for name, tx in DEVICE_PROFILES.items():
        for d in TRUE_DISTANCES:
            mr, mk, mf, _ = run_one(rng, tx, d, tx_ref=tx)
            rows.append({"device": name, "true_m": d, "reference": "calibrated",
                         "mae_raw": mr, "mae_kalman": mk, "mae_full": mf})

    # Table 2 — the same devices but with the app's FIXED -59 reference.
    bias_rows = []
    for name, tx in DEVICE_PROFILES.items():
        for d in TRUE_DISTANCES:
            _, _, mf, est = run_one(rng, tx, d, tx_ref=FIXED_REFERENCE)
            bias_rows.append({"device": name, "true_m": d, "est_m": est, "mae_full": mf})

    # ── CSV ──
    with open(OUT_DIR / "simulated_accuracy.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ── Markdown ──
    def agg(device, key):
        return statistics.mean(r[key] for r in rows if r["device"] == device)

    md = []
    md.append("# Simulated distance-accuracy benchmark\n")
    md.append("> **SIMULATED — not a physical measurement.** These numbers are properties of the\n"
              "> filtering algorithms under a stated indoor-noise model. Real-room results must be\n"
              "> produced with `benchmark/measure_real.py`. Device profiles are illustrative assumptions.\n")
    md.append(f"Reproduce: `.venv/bin/python -m benchmark.simulate_accuracy` (seed {SEED}).\n")
    md.append("## Noise model\n")
    md.append(f"- Path loss: `RSSI = RSSI@1m − 10·{N_PATH_LOSS}·log10(d)`\n"
              f"- Shadowing: Gaussian σ = {SHADOW_SIGMA_DB} dB\n"
              f"- Multipath: with p = {SPIKE_PROB} per sample, add one of {SPIKES_DB} dB\n"
              f"- {SAMPLES} samples per point at 1 Hz; first {WARMUP} s discarded (filter warm-up)\n"
              f"- True distances: {TRUE_DISTANCES} m\n")

    md.append("## 1. Full chain vs Kalman-only (perfect per-device calibration)\n")
    md.append("Mean absolute distance error, averaged over all true distances.\n")
    md.append("| Device profile (assumed RSSI@1m) | Raw RSSI | Kalman only | Full chain | Full vs Kalman |")
    md.append("|---|---:|---:|---:|---:|")
    for name, tx in DEVICE_PROFILES.items():
        mr, mk, mf = agg(name, "mae_raw"), agg(name, "mae_kalman"), agg(name, "mae_full")
        imp = (1 - mf / mk) * 100 if mk > 0 else 0.0
        md.append(f"| {name} ({tx:.0f} dBm) | {mr:.2f} m | {mk:.2f} m | {mf:.2f} m | **−{imp:.0f}%** error |")
    md.append("")

    md.append("### Per-distance detail (Beacon-like profile)\n")
    md.append("| True distance | Raw MAE | Kalman MAE | Full-chain MAE |")
    md.append("|---:|---:|---:|---:|")
    for r in rows:
        if r["device"] == "Beacon-like":
            md.append(f"| {r['true_m']:.1f} m | {r['mae_raw']:.2f} m | {r['mae_kalman']:.2f} m | {r['mae_full']:.2f} m |")
    md.append("")

    md.append(f"## 2. Why devices disagree — effect of a fixed {FIXED_REFERENCE:.0f} dBm reference\n")
    md.append("Full-chain estimate when every device is measured against the app's single default\n"
              "reference instead of its own RSSI@1m. This is the mechanism behind \"my iPhone reads\n"
              "far even when it is next to the Mac\": a device with a weaker radio is systematically\n"
              "overestimated unless it is calibrated.\n")
    md.append("| Device profile | True 1 m → est. | True 2 m → est. | True 3 m → est. | Bias direction |")
    md.append("|---|---:|---:|---:|---|")
    for name, tx in DEVICE_PROFILES.items():
        ests = {r["true_m"]: r["est_m"] for r in bias_rows if r["device"] == name}
        gap = FIXED_REFERENCE - tx
        direction = ("none (matches default)" if abs(gap) < 0.5
                     else f"reads **{'farther' if gap > 0 else 'closer'}** ({gap:+.0f} dB off)")
        md.append(f"| {name} | {ests[1.0]:.1f} m | {ests[2.0]:.1f} m | {ests[3.0]:.1f} m | {direction} |")
    md.append("")
    md.append("**Takeaway:** the filter chain removes noise well, but *absolute* accuracy is bounded by\n"
              "per-device calibration of RSSI@1m. That is a physics limit of RSSI ranging, not a\n"
              "software one.\n")

    (OUT_DIR / "SIMULATED_ACCURACY.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    print(f"\nWrote {OUT_DIR / 'SIMULATED_ACCURACY.md'} and simulated_accuracy.csv")


if __name__ == "__main__":
    main()
