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
from .core import PreparedData, prepare, sample_dt


def _onset_mask(on: np.ndarray) -> np.ndarray:
    """Rising-edge (0→1) mask, counting an initial ON sample as an onset."""
    n = len(on)
    onset = np.zeros(n, dtype=bool)
    if n:
        onset[0] = on[0]
        onset[1:] = on[1:] & ~on[:-1]
    return onset


def base_quantities(pd_data: PreparedData, mask: np.ndarray | None = None) -> dict:
    """Extensive quantities that pool by summation across a cohort.

    With ``mask`` (a per-sample boolean), only in-condition samples/events are
    counted and time/distance integrate over the in-condition part.
    """
    gs = gears.shift_events(pd_data)
    if mask is not None and not gs.empty:
        gs = gs[mask[gs["idx"].to_numpy()]]
    n = len(gs)
    up = int((gs["direction"] > 0).sum()) if n else 0
    down = int((gs["direction"] < 0).sum()) if n else 0

    if mask is None:
        duration_s = float(pd_data.duration_s)
        dist = pd_data.distance_km()
        distance_km = float(dist) if dist is not None else np.nan
        n_rows = float(pd_data.n)
    else:
        dt = sample_dt(pd_data.t)
        duration_s = float(np.sum(dt[mask]))
        n_rows = float(int(mask.sum()))
        if pd_data.speed_col and pd_data.speed_col in pd_data.df:
            v = pd.to_numeric(pd_data.df[pd_data.speed_col],
                              errors="coerce").to_numpy(dtype=float)
            ok = mask & np.isfinite(v)
            distance_km = float(np.sum(v[ok] * dt[ok]) / 3600.0)
        else:
            distance_km = np.nan

    q = {
        "n_datasets": 1,
        "n_rows": n_rows,
        "duration_s": duration_s,
        "distance_km": distance_km,
        "shift_count": float(n),
        "upshifts": float(up),
        "downshifts": float(down),
    }
    dt = sample_dt(pd_data.t) if mask is not None else None
    # Per-flag extensive quantities, namespaced.
    for col in pd_data.flag_cols:
        if mask is None:
            s = flags.summary(pd_data, col)
            q[f"flag::{col}::activations"] = float(s["activations"])
            q[f"flag::{col}::total_on_s"] = float(s["total_on_s"])
        else:
            on = pd.to_numeric(pd_data.df[col], errors="coerce").to_numpy(dtype=float) > 0.5
            onset = _onset_mask(on)
            q[f"flag::{col}::activations"] = float(int((onset & mask).sum()))
            q[f"flag::{col}::total_on_s"] = float(np.sum(dt[on & mask]))
    # Per-numeric extensive stats (sum/sumsq/n/max/min). These pool exactly:
    # sum,sumsq,n add; max/min reduce by max/min — so the cohort mean/std/max/min
    # are the true length-weighted values, not an average of per-file means.
    for col in pd_data.numeric_cols:
        v = pd.to_numeric(pd_data.df[col], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(v)
        if mask is not None:
            valid = valid & mask
        vv = v[valid]
        if len(vv) == 0:
            continue
        q[f"num::{col}::sum"] = float(vv.sum())
        q[f"num::{col}::sumsq"] = float(np.dot(vv, vv))
        q[f"num::{col}::n"] = float(len(vv))
        q[f"num::{col}::max"] = float(vv.max())
        q[f"num::{col}::min"] = float(vv.min())
    return q


def metrics_from_prepared(pd_data: PreparedData, mask: np.ndarray | None = None) -> dict:
    """Full flat metric dict derived from (optionally masked) base quantities."""
    q = base_quantities(pd_data, mask)
    m = dict(q)
    dur = q.get("duration_s", 0.0)
    hours = dur / 3600.0
    dist = q.get("distance_km")
    sc = q["shift_count"]

    m["duration_h"] = hours
    m["sample_rate_hz"] = (1.0 / pd_data.dt) if pd_data.dt else np.nan
    m["shifts_per_hour"] = (sc / hours) if hours else np.nan
    m["shifts_per_km"] = (sc / dist) if dist and not np.isnan(dist) else np.nan
    m["upshift_ratio"] = (q["upshifts"] / sc) if sc else np.nan
    for col in pd_data.flag_cols:
        act = q.get(f"flag::{col}::activations", np.nan)
        on = q.get(f"flag::{col}::total_on_s", np.nan)
        m[f"flag::{col}::activations_per_hour"] = (act / hours) if hours else np.nan
        m[f"flag::{col}::duty_cycle"] = (on / dur) if dur else np.nan
    for col in pd_data.numeric_cols:
        n = q.get(f"num::{col}::n", 0.0)
        if not n:
            continue
        mean = q[f"num::{col}::sum"] / n
        var = max(q.get(f"num::{col}::sumsq", 0.0) / n - mean * mean, 0.0)
        m[f"num::{col}::mean"] = mean
        m[f"num::{col}::std"] = var ** 0.5
    return m


def dataset_metrics(dataset: Dataset) -> dict:
    """Full flat metric dict for one dataset (for the single-dataset view)."""
    return metrics_from_prepared(prepare(dataset))


def derived_from_pool(pool: dict) -> dict:
    """Compute intensive cohort metrics from pooled extensive quantities."""
    hours = pool.get("duration_s", 0.0) / 3600.0
    dist = pool.get("distance_km", np.nan)
    sc = pool.get("shift_count", 0.0)
    out = {
        "duration_h": hours,
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
    # Numeric mean/std from pooled moments (max/min are already pooled).
    for key in list(pool.keys()):
        if key.startswith("num::") and key.endswith("::sum"):
            col = key[len("num::"):-len("::sum")]
            n = pool.get(f"num::{col}::n", 0.0)
            if not n:
                continue
            mean = pool[key] / n
            var = max(pool.get(f"num::{col}::sumsq", 0.0) / n - mean * mean, 0.0)
            out[f"num::{col}::mean"] = mean
            out[f"num::{col}::std"] = var ** 0.5
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
