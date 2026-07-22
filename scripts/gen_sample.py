"""Generate synthetic J1939-like telemetry for demoing VDAS-Insight.

Produces several parquet logs under ``sample_data/`` simulating two driving
regimes — ``city`` (frequent shifting, stop-go, brake usage) and ``highway``
(few shifts, sustained high gear) — so the tag/cohort comparison has something
meaningful to show. Column names mimic preprocessed J1939 signals.

Run:  python scripts/gen_sample.py
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sample_data"


def _drive(rng: np.random.Generator, regime: str, minutes: float, hz: float = 10.0):
    n = int(minutes * 60 * hz)
    t = np.arange(n) / hz  # seconds

    if regime == "city":
        # stop-go: smooth speed profile 0..60, periodic stops
        base = 32 + 20 * np.sin(t / 40.0) + 6 * np.sin(t / 17.0)
        stops = (np.sin(t / 55.0) < -0.5)
        speed = np.clip(base, 0, 62)
        speed[stops] *= 0.03
        top_gear = 5
        up_thr = np.array([6, 16, 28, 42, 54], dtype=float)   # accel-side thresholds
    else:  # highway
        base = 88 + 6 * np.sin(t / 90.0) + 3 * np.sin(t / 33.0)
        speed = np.clip(base, 0, 105)
        top_gear = 6
        up_thr = np.array([6, 16, 30, 48, 66, 84], dtype=float)

    # Smooth the speed the gearbox "sees" so gears don't hunt on sensor noise.
    speed = np.clip(speed + rng.normal(0, 0.5, n), 0, None)
    win = int(hz * 2)  # 2 s moving average
    kernel = np.ones(win) / win
    ctrl = np.convolve(speed, kernel, mode="same")

    # Gear state machine with hysteresis + minimum dwell time.
    down_thr = up_thr - np.array([3] + [4] * (top_gear - 1), dtype=float)
    min_dwell = int(hz * 1.5)  # hold each gear at least 1.5 s
    gear = np.empty(n, dtype=int)
    g = 1
    hold = 0
    for i in range(n):
        v = ctrl[i]
        if v < 1.5:
            g_new = 0
        else:
            g_new = max(g, 1)
            if hold >= min_dwell:
                if g < top_gear and v > up_thr[min(g, top_gear - 1)]:
                    g_new = g + 1
                elif g > 1 and v < down_thr[g - 1]:
                    g_new = g - 1
                elif g == 0:
                    g_new = 1
        if g_new != g:
            hold = 0
        else:
            hold += 1
        g = g_new
        gear[i] = g

    rpm = 700 + ctrl * (26 if regime == "highway" else 40) \
        - (gear * 90) + rng.normal(0, 35, n)
    rpm = np.clip(rpm, 600, 3200)

    # Flags (0/1) — brake as sustained blocks on genuine deceleration. City
    # stop-go brakes far more than steady highway cruising.
    decel_thr, brake_prob2 = (-0.10, 0.75) if regime == "city" else (-0.22, 0.35)
    decel = np.gradient(ctrl) < decel_thr
    brake_sw = np.zeros(n, dtype=int)
    i = 0
    while i < n:
        if decel[i] and rng.random() < brake_prob2:
            blk = int(rng.integers(int(hz * 0.6), int(hz * 2.5)))
            brake_sw[i:i + blk] = 1
            i += blk
        else:
            i += 1
    # Cruise control: sustained engagement blocks at steady highway speed.
    cruise_active = np.zeros(n, dtype=int)
    if regime == "highway":
        eligible = (ctrl > 82) & (np.abs(np.gradient(ctrl)) < 0.03)
        i = 0
        while i < n:
            if eligible[i] and rng.random() < 0.05:
                blk = int(rng.integers(int(hz * 25), int(hz * 90)))
                j = min(i + blk, n)
                cruise_active[i:j] = 1
                # enforce an off gap before the next possible engagement
                i = j + int(hz * rng.integers(15, 60))
            else:
                i += 1
    # DPF regeneration: rare, long ON blocks
    dpf = np.zeros(n, dtype=int)
    if rng.random() < 0.6:
        start = rng.integers(0, max(1, n - int(120 * hz)))
        dpf[start:start + int(rng.integers(40, 120) * hz)] = 1

    return pd.DataFrame({
        "timestamp_s": t.round(3),
        "engine_speed_rpm": rpm.round(1),
        "vehicle_speed_kph": speed.round(2),
        "current_gear": gear,
        "brake_switch": brake_sw,
        "cruise_active": cruise_active,
        "dpf_regen_active": dpf,
        "coolant_temp_c": np.clip(85 + rng.normal(0, 2, n) + t / 600.0, 60, 105).round(1),
    })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--fmt", choices=["parquet", "csv"], default="parquet")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    plan = [
        ("city_route_A_run1", "city", 18),
        ("city_route_A_run2", "city", 12),
        ("city_route_B_run1", "city", 22),
        ("highway_M1_run1", "highway", 35),
        ("highway_M1_run2", "highway", 28),
        ("highway_A9_run1", "highway", 40),
    ]
    for name, regime, minutes in plan:
        df = _drive(rng, regime, minutes)
        path = OUT / f"{name}.{args.fmt}"
        if args.fmt == "parquet":
            df.to_parquet(path, index=False)
        else:
            df.to_csv(path, index=False)
        print(f"wrote {path}  ({len(df):,} rows, {minutes} min, {regime})")


if __name__ == "__main__":
    main()
