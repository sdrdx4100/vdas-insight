"""Prepared-frame layer.

``prepare`` loads a dataset and resolves its role mapping into a single,
analysis-ready object with a normalized time axis (seconds from start), a
sampling period, and convenient handles to the gear/speed/flag/numeric columns.
Everything downstream (metrics, gears, flags) consumes a ``PreparedData``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .. import datasets as ds_mod
from ..datasets import Dataset


@dataclass
class PreparedData:
    dataset: Dataset
    df: pd.DataFrame
    time_col: str | None
    t: np.ndarray                       # seconds from start (float)
    dt: float                           # median sample period (s)
    duration_s: float
    gear_col: str | None
    speed_col: str | None
    flag_cols: list[str] = field(default_factory=list)
    numeric_cols: list[str] = field(default_factory=list)

    @property
    def duration_h(self) -> float:
        return self.duration_s / 3600.0 if self.duration_s else 0.0

    @property
    def n(self) -> int:
        return len(self.df)

    def distance_km(self) -> float | None:
        """Integrate speed (km/h) over time to estimate distance travelled."""
        if not self.speed_col or self.speed_col not in self.df:
            return None
        v = pd.to_numeric(self.df[self.speed_col], errors="coerce").to_numpy(dtype=float)
        if len(v) < 2:
            return 0.0
        dt_h = np.diff(self.t) / 3600.0
        seg = np.minimum(v[:-1], v[1:])  # conservative lower-rectangle
        mask = np.isfinite(seg) & np.isfinite(dt_h)
        return float(np.sum(seg[mask] * dt_h[mask]))


def _time_seconds(series: pd.Series, unit: str = "s") -> np.ndarray:
    """Convert a time column to float seconds from the first sample."""
    if pd.api.types.is_datetime64_any_dtype(series):
        t = series.astype("int64").to_numpy(dtype=float) / 1e9
    else:
        raw = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
        scale = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "min": 60.0}.get(unit, 1.0)
        t = raw * scale
    t = t - np.nanmin(t)
    return t


def _median_dt(t: np.ndarray) -> float:
    if len(t) < 2:
        return 0.0
    d = np.diff(t)
    d = d[np.isfinite(d) & (d > 0)]
    return float(np.median(d)) if len(d) else 0.0


#: Self-invalidating cache of full prepared frames, keyed by dataset id. The
#: signature folds in file mtime + roles + derived-signal definitions, so any
#: change produces a new key and a fresh build without explicit invalidation.
_PREP_CACHE: dict[int, tuple] = {}


def _prep_signature(dataset: Dataset) -> tuple:
    from .. import derived
    try:
        mtime = os.path.getmtime(dataset.path)
    except OSError:
        mtime = 0.0
    roles = tuple(sorted(ds_mod.get_roles(dataset.id).items()))
    params = tuple(sorted(
        (k, tuple(sorted((v or {}).items())))
        for k, v in ds_mod.get_role_params(dataset.id).items()))
    dsig = tuple((d.name, d.kind, d.source,
                  tuple(sorted((d.params or {}).items())))
                 for d in derived.list_for_dataset(dataset.id))
    return (mtime, roles, params, dsig)


def prepare(dataset: Dataset, columns: list[str] | None = None) -> PreparedData:
    """Build a PreparedData for a dataset (optionally restricting columns).

    Full-load results (``columns is None``) are cached until the file, roles or
    derived-signal definitions change.
    """
    if columns is None:
        sig = _prep_signature(dataset)
        hit = _PREP_CACHE.get(dataset.id)
        if hit is not None and hit[0] == sig:
            return hit[1]

    time_col = ds_mod.time_column(dataset.id)
    gear_col = ds_mod.gear_column(dataset.id)
    speed_col = ds_mod.speed_column(dataset.id)
    flag_cols = ds_mod.flag_columns(dataset.id)
    numeric_cols = ds_mod.numeric_columns(dataset.id)
    role_params = ds_mod.get_role_params(dataset.id)

    load_cols = None
    if columns is not None:
        want = set(columns) | {c for c in [time_col, gear_col, speed_col] if c}
        want |= set(flag_cols)
        load_cols = [c for c in ds_mod.columns(dataset) if c in want]

    df = ds_mod.load(dataset, columns=load_cols, order_by=time_col)

    if time_col and time_col in df:
        unit = (role_params.get(time_col) or {}).get("unit", "s")
        t = _time_seconds(df[time_col], unit=unit)
    else:
        # No time column: fall back to a synthetic 1 Hz index so rate metrics
        # still work (the user can register a real time column later).
        t = np.arange(len(df), dtype=float)

    dt = _median_dt(t)
    duration_s = float(t[-1] - t[0]) if len(t) else 0.0

    # Keep only flags/numerics that actually loaded.
    flag_cols = [c for c in flag_cols if c in df.columns]
    numeric_cols = [c for c in numeric_cols if c in df.columns]

    # Compute & append derived signals (acceleration, jerk, threshold events…)
    # as real columns. Numeric outputs join numeric_cols; 0/1 event outputs join
    # flag_cols so they flow into the flag analysis and flag cohort metrics.
    from .. import derived
    for name, values, out_role in derived.compute_all(dataset.id, df, t):
        df[name] = values
        if out_role == "flag":
            if name not in flag_cols:
                flag_cols.append(name)
        elif name not in numeric_cols:
            numeric_cols.append(name)

    result = PreparedData(
        dataset=dataset, df=df, time_col=time_col, t=t, dt=dt,
        duration_s=duration_s, gear_col=gear_col, speed_col=speed_col,
        flag_cols=flag_cols, numeric_cols=numeric_cols,
    )
    if columns is None:
        _PREP_CACHE[dataset.id] = (sig, result)
    return result
