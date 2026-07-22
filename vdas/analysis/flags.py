"""Flag (0/1) signal analysis.

For a binary signal we care about:
  * activations       — number of rising edges (0->1)
  * duty cycle        — fraction of time in the ON state
  * on/off durations  — how long each ON (and OFF) interval lasts
  * intervals         — time between successive activations (0->1 edges)

Every duration is measured on the normalized time axis (seconds), so results
are comparable across datasets sampled at different rates.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .core import PreparedData


def _binary(series: pd.Series) -> np.ndarray:
    v = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    # Treat anything > 0.5 as ON; carry NaN forward as previous state.
    on = v > 0.5
    return on


def _runs(on: np.ndarray, t: np.ndarray):
    """Yield (state, t_start, t_end) for each contiguous ON/OFF run."""
    n = len(on)
    if n == 0:
        return
    change = np.empty(n, dtype=bool)
    change[0] = True
    change[1:] = on[1:] != on[:-1]
    starts = np.flatnonzero(change)
    ends = np.append(starts[1:], n) - 1
    for s, e in zip(starts, ends):
        t_start = float(t[s])
        t_end = float(t[e + 1]) if e + 1 < n else float(t[e])
        yield bool(on[s]), t_start, t_end


def intervals(pd_data: PreparedData, col: str) -> dict:
    """Full interval breakdown for one flag column."""
    on = _binary(pd_data.df[col])
    t = pd_data.t
    on_durs, off_durs, on_starts = [], [], []
    for state, t0, t1 in _runs(on, t):
        dur = max(t1 - t0, 0.0)
        if state:
            on_durs.append(dur)
            on_starts.append(t0)
        else:
            off_durs.append(dur)

    on_durs = np.array(on_durs, dtype=float)
    off_durs = np.array(off_durs, dtype=float)
    on_starts = np.array(on_starts, dtype=float)
    # Rising-edge count: number of ON runs that are not the very first sample
    # already being ON is still an activation event we count.
    activations = int(len(on_durs))
    between = np.diff(on_starts) if len(on_starts) > 1 else np.array([], dtype=float)

    total_on = float(on_durs.sum())
    hours = pd_data.duration_h
    return {
        "column": col,
        "activations": activations,
        "activations_per_hour": (activations / hours) if hours else float("nan"),
        "duty_cycle": (total_on / pd_data.duration_s) if pd_data.duration_s else float("nan"),
        "total_on_s": total_on,
        "mean_on_s": float(on_durs.mean()) if len(on_durs) else float("nan"),
        "median_on_s": float(np.median(on_durs)) if len(on_durs) else float("nan"),
        "max_on_s": float(on_durs.max()) if len(on_durs) else float("nan"),
        "mean_off_s": float(off_durs.mean()) if len(off_durs) else float("nan"),
        "mean_interval_s": float(between.mean()) if len(between) else float("nan"),
        "on_durations": on_durs,
        "off_durations": off_durs,
        "between_activations": between,
        "on_starts": on_starts,
    }


def summary_table(pd_data: PreparedData) -> pd.DataFrame:
    """One row per flag column with the scalar interval metrics."""
    rows = []
    for col in pd_data.flag_cols:
        d = intervals(pd_data, col)
        rows.append({k: d[k] for k in (
            "column", "activations", "activations_per_hour", "duty_cycle",
            "total_on_s", "mean_on_s", "median_on_s", "max_on_s",
            "mean_off_s", "mean_interval_s",
        )})
    return pd.DataFrame(rows)


def summary(pd_data: PreparedData, col: str) -> dict:
    """Scalar-only summary for cohort aggregation."""
    d = intervals(pd_data, col)
    return {k: d[k] for k in (
        "activations", "activations_per_hour", "duty_cycle",
        "total_on_s", "mean_on_s", "mean_interval_s",
    )}
