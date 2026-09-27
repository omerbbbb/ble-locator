# Real-room distance measurements

*No on-site measurements recorded yet.* This file is regenerated automatically by
`benchmark/measure_real.py` each time you record a device at a known distance:

```bash
make measure DEVICE=iPhone DIST=1.0      # hold the device 1.0 m away, ~30 s
make measure DEVICE=iPhone DIST=2.0
make measure DEVICE="Apple Watch" DIST=1.0
```

Each run appends a row to `measurements.csv` (mean RSSI, raw / Kalman-only / full-chain error) and
rebuilds the tables below with per-device error and the Kalman-vs-full-chain gain.

For the algorithm-only comparison that does not depend on a room, see
[`SIMULATED_ACCURACY.md`](SIMULATED_ACCURACY.md).
