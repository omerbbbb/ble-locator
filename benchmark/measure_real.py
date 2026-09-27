"""Real-room distance measurement tool for BLE Locator.

Stand a device at a KNOWN distance from the Mac, run this for ~30 s, and it
records the RSSI stream, converts it to distance three ways (raw, Kalman-only,
full chain), scores each against the true distance, appends the result to
`docs/benchmark/measurements.csv`, and regenerates
`docs/benchmark/REAL_MEASUREMENTS.md` as a summary table.

Repeat at several distances and for several devices (iPhone, watch, …) to
build the accuracy table.

Example:
    .venv/bin/python -m benchmark.measure_real --device "iPhone" \
        --true-distance 1.0 --seconds 30 --label "iPhone 15"

--device matches the device's UUID (as shown on hover in the app) or a
case-insensitive substring of its advertised name.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.distance import rssi_to_distance  # noqa: E402
from filtering.adaptive_kalman import AdaptiveKalmanFilter  # noqa: E402
from filtering.composite_filter import CompositeFilter  # noqa: E402
from filtering.hampel_filter import HampelFilter  # noqa: E402
from filtering.median_filter import MedianFilter  # noqa: E402
from sensor.ble_scanner import BLEScannerImpl  # noqa: E402

OUT_DIR = ROOT / "docs" / "benchmark"
CSV_PATH = OUT_DIR / "measurements.csv"
MD_PATH = OUT_DIR / "REAL_MEASUREMENTS.md"
FIELDS = ["timestamp", "label", "device_id", "true_m", "tx_ref", "n", "samples",
          "mean_rssi", "std_rssi", "mae_raw", "mae_kalman", "mae_full",
          "est_kalman", "est_full"]


def _match(reading, needle: str) -> bool:
    nd = needle.lower()
    return nd in reading.device_id.lower() or nd in (reading.name or "").lower()


async def collect(needle: str, seconds: int):
    scanner = BLEScannerImpl()
    await scanner.start()
    rssis, device_id, name = [], None, None
    t_end = time.time() + seconds
    last_ts = None
    print(f"Scanning for '{needle}' for {seconds}s… stay still.")
    try:
        while time.time() < t_end:
            await asyncio.sleep(1.0)
            for r in scanner.get_active(5.0).values():
                if _match(r, needle):
                    if r.timestamp != last_ts:      # only count fresh adverts
                        rssis.append(r.rssi)
                        last_ts = r.timestamp
                    device_id, name = r.device_id, r.name
                    break
            print(f"  {len(rssis):3d} samples", end="\r")
    finally:
        await scanner.stop()
    print()
    return device_id, name, rssis


def score(rssis, true_d, tx_ref, n):
    fk = AdaptiveKalmanFilter()
    ff = CompositeFilter([MedianFilter(5), HampelFilter(7, 2.5), AdaptiveKalmanFilter()])
    warm = min(10, len(rssis) // 3)
    e_raw, e_k, e_f, est_k, est_f = [], [], [], [], []
    for i, r in enumerate(rssis):
        rk, rf = fk.filter(r), ff.filter(r)
        if i < warm:
            continue
        dr, dk, df = (rssi_to_distance(r, tx_ref, n), rssi_to_distance(rk, tx_ref, n),
                      rssi_to_distance(rf, tx_ref, n))
        e_raw.append(abs(dr - true_d)); e_k.append(abs(dk - true_d)); e_f.append(abs(df - true_d))
        est_k.append(dk); est_f.append(df)
    m = statistics.mean
    return dict(mae_raw=m(e_raw), mae_kalman=m(e_k), mae_full=m(e_f),
                est_kalman=m(est_k), est_full=m(est_f))


def regenerate_markdown():
    if not CSV_PATH.exists():
        return
    with open(CSV_PATH, newline="") as fh:
        rows = list(csv.DictReader(fh))
    md = ["# Real-room distance measurements\n",
          "Produced by `benchmark/measure_real.py` — each row is one ~30 s recording of a device held\n"
          "at a known distance from the Mac. Errors are mean absolute error after filter warm-up.\n",
          "| Device | True | Samples | Mean RSSI | Raw MAE | Kalman MAE | Full-chain MAE | Full vs Kalman |",
          "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        mk, mf = float(r["mae_kalman"]), float(r["mae_full"])
        imp = (1 - mf / mk) * 100 if mk > 0 else 0.0
        md.append(f"| {r['label']} | {float(r['true_m']):.1f} m | {r['samples']} | "
                  f"{float(r['mean_rssi']):.0f} dBm | {float(r['mae_raw']):.2f} m | {mk:.2f} m | "
                  f"{mf:.2f} m | −{imp:.0f}% |")
    # Per-device summary
    by = {}
    for r in rows:
        by.setdefault(r["label"], []).append(r)
    md += ["", "## Per-device summary (averaged over distances)\n",
           "| Device | Raw MAE | Kalman MAE | Full-chain MAE |", "|---|---:|---:|---:|"]
    for label, rs in by.items():
        f = lambda k: statistics.mean(float(x[k]) for x in rs)  # noqa: E731
        md.append(f"| {label} | {f('mae_raw'):.2f} m | {f('mae_kalman'):.2f} m | {f('mae_full'):.2f} m |")
    MD_PATH.write_text("\n".join(md) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", required=True, help="UUID or name substring")
    ap.add_argument("--true-distance", type=float, required=True, help="metres")
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--label", default=None, help="human label for the table (default: device name)")
    ap.add_argument("--tx", type=float, default=-59.0, help="RSSI@1m reference (default -59)")
    ap.add_argument("--n", type=float, default=2.5, help="path-loss exponent (default 2.5)")
    a = ap.parse_args()

    device_id, name, rssis = asyncio.run(collect(a.device, a.seconds))
    if len(rssis) < 8:
        sys.exit(f"Only {len(rssis)} samples — device not seen enough. Check the name/UUID.")

    s = score(rssis, a.true_distance, a.tx, a.n)
    label = a.label or name or device_id
    row = dict(timestamp=time.strftime("%Y-%m-%d %H:%M:%S"), label=label, device_id=device_id,
               true_m=a.true_distance, tx_ref=a.tx, n=a.n, samples=len(rssis),
               mean_rssi=statistics.mean(rssis), std_rssi=statistics.pstdev(rssis), **s)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    new = not CSV_PATH.exists()
    with open(CSV_PATH, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    regenerate_markdown()

    print(f"\n{label} @ {a.true_distance} m  ({len(rssis)} samples, mean RSSI {row['mean_rssi']:.0f} dBm)")
    print(f"  raw          MAE {s['mae_raw']:.2f} m")
    print(f"  Kalman only  MAE {s['mae_kalman']:.2f} m   (est {s['est_kalman']:.2f} m)")
    print(f"  full chain   MAE {s['mae_full']:.2f} m   (est {s['est_full']:.2f} m)")
    print(f"\nAppended to {CSV_PATH}; table at {MD_PATH}")


if __name__ == "__main__":
    main()
