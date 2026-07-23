"""2D operating-map aggregation (engine-map style).

Bin two signals onto an X-Y grid and colour each cell by a third quantity:
time-share (density), sample count, or the mean / std of a chosen signal —
the classic powertrain "how much time / what value at each operating point"
map (cf. Ono Sokki EX-Summary contour maps).

All aggregates are computed from 2D histograms so they scale to millions of
samples: mean = Σz / count, std from Σz and Σz² per cell.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .core import PreparedData

# Z aggregation modes.
MODE_DENSITY = "density"   # % of time (samples) in each cell
MODE_COUNT = "count"       # raw sample count
MODE_MEAN = "mean"         # mean of a chosen signal
MODE_STD = "std"           # std of a chosen signal

MODE_LABELS = {
    MODE_DENSITY: "滞在割合 (%)",
    MODE_COUNT: "サンプル数",
    MODE_MEAN: "平均",
    MODE_STD: "標準偏差",
}


@dataclass
class MapResult:
    z: np.ndarray            # (nx, ny), NaN where empty
    x_edges: np.ndarray      # length nx+1
    y_edges: np.ndarray      # length ny+1
    zlabel: str
    n_used: int


def _num(df: pd.DataFrame, col: str) -> np.ndarray:
    return pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)


def compute_map(pd_data: PreparedData, xcol: str, ycol: str, mode: str,
                zcol: str | None = None, bins: int = 40) -> MapResult:
    df = pd_data.df
    x = _num(df, xcol)
    y = _num(df, ycol)
    mask = np.isfinite(x) & np.isfinite(y)
    z = None
    if mode in (MODE_MEAN, MODE_STD):
        if not zcol or zcol not in df:
            return MapResult(np.zeros((1, 1)) * np.nan, np.array([0, 1]),
                             np.array([0, 1]), "", 0)
        z = _num(df, zcol)
        mask &= np.isfinite(z)
    x, y = x[mask], y[mask]
    if z is not None:
        z = z[mask]
    if len(x) < 2:
        return MapResult(np.zeros((1, 1)) * np.nan, np.array([0, 1]),
                         np.array([0, 1]), "", 0)

    count, xe, ye = np.histogram2d(x, y, bins=bins)
    with np.errstate(invalid="ignore", divide="ignore"):
        if mode == MODE_COUNT:
            zg = count.copy()
            zlabel = MODE_LABELS[MODE_COUNT]
        elif mode == MODE_DENSITY:
            total = count.sum()
            zg = count / total * 100.0 if total else count
            zlabel = MODE_LABELS[MODE_DENSITY]
        else:
            s, _, _ = np.histogram2d(x, y, bins=[xe, ye], weights=z)
            mean = s / count
            if mode == MODE_MEAN:
                zg = mean
                zlabel = f"{zcol} 平均"
            else:
                s2, _, _ = np.histogram2d(x, y, bins=[xe, ye], weights=z * z)
                var = np.clip(s2 / count - mean * mean, 0.0, None)
                zg = np.sqrt(var)
                zlabel = f"{zcol} 標準偏差"
        zg = zg.astype(float)
        zg[count == 0] = np.nan       # empty cells → transparent
    return MapResult(z=zg, x_edges=xe, y_edges=ye, zlabel=zlabel, n_used=int(len(x)))
