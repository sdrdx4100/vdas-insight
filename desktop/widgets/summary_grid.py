"""Small-multiples grid: a matrix of mini bar charts (one per metric).

An EX-Summary-style overview — every selected metric is a small panel with one
bar per cohort, laid out in a grid so many metrics × cohorts read at a glance.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg

from .. import theme
from .plots import style_axes


class MiniBarGrid(pg.GraphicsLayoutWidget):
    def __init__(self):
        super().__init__()
        self.ci.setContentsMargins(6, 6, 6, 6)
        self.ci.setSpacing(10)
        self._ncols = 3

    def set_panels(self, cohort_labels, colors, panels, ncols: int = 3):
        """panels: list of {title, values(list[float]), is_percent(bool)}."""
        self.clear()
        self._ncols = ncols
        x = np.arange(len(cohort_labels), dtype=float)
        short = [lbl if len(lbl) <= 8 else lbl[:7] + "…" for lbl in cohort_labels]
        for idx, panel in enumerate(panels):
            r, c = divmod(idx, ncols)
            p = self.addPlot(row=r, col=c)
            style_axes(p)
            p.setTitle(panel["title"], color=theme.INK, size="9pt")
            p.getViewBox().setDefaultPadding(0.05)
            scale = 100.0 if panel.get("is_percent") else 1.0
            vals = np.asarray(panel["values"], dtype=float) * scale
            for xi, v, col in zip(x, vals, colors):
                if not np.isfinite(v):
                    continue
                p.addItem(pg.BarGraphItem(x=[xi], height=[v], width=0.62,
                                          brush=pg.mkBrush(col), pen=pg.mkPen(col)))
                t = pg.TextItem(_fmt(v), color=theme.INK_DIM, anchor=(0.5, 1))
                t.setPos(xi, v)
                p.addItem(t)
            ax = p.getAxis("bottom")
            ax.setTicks([list(zip(x.tolist(), short))])
            ax.setStyle(tickFont=_tick_font())
            p.getAxis("left").setStyle(tickFont=_tick_font())
            finite = vals[np.isfinite(vals)]
            vmax = float(finite.max()) if finite.size else 1.0
            vmin = min(0.0, float(finite.min()) if finite.size else 0.0)
            p.setYRange(vmin, vmax * 1.2 if vmax > 0 else 1.0)
        # keep panels a sensible height so the scroll area can scroll
        rows = (len(panels) + ncols - 1) // ncols
        self.setMinimumHeight(max(rows * 200, 200))


def _fmt(v: float) -> str:
    a = abs(v)
    if a >= 100:
        return f"{v:.0f}"
    if a >= 1:
        return f"{v:.1f}"
    return f"{v:.2f}"


def _tick_font():
    from PySide6 import QtGui
    f = QtGui.QFont()
    f.setPointSize(8)
    return f
