"""Row-level conditions for gated (conditional) aggregation.

A *condition* is a list of predicates on signals (e.g. ``vehicle_speed_kph <=
70`` AND ``current_gear >= 2``) combined with AND. ``compute_mask`` turns it
into a per-sample boolean mask; metrics computed with that mask only count
samples / events where the condition holds, and normalise rates by the
in-condition time.

A predicate whose signal is missing from a dataset excludes that dataset's
samples entirely (mask all False) — the condition cannot be verified, so those
samples are not silently included.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .core import PreparedData

# operator key -> (label, arity)  arity 1 = value, 2 = value+value2 (between)
OPS = {
    "<=": "≤",
    "<": "<",
    ">=": "≥",
    ">": ">",
    "==": "=",
    "!=": "≠",
    "abs<=": "|x| ≤",
    "abs>=": "|x| ≥",
    "between": "範囲 [a, b]",
}


@dataclass
class Predicate:
    signal: str
    op: str
    value: float
    value2: float = 0.0

    def label(self) -> str:
        if self.op == "between":
            return f"{self.value:g} ≤ {self.signal} ≤ {self.value2:g}"
        return f"{self.signal} {OPS.get(self.op, self.op)} {self.value:g}"


def _apply(v: np.ndarray, p: Predicate) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        if p.op == "<=":
            m = v <= p.value
        elif p.op == "<":
            m = v < p.value
        elif p.op == ">=":
            m = v >= p.value
        elif p.op == ">":
            m = v > p.value
        elif p.op == "==":
            m = v == p.value
        elif p.op == "!=":
            m = v != p.value
        elif p.op == "abs<=":
            m = np.abs(v) <= p.value
        elif p.op == "abs>=":
            m = np.abs(v) >= p.value
        elif p.op == "between":
            lo, hi = sorted((p.value, p.value2))
            m = (v >= lo) & (v <= hi)
        else:
            m = np.ones(len(v), dtype=bool)
    return m & np.isfinite(v)


def compute_mask(pd_data: PreparedData, predicates: list[Predicate]) -> np.ndarray:
    n = pd_data.n
    mask = np.ones(n, dtype=bool)
    for p in predicates:
        if not p.signal or p.signal not in pd_data.df.columns:
            return np.zeros(n, dtype=bool)     # cannot verify → exclude all
        v = pd.to_numeric(pd_data.df[p.signal], errors="coerce").to_numpy(dtype=float)
        mask &= _apply(v, p)
    return mask


def label(predicates: list[Predicate]) -> str:
    return " かつ ".join(p.label() for p in predicates) if predicates else ""
