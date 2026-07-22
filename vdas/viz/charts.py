"""Plotly chart builders.

All charts share one theme and draw categorical hues from the validated
fixed-order palette (never cycled beyond 8 — past that we fold to "Other").
Charts are interactive by default (hover, zoom, pan). Multi-signal time series
use stacked sub-plots that share the x-axis rather than a dual y-axis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..config import PALETTE, SEQUENTIAL, STATUS

# --- Ink / chrome (light theme; charts render on a near-white surface) ------
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"

_LAYOUT = dict(
    template="plotly_white",
    font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif',
              color=INK, size=13),
    paper_bgcolor=SURFACE,
    plot_bgcolor=SURFACE,
    margin=dict(l=60, r=24, t=48, b=48),
    hoverlabel=dict(font_size=12, bgcolor="white"),
    colorway=PALETTE,
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=INK2)),
)


def color_for(i: int) -> str:
    """Categorical color by slot index (fixed order, folds past 8)."""
    return PALETTE[i % len(PALETTE)]


def _apply(fig: go.Figure, title: str | None = None, height: int = 420) -> go.Figure:
    fig.update_layout(**_LAYOUT, height=height)
    if title:
        fig.update_layout(title=dict(text=title, font=dict(size=16, color=INK), x=0.01))
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=AXIS, linecolor=AXIS,
                     ticks="outside", tickcolor=AXIS, color=INK2)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=AXIS, linecolor=AXIS,
                     ticks="outside", tickcolor=AXIS, color=INK2)
    return fig


# --------------------------------------------------------------------------- #
#  Time series
# --------------------------------------------------------------------------- #
def timeseries(t: np.ndarray, df: pd.DataFrame, columns: list[str],
               xlabel: str = "time (s)", height: int | None = None) -> go.Figure:
    """Stacked, x-shared sub-plots — one signal per row (no dual axis)."""
    columns = columns[:8] or []
    if not columns:
        return _apply(go.Figure(), height=200)
    rows = len(columns)
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True,
                        vertical_spacing=0.03,
                        subplot_titles=columns)
    for i, col in enumerate(columns):
        y = pd.to_numeric(df[col], errors="coerce")
        fig.add_trace(
            go.Scattergl(x=t, y=y, mode="lines", name=col,
                         line=dict(width=1.6, color=color_for(i)),
                         showlegend=False,
                         hovertemplate=f"{col}: %{{y:.3g}}<br>t=%{{x:.1f}}s<extra></extra>"),
            row=i + 1, col=1,
        )
    fig.update_xaxes(title_text=xlabel, row=rows, col=1)
    h = height or max(180 * rows, 260)
    fig.update_layout(**_LAYOUT, height=h)
    fig.update_xaxes(gridcolor=GRID, linecolor=AXIS, color=INK2)
    fig.update_yaxes(gridcolor=GRID, linecolor=AXIS, color=INK2)
    for ann in fig.layout.annotations:
        ann.font = dict(size=12, color=INK2)
        ann.x = 0.0
        ann.xanchor = "left"
    return fig


def gear_timeline(t: np.ndarray, gear: pd.Series, shift_times: np.ndarray | None = None,
                  height: int = 300) -> go.Figure:
    """Step plot of gear over time, with optional shift-event markers."""
    fig = go.Figure()
    fig.add_trace(go.Scattergl(
        x=t, y=gear, mode="lines", name="gear",
        line=dict(width=1.8, color=PALETTE[0], shape="hv"),
        hovertemplate="gear %{y}<br>t=%{x:.1f}s<extra></extra>"))
    if shift_times is not None and len(shift_times):
        gmin = float(np.nanmin(pd.to_numeric(gear, errors="coerce")))
        fig.add_trace(go.Scattergl(
            x=shift_times, y=[gmin] * len(shift_times), mode="markers",
            name="shift", marker=dict(color=STATUS["serious"], size=7, symbol="line-ns-open"),
            hovertemplate="shift @ %{x:.1f}s<extra></extra>"))
    _apply(fig, height=height)
    fig.update_yaxes(title_text="gear", dtick=1)
    fig.update_xaxes(title_text="time (s)")
    return fig


# --------------------------------------------------------------------------- #
#  Gear analytics
# --------------------------------------------------------------------------- #
def time_in_gear(tig: pd.DataFrame, height: int = 360) -> go.Figure:
    """Horizontal bar: share of time spent in each gear."""
    fig = go.Figure()
    labels = [f"{g}" for g in tig["gear"]]
    fig.add_trace(go.Bar(
        y=labels, x=tig["share"] * 100.0, orientation="h",
        marker=dict(color=PALETTE[2]),
        text=[f"{s*100:.1f}%" for s in tig["share"]], textposition="outside",
        hovertemplate="gear %{y}: %{x:.2f}% (%{customdata:.0f}s)<extra></extra>",
        customdata=tig["duration_s"]))
    _apply(fig, height=height)
    fig.update_xaxes(title_text="time share (%)")
    fig.update_yaxes(title_text="gear", type="category")
    return fig


def transition_heatmap(mat: pd.DataFrame, height: int = 420) -> go.Figure:
    """Heatmap of shift counts from-gear (row) → to-gear (col)."""
    fig = go.Figure(go.Heatmap(
        z=mat.values, x=[str(c) for c in mat.columns], y=[str(i) for i in mat.index],
        colorscale=[[i / (len(SEQUENTIAL) - 1), c] for i, c in enumerate(SEQUENTIAL)],
        hovertemplate="%{y} → %{x}: %{z} 回<extra></extra>",
        colorbar=dict(title="回数")))
    _apply(fig, height=height)
    fig.update_xaxes(title_text="to gear", type="category")
    fig.update_yaxes(title_text="from gear", type="category", autorange="reversed")
    return fig


# --------------------------------------------------------------------------- #
#  Flag analytics
# --------------------------------------------------------------------------- #
def flag_timeline(t: np.ndarray, series: pd.Series, name: str, height: int = 220) -> go.Figure:
    on = (pd.to_numeric(series, errors="coerce") > 0.5).astype(int)
    fig = go.Figure()
    fig.add_trace(go.Scattergl(
        x=t, y=on, mode="lines", name=name, fill="tozeroy",
        line=dict(width=1.4, color=PALETTE[1], shape="hv"),
        fillcolor="rgba(235,104,52,0.18)",
        hovertemplate=name + ": %{y}<br>t=%{x:.1f}s<extra></extra>"))
    _apply(fig, height=height)
    fig.update_yaxes(title_text=name, dtick=1, range=[-0.1, 1.1])
    fig.update_xaxes(title_text="time (s)")
    return fig


def duration_histogram(values: np.ndarray, title: str, xlabel: str,
                       color_slot: int = 0, height: int = 340) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=values, marker=dict(color=color_for(color_slot)),
        hovertemplate=f"{xlabel}: %{{x}}<br>count: %{{y}}<extra></extra>"))
    _apply(fig, title=title, height=height)
    fig.update_xaxes(title_text=xlabel)
    fig.update_yaxes(title_text="count")
    return fig


# --------------------------------------------------------------------------- #
#  Cohort comparison
# --------------------------------------------------------------------------- #
def cohort_bar(df: pd.DataFrame, metric_key: str, label: str, unit: str,
               is_percent: bool = False, height: int = 420) -> go.Figure:
    """Grouped bar comparing cohorts on a pooled metric. One color per cohort."""
    vals = df[metric_key].astype(float)
    disp = vals * 100.0 if is_percent else vals
    fig = go.Figure()
    colors = [color_for(i) for i in range(len(df))]
    fig.add_trace(go.Bar(
        x=df["tag"], y=disp, marker=dict(color=colors),
        text=[f"{v:.2f}" for v in disp], textposition="outside",
        hovertemplate="%{x}: %{y:.3g} " + unit + "<extra></extra>"))
    _apply(fig, title=f"{label}（コホート比較）", height=height)
    fig.update_yaxes(title_text=f"{label} ({unit})")
    fig.update_xaxes(title_text="tag", type="category")
    return fig


def cohort_box(cohorts, metric_key: str, label: str, unit: str,
               is_percent: bool = False, height: int = 420) -> go.Figure:
    """Per-dataset distribution of a metric within each cohort (box + points)."""
    fig = go.Figure()
    for i, c in enumerate(cohorts):
        vals = c.spread(metric_key)
        vals = vals[np.isfinite(vals)]
        if is_percent:
            vals = vals * 100.0
        fig.add_trace(go.Box(
            y=vals, name=c.tag.name, boxpoints="all", jitter=0.4, pointpos=0,
            marker=dict(color=color_for(i), size=6),
            line=dict(color=color_for(i)),
            hovertemplate="%{y:.3g} " + unit + "<extra></extra>"))
    _apply(fig, title=f"{label}（データ単位の分布）", height=height)
    fig.update_yaxes(title_text=f"{label} ({unit})")
    fig.update_xaxes(title_text="tag", type="category")
    fig.update_layout(showlegend=False)
    return fig


def relative_index_bar(idx: pd.Series, label: str, height: int = 400) -> go.Figure:
    """Cohorts indexed to a baseline (=100%)."""
    fig = go.Figure()
    colors = [color_for(i) for i in range(len(idx))]
    fig.add_trace(go.Bar(
        x=idx.index, y=idx.values, marker=dict(color=colors),
        text=[f"{v:.0f}" for v in idx.values], textposition="outside",
        hovertemplate="%{x}: %{y:.1f}<extra></extra>"))
    fig.add_hline(y=100, line=dict(color=MUTED, dash="dash", width=1))
    _apply(fig, title=f"{label} — 相対指数 (基準=100)", height=height)
    fig.update_yaxes(title_text="index")
    fig.update_xaxes(title_text="tag", type="category")
    return fig


def histogram(values: np.ndarray, title: str, xlabel: str, height: int = 340) -> go.Figure:
    return duration_histogram(values, title, xlabel, color_slot=0, height=height)


def scatter(x: np.ndarray, y: np.ndarray, xlabel: str, ylabel: str,
            title: str | None = None, height: int = 420) -> go.Figure:
    fig = go.Figure(go.Scattergl(
        x=x, y=y, mode="markers", marker=dict(color=PALETTE[0], size=5, opacity=0.5),
        hovertemplate=f"{xlabel}: %{{x:.3g}}<br>{ylabel}: %{{y:.3g}}<extra></extra>"))
    _apply(fig, title=title, height=height)
    fig.update_xaxes(title_text=xlabel)
    fig.update_yaxes(title_text=ylabel)
    return fig
