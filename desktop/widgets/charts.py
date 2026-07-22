"""Reusable pyqtgraph chart widgets: bar, grouped bar, histogram, heatmap."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore

from .. import theme
from .plots import style_axes

# Sequential blue ramp for heatmaps: low (near-white) → high (dark ink).
_SEQ = ["#eaf2fc", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def _seq_lut(n=256):
    stops = np.linspace(0, 1, len(_SEQ))
    cmap = pg.ColorMap(stops, [pg.mkColor(c).getRgb() for c in _SEQ])
    return cmap.getLookupTable(0.0, 1.0, n)


class BarChart(pg.GraphicsLayoutWidget):
    """Vertical bar chart with categorical x-axis and optional value labels."""

    def __init__(self, ylabel: str = ""):
        super().__init__()
        self.plot = self.addPlot()
        style_axes(self.plot)
        self.plot.setLabel("left", ylabel, color=theme.INK_DIM)
        self._ylabel = ylabel

    def set_data(self, labels, values, colors=None, value_fmt="{:.2f}",
                 scatter=None):
        self.plot.clear()
        labels = [str(x) for x in labels]
        x = np.arange(len(labels), dtype=float)
        vals = np.asarray(values, dtype=float)
        if colors is None:
            colors = [theme.series_color(i) for i in range(len(labels))]
        for xi, v, col in zip(x, vals, colors):
            if not np.isfinite(v):
                continue
            self.plot.addItem(pg.BarGraphItem(x=[xi], height=[v], width=0.62,
                                              brush=pg.mkBrush(col),
                                              pen=pg.mkPen(col)))
            t = pg.TextItem(value_fmt.format(v), color=theme.INK, anchor=(0.5, 1))
            t.setPos(xi, v)
            self.plot.addItem(t)
        # optional per-item scatter overlay (e.g. per-dataset spread)
        if scatter is not None:
            for xi, pts, col in zip(x, scatter, colors):
                pts = np.asarray(pts, dtype=float)
                pts = pts[np.isfinite(pts)]
                if len(pts):
                    jitter = (np.random.default_rng(0).random(len(pts)) - 0.5) * 0.28
                    # dark dot + light halo → visible both on colored bars and surface
                    sp = pg.ScatterPlotItem(
                        x=xi + jitter, y=pts, size=7,
                        brush=pg.mkBrush(theme.INK),
                        pen=pg.mkPen(theme.BG_PLOT, width=1.4))
                    sp.setZValue(20)
                    self.plot.addItem(sp)
        ax = self.plot.getAxis("bottom")
        ax.setTicks([list(zip(x.tolist(), labels))])
        self.plot.setLabel("left", self._ylabel, color=theme.INK_DIM)
        vmax = np.nanmax(vals) if len(vals) and np.isfinite(np.nanmax(vals)) else 1
        self.plot.setYRange(0, vmax * 1.18 if vmax > 0 else 1)


class Histogram(pg.GraphicsLayoutWidget):
    def __init__(self, xlabel: str = "", color_slot: int = 0):
        super().__init__()
        self.plot = self.addPlot()
        style_axes(self.plot)
        self.plot.setLabel("left", "count", color=theme.INK_DIM)
        self._xlabel = xlabel
        self._color = theme.series_color(color_slot)

    def set_data(self, values, bins: int = 30, xlabel: str | None = None):
        self.plot.clear()
        values = np.asarray(values, dtype=float)
        values = values[np.isfinite(values)]
        if len(values) == 0:
            return
        y, edges = np.histogram(values, bins=bins)
        x0 = edges[:-1]
        w = np.diff(edges)
        self.plot.addItem(pg.BarGraphItem(x0=x0, width=w, height=y,
                                          brush=pg.mkBrush(self._color),
                                          pen=pg.mkPen(theme.BG_PLOT)))
        self.plot.setLabel("bottom", xlabel or self._xlabel, color=theme.INK_DIM)


class Heatmap(pg.GraphicsLayoutWidget):
    """Matrix heatmap with categorical tick labels and a colorbar."""

    def __init__(self, xlabel: str = "", ylabel: str = ""):
        super().__init__()
        self.plot = self.addPlot()
        self.plot.setLabel("bottom", xlabel, color=theme.INK_DIM)
        self.plot.setLabel("left", ylabel, color=theme.INK_DIM)
        self.plot.getAxis("left").setPen(pg.mkPen(theme.INK_FAINT))
        self.plot.getAxis("bottom").setPen(pg.mkPen(theme.INK_FAINT))
        self.plot.getAxis("left").setTextPen(pg.mkPen(theme.INK_DIM))
        self.plot.getAxis("bottom").setTextPen(pg.mkPen(theme.INK_DIM))
        self.plot.setAspectLocked(False)
        self.img = pg.ImageItem()
        self.img.setLookupTable(_seq_lut())
        self.plot.addItem(self.img)
        self._bar = None

    def set_matrix(self, mat, row_labels, col_labels):
        z = np.asarray(mat, dtype=float)
        # ImageItem is column-major on axis0=x; transpose so rows map to y.
        self.img.setImage(z.T, autoLevels=False)
        vmax = np.nanmax(z) if z.size else 1
        self.img.setLevels([0, vmax if vmax > 0 else 1])
        self.img.setRect(QtCore.QRectF(0, 0, len(col_labels), len(row_labels)))
        xax = self.plot.getAxis("bottom")
        yax = self.plot.getAxis("left")
        xax.setTicks([[(i + 0.5, str(c)) for i, c in enumerate(col_labels)]])
        yax.setTicks([[(i + 0.5, str(r)) for i, r in enumerate(row_labels)]])
        # value overlays
        for it in [i for i in self.plot.items if isinstance(i, pg.TextItem)]:
            self.plot.removeItem(it)
        hi = vmax if vmax > 0 else 1
        for r in range(z.shape[0]):
            for c in range(z.shape[1]):
                if z[r, c] > 0:
                    # white ink on dark (high) cells, dark ink on light (low) cells
                    col = "#ffffff" if z[r, c] / hi > 0.55 else theme.INK
                    t = pg.TextItem(f"{int(z[r, c])}", color=col, anchor=(0.5, 0.5))
                    t.setPos(c + 0.5, r + 0.5)
                    self.plot.addItem(t)
        self.plot.setYRange(0, len(row_labels))
        self.plot.setXRange(0, len(col_labels))
        self.plot.getViewBox().invertY(True)
