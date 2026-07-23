"""Gear-stage analysis: shift detection, dwell time, transition matrix.

A *shift* is a change in the gear signal between consecutive (de-bounced)
samples. We collapse runs of equal gear first so that noise / repeated samples
never inflate the count, then count transitions between distinct runs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .core import PreparedData


def _gear_runs(pd_data: PreparedData) -> pd.DataFrame:
    """Collapse the gear signal into runs: one row per contiguous gear value.

    Returns columns: gear, start_idx, end_idx, t_start, t_end, duration_s.
    """
    g = pd_data.df[pd_data.gear_col]
    # Preserve NaN as its own sentinel so N<->engaged shows as a transition.
    vals = g.to_numpy()
    t = pd_data.t
    n = len(vals)
    if n == 0:
        return pd.DataFrame(columns=["gear", "start_idx", "end_idx",
                                     "t_start", "t_end", "duration_s"])

    # Boundaries where the value changes (NaN-aware).
    change = np.empty(n, dtype=bool)
    change[0] = True
    prev, cur = vals[:-1], vals[1:]
    neq = prev != cur
    # treat NaN==NaN as equal (no change)
    both_nan = pd.isna(prev) & pd.isna(cur)
    change[1:] = neq & ~both_nan

    starts = np.flatnonzero(change)
    ends = np.append(starts[1:], n) - 1
    rows = []
    for s, e in zip(starts, ends):
        t_start = float(t[s])
        # duration extends to the next run's start (or last sample).
        t_end = float(t[e + 1]) if e + 1 < n else float(t[e])
        rows.append({
            "gear": vals[s],
            "start_idx": int(s),
            "end_idx": int(e),
            "t_start": t_start,
            "t_end": t_end,
            "duration_s": max(t_end - t_start, 0.0),
        })
    return pd.DataFrame(rows)


def shift_count(pd_data: PreparedData) -> int:
    """Number of gear changes (transitions between adjacent runs)."""
    if not pd_data.gear_col:
        return 0
    runs = _gear_runs(pd_data)
    return max(len(runs) - 1, 0)


def shift_events(pd_data: PreparedData) -> pd.DataFrame:
    """One row per shift: time, sample idx, from_gear, to_gear, direction."""
    if not pd_data.gear_col:
        return pd.DataFrame(columns=["t", "idx", "from_gear", "to_gear", "direction"])
    runs = _gear_runs(pd_data)
    events = []
    for i in range(1, len(runs)):
        fr, to = runs.iloc[i - 1]["gear"], runs.iloc[i]["gear"]
        direction = 0
        try:
            direction = int(np.sign(float(to) - float(fr)))
        except (TypeError, ValueError):
            direction = 0
        events.append({
            "t": runs.iloc[i]["t_start"],
            "idx": int(runs.iloc[i]["start_idx"]),   # sample index of the shift
            "from_gear": fr,
            "to_gear": to,
            "direction": direction,
        })
    return pd.DataFrame(events)


def time_in_gear(pd_data: PreparedData) -> pd.DataFrame:
    """Total dwell time and share per gear value. Sorted by gear."""
    if not pd_data.gear_col:
        return pd.DataFrame(columns=["gear", "duration_s", "share", "n_runs"])
    runs = _gear_runs(pd_data)
    if runs.empty:
        return pd.DataFrame(columns=["gear", "duration_s", "share", "n_runs"])
    grp = runs.groupby("gear", dropna=False).agg(
        duration_s=("duration_s", "sum"),
        n_runs=("gear", "size"),
    ).reset_index()
    total = grp["duration_s"].sum()
    grp["share"] = grp["duration_s"] / total if total else 0.0
    return grp.sort_values("gear").reset_index(drop=True)


def transition_matrix(pd_data: PreparedData) -> pd.DataFrame:
    """Square matrix of shift counts: rows = from-gear, cols = to-gear."""
    ev = shift_events(pd_data)
    if ev.empty:
        return pd.DataFrame()
    return pd.crosstab(ev["from_gear"], ev["to_gear"])


def summary(pd_data: PreparedData) -> dict:
    """Scalar shift metrics used both in single-view and cohort aggregation."""
    ev = shift_events(pd_data)
    n = len(ev)
    up = int((ev["direction"] > 0).sum()) if n else 0
    down = int((ev["direction"] < 0).sum()) if n else 0
    hours = pd_data.duration_h
    dist = pd_data.distance_km()
    return {
        "shift_count": n,
        "upshifts": up,
        "downshifts": down,
        "shifts_per_hour": (n / hours) if hours else float("nan"),
        "shifts_per_km": (n / dist) if dist else float("nan"),
    }
