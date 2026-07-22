"""Per-dataset metric engine.

Produces a flat, comparable set of metrics for one dataset. Metrics are split
into two kinds, which matters for fair cohort aggregation:

  * **extensive** — additive over time/records (counts, durations, distance).
    Cohorts pool these by *summation*.
  * **intensive** — rates / ratios / means. Cohorts must **recompute** these
    from pooled extensives, never average the per-dataset rates (that would
    weight a 2-minute log the same as a 5-hour log).

``base_quantities`` returns just the extensive quantities used for pooling;
``dataset_metrics`` returns the full display dict (extensive + per-dataset
intensive).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..datasets import Dataset
from . import flags, gears
from .core import PreparedData, prepare


def base_quantities(pd_data: PreparedData) -> dict:
    """Extensive quantities that pool by summation across a cohort."""
    gs = gears.shift_events(pd_data)
    n = len(gs)
    up = int((gs["direction"] > 0).sum()) if n else 0
    down = int((gs["direction"] < 0).sum()) if n else 0
    dist = pd_data.distance_km()

    q = {
        "n_datasets": 1,
        "n_rows": float(pd_data.n),
        "duration_s": float(pd_data.duration_s),
        "distance_km": float(dist) if dist is not None else np.nan,
        "shift_count": float(n),
        "upshifts": float(up),
        "downshifts": float(down),
    }
    # Per-flag extensive quantities, namespaced.
    for col in pd_data.flag_cols:
        s = flags.summary(pd_data, col)
        q[f"flag::{col}::activations"] = float(s["activations"])
        q[f"flag::{col}::total_on_s"] = float(s["total_on_s"])
    return q


def dataset_metrics(dataset: Dataset) -> dict:
    """Full flat metric dict for one dataset (for the single-dataset view)."""
    pd_data = prepare(dataset)
    q = base_quantities(pd_data)
    m = dict(q)
    hours = pd_data.duration_h
    dist = q.get("distance_km")

    m["duration_h"] = hours
    m["sample_rate_hz"] = (1.0 / pd_data.dt) if pd_data.dt else np.nan
    m["shifts_per_hour"] = (q["shift_count"] / hours) if hours else np.nan
    m["shifts_per_km"] = (q["shift_count"] / dist) if dist else np.nan
    m["upshift_ratio"] = (q["upshifts"] / q["shift_count"]) if q["shift_count"] else np.nan
    for col in pd_data.flag_cols:
        s = flags.summary(pd_data, col)
        m[f"flag::{col}::activations_per_hour"] = s["activations_per_hour"]
        m[f"flag::{col}::duty_cycle"] = s["duty_cycle"]
        m[f"flag::{col}::mean_on_s"] = s["mean_on_s"]
    return m


def derived_from_pool(pool: dict) -> dict:
    """Compute intensive cohort metrics from pooled extensive quantities."""
    hours = pool.get("duration_s", 0.0) / 3600.0
    dist = pool.get("distance_km", np.nan)
    sc = pool.get("shift_count", 0.0)
    out = {
        "shifts_per_hour": (sc / hours) if hours else np.nan,
        "shifts_per_km": (sc / dist) if dist and not np.isnan(dist) else np.nan,
        "upshift_ratio": (pool.get("upshifts", 0.0) / sc) if sc else np.nan,
        "downshift_ratio": (pool.get("downshifts", 0.0) / sc) if sc else np.nan,
    }
    # Flag rates
    for key in list(pool.keys()):
        if key.startswith("flag::") and key.endswith("::activations"):
            col = key[len("flag::"):-len("::activations")]
            act = pool[key]
            on = pool.get(f"flag::{col}::total_on_s", np.nan)
            out[f"flag::{col}::activations_per_hour"] = (act / hours) if hours else np.nan
            out[f"flag::{col}::duty_cycle"] = (
                (on / pool["duration_s"]) if pool.get("duration_s") else np.nan)
    return out


def numeric_stats(pd_data: PreparedData, column: str) -> dict:
    """Descriptive statistics for one numeric column."""
    v = pd.to_numeric(pd_data.df[column], errors="coerce").to_numpy(dtype=float)
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return {"column": column, "n": 0}
    return {
        "column": column,
        "n": int(len(v)),
        "mean": float(np.mean(v)),
        "std": float(np.std(v, ddof=1)) if len(v) > 1 else 0.0,
        "min": float(np.min(v)),
        "p05": float(np.percentile(v, 5)),
        "p50": float(np.percentile(v, 50)),
        "p95": float(np.percentile(v, 95)),
        "max": float(np.max(v)),
    }
