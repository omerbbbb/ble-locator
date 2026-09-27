# Simulated distance-accuracy benchmark

> **SIMULATED — not a physical measurement.** These numbers are properties of the
> filtering algorithms under a stated indoor-noise model. Real-room results must be
> produced with `benchmark/measure_real.py`. Device profiles are illustrative assumptions.

Reproduce: `.venv/bin/python -m benchmark.simulate_accuracy` (seed 42).

## Noise model

- Path loss: `RSSI = RSSI@1m − 10·2.5·log10(d)`
- Shadowing: Gaussian σ = 3.5 dB
- Multipath: with p = 0.08 per sample, add one of (-12.0, -9.0, 7.0) dB
- 60 samples per point at 1 Hz; first 15 s discarded (filter warm-up)
- True distances: [0.5, 1.0, 2.0, 3.0, 4.0] m

## 1. Full chain vs Kalman-only (perfect per-device calibration)

Mean absolute distance error, averaged over all true distances.

| Device profile (assumed RSSI@1m) | Raw RSSI | Kalman only | Full chain | Full vs Kalman |
|---|---:|---:|---:|---:|
| Beacon-like (-59 dBm) | 0.83 m | 0.58 m | 0.39 m | **−33%** error |
| Watch-like (-64 dBm) | 0.80 m | 0.52 m | 0.30 m | **−42%** error |
| iPhone-like (-72 dBm) | 0.83 m | 0.61 m | 0.45 m | **−26%** error |

### Per-distance detail (Beacon-like profile)

| True distance | Raw MAE | Kalman MAE | Full-chain MAE |
|---:|---:|---:|---:|
| 0.5 m | 0.46 m | 0.45 m | 0.45 m |
| 1.0 m | 0.73 m | 0.48 m | 0.72 m |
| 2.0 m | 0.78 m | 0.48 m | 0.18 m |
| 3.0 m | 0.93 m | 0.55 m | 0.16 m |
| 4.0 m | 1.24 m | 0.95 m | 0.44 m |

## 2. Why devices disagree — effect of a fixed -59 dBm reference

Full-chain estimate when every device is measured against the app's single default
reference instead of its own RSSI@1m. This is the mechanism behind "my iPhone reads
far even when it is next to the Mac": a device with a weaker radio is systematically
overestimated unless it is calibrated.

| Device profile | True 1 m → est. | True 2 m → est. | True 3 m → est. | Bias direction |
|---|---:|---:|---:|---|
| Beacon-like | 0.8 m | 2.0 m | 3.3 m | none (matches default) |
| Watch-like | 1.8 m | 3.3 m | 5.0 m | reads **farther** (+5 dB off) |
| iPhone-like | 3.2 m | 6.3 m | 10.6 m | reads **farther** (+13 dB off) |

**Takeaway:** the filter chain removes noise well, but *absolute* accuracy is bounded by
per-device calibration of RSSI@1m. That is a physics limit of RSSI ranging, not a
software one.
