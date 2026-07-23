"""Derived signals — compute new channels from existing ones.

A *derived signal* is a named channel computed from an existing column (a file
column or another derived signal) plus the time axis: e.g. acceleration and
jerk from vehicle speed, a generic time-derivative, a rolling mean, etc.

Definitions are persisted per dataset; the values are (re)computed on load in
``vdas.analysis.core.prepare`` and appear as ordinary numeric columns, so they
flow into the signal list, time-series, statistics and cohort metrics.

Differentiation amplifies noise, so every derivative kind accepts a smoothing
window ``window_s`` (seconds, moving average applied before differentiating).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from . import db

# km/h → m/s
_KPH_TO_MS = 1000.0 / 3600.0


# --------------------------------------------------------------------------- #
#  Numeric helpers
# --------------------------------------------------------------------------- #
def _median_dt(t: np.ndarray) -> float:
    if len(t) < 2:
        return 1.0
    d = np.diff(t)
    d = d[np.isfinite(d) & (d > 0)]
    return float(np.median(d)) if len(d) else 1.0


def _smooth(y: np.ndarray, t: np.ndarray, window_s: float) -> np.ndarray:
    if window_s and window_s > 0:
        dt = _median_dt(t)
        win = max(1, int(round(window_s / dt)))
        if win > 1:
            # Centered rolling mean with min_periods=1 avoids the edge dip that
            # a zero-padded convolution would introduce (which then blows up the
            # derivative at the first/last samples).
            return (pd.Series(y).rolling(win, center=True, min_periods=1)
                    .mean().to_numpy())
    return y


def _ddt(y: np.ndarray, t: np.ndarray) -> np.ndarray:
    """First time-derivative, robust to non-uniform / degenerate time."""
    if len(y) < 2:
        return np.zeros_like(y)
    if np.all(np.diff(t) > 0):
        return np.gradient(y, t)
    return np.gradient(y) / _median_dt(t)


# --------------------------------------------------------------------------- #
#  Kind registry
# --------------------------------------------------------------------------- #
@dataclass
class Kind:
    key: str
    label: str
    unit_fn: Callable[[str], str]          # source unit hint -> output unit hint
    compute: Callable[[np.ndarray, np.ndarray, dict], np.ndarray]
    default_window_s: float = 0.0
    needs_speed: bool = False              # preset that assumes km/h source
    out_role: str = "numeric"              # "numeric" or "flag" (0/1 event)
    needs_threshold: bool = False          # threshold-event kind


def _c_accel_kph(y, t, p):
    return _ddt(_smooth(y, t, p.get("window_s", 0.5)), t) * _KPH_TO_MS


def _c_jerk_kph(y, t, p):
    v = _smooth(y, t, p.get("window_s", 1.0))
    return _ddt(_ddt(v, t), t) * _KPH_TO_MS


def _c_derivative(y, t, p):
    return _ddt(_smooth(y, t, p.get("window_s", 0.0)), t)


def _c_second_derivative(y, t, p):
    s = _smooth(y, t, p.get("window_s", 0.0))
    return _ddt(_ddt(s, t), t)


def _c_rolling_mean(y, t, p):
    return _smooth(y, t, p.get("window_s", 1.0))


def _c_abs(y, t, p):
    return np.abs(y)


# --- Threshold event kinds (output 0/1) ------------------------------------
def _thr_input(y, t, p):
    """Optionally debounce the signal before comparing to the threshold."""
    return _smooth(y, t, p.get("window_s", 0.0))


def _c_thr_gt(y, t, p):
    return (_thr_input(y, t, p) > p.get("threshold", 0.0)).astype(float)


def _c_thr_lt(y, t, p):
    return (_thr_input(y, t, p) < p.get("threshold", 0.0)).astype(float)


def _c_thr_abs_gt(y, t, p):
    return (np.abs(_thr_input(y, t, p)) > p.get("threshold", 0.0)).astype(float)


KINDS: dict[str, Kind] = {
    "accel_from_speed": Kind(
        "accel_from_speed", "加速度 (m/s²) ← 車速",
        lambda u: "m/s²", _c_accel_kph, default_window_s=0.5, needs_speed=True),
    "jerk_from_speed": Kind(
        "jerk_from_speed", "加加速度 (m/s³) ← 車速",
        lambda u: "m/s³", _c_jerk_kph, default_window_s=1.0, needs_speed=True),
    "derivative": Kind(
        "derivative", "微分 d/dt",
        lambda u: f"{u}/s" if u else "/s", _c_derivative),
    "second_derivative": Kind(
        "second_derivative", "2階微分 d²/dt²",
        lambda u: f"{u}/s²" if u else "/s²", _c_second_derivative),
    "rolling_mean": Kind(
        "rolling_mean", "移動平均",
        lambda u: u, _c_rolling_mean, default_window_s=1.0),
    "abs": Kind("abs", "絶対値 |x|", lambda u: u, _c_abs),
    # Threshold events → 0/1 flags (feed the flag analysis & flag cohort metrics)
    "thr_gt": Kind(
        "thr_gt", "しきい値イベント: x > 閾値", lambda u: "0/1", _c_thr_gt,
        out_role="flag", needs_threshold=True),
    "thr_lt": Kind(
        "thr_lt", "しきい値イベント: x < 閾値", lambda u: "0/1", _c_thr_lt,
        out_role="flag", needs_threshold=True),
    "thr_abs_gt": Kind(
        "thr_abs_gt", "しきい値イベント: |x| > 閾値", lambda u: "0/1", _c_thr_abs_gt,
        out_role="flag", needs_threshold=True),
}


# --------------------------------------------------------------------------- #
#  Definition dataclass + CRUD
# --------------------------------------------------------------------------- #
@dataclass
class DerivedSignal:
    id: int
    dataset_id: int
    name: str
    kind: str
    source: str | None
    params: dict = field(default_factory=dict)
    ordinal: int = 0


def suggest_name(kind: str, source: str) -> str:
    base = {
        "accel_from_speed": "accel_mps2",
        "jerk_from_speed": "jerk_mps3",
        "derivative": f"{source}_ddt",
        "second_derivative": f"{source}_d2dt",
        "rolling_mean": f"{source}_ma",
        "abs": f"{source}_abs",
        "thr_gt": f"{source}_hi",
        "thr_lt": f"{source}_lo",
        "thr_abs_gt": f"{source}_absHi",
    }.get(kind, f"{source}_{kind}")
    return base


def add(dataset_id: int, kind: str, source: str, name: str | None = None,
        params: dict | None = None) -> DerivedSignal:
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind}")
    name = (name or suggest_name(kind, source)).strip()
    params = params or {}
    con = db.get_con()
    nxt = con.execute(
        "SELECT COALESCE(max(ordinal), 0) + 1 FROM derived_signals WHERE dataset_id = ?",
        [dataset_id]).fetchone()[0]
    row = con.execute(
        "INSERT INTO derived_signals (dataset_id, name, kind, source, params, ordinal) "
        "VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
        [dataset_id, name, kind, source, db._dumps(params), nxt],
    ).fetchone()
    return DerivedSignal(row[0], dataset_id, name, kind, source, params, nxt)


def list_for_dataset(dataset_id: int) -> list[DerivedSignal]:
    rows = db.get_con().execute(
        "SELECT id, dataset_id, name, kind, source, params, ordinal "
        "FROM derived_signals WHERE dataset_id = ? ORDER BY ordinal, id", [dataset_id]
    ).fetchall()
    return [DerivedSignal(r[0], r[1], r[2], r[3], r[4], db._loads(r[5]), r[6])
            for r in rows]


def names_for_dataset(dataset_id: int) -> list[str]:
    return [d.name for d in list_for_dataset(dataset_id)]


def _names_by_role(dataset_id: int, role: str) -> list[str]:
    return [d.name for d in list_for_dataset(dataset_id)
            if (KINDS[d.kind].out_role if d.kind in KINDS else "numeric") == role]


def numeric_names(dataset_id: int) -> list[str]:
    """Derived signals whose output is a numeric channel."""
    return _names_by_role(dataset_id, "numeric")


def flag_names(dataset_id: int) -> list[str]:
    """Derived signals whose output is a 0/1 event flag."""
    return _names_by_role(dataset_id, "flag")


def delete(derived_id: int) -> None:
    db.get_con().execute("DELETE FROM derived_signals WHERE id = ?", [derived_id])


def delete_for_dataset(dataset_id: int) -> None:
    db.get_con().execute("DELETE FROM derived_signals WHERE dataset_id = ?", [dataset_id])


# --------------------------------------------------------------------------- #
#  Computation
# --------------------------------------------------------------------------- #
def compute_all(dataset_id: int, df: pd.DataFrame,
                t: np.ndarray) -> list[tuple[str, np.ndarray, str]]:
    """Compute every derived signal for a dataset, in evaluation order.

    A derived signal may reference a file column or an earlier derived signal.
    Returns an ordered list of ``(name, values, out_role)`` where out_role is
    "numeric" or "flag". Missing sources are skipped rather than raising.
    """
    out: list[tuple[str, np.ndarray, str]] = []
    work = {c: df[c] for c in df.columns}
    for d in list_for_dataset(dataset_id):
        kind = KINDS.get(d.kind)
        if kind is None or d.source is None:
            continue
        src = work.get(d.source)
        if src is None:
            continue
        y = pd.to_numeric(src, errors="coerce").to_numpy(dtype=float)
        try:
            vals = kind.compute(y, t, d.params or {})
        except Exception:  # noqa: BLE001 — never let one bad signal break loading
            vals = np.full(len(df), np.nan)
        vals = np.asarray(vals, dtype=float)
        out.append((d.name, vals, kind.out_role))
        work[d.name] = pd.Series(vals)  # allow chaining (jerk from accel, etc.)
    return out
