"""pyqtgraph-based measurement plot widgets (the instrument core)."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore

from .. import theme


def style_axes(plot: pg.PlotItem) -> None:
    plot.showGrid(x=True, y=True, alpha=0.15)
    plot.getViewBox().setDefaultPadding(0.02)
    for ax in ("left", "bottom"):
        a = plot.getAxis(ax)
        a.setPen(pg.mkPen(theme.INK_FAINT))
        a.setTextPen(pg.mkPen(theme.INK_DIM))


class LinkedTimePlots(pg.GraphicsLayoutWidget):
    """A vertical stack of x-linked time-series plots with a shared crosshair.

    Emits ``cursorMoved(t, readouts)`` where readouts is a list of
    ``(name, value)`` at the cursor's time — wire it to a status bar.
    """

    cursorMoved = QtCore.Signal(float, list)

    def __init__(self):
        super().__init__()
        self.ci.setContentsMargins(6, 6, 6, 6)
        self.ci.setSpacing(8)
        self._t: np.ndarray = np.array([])
        self._series: list[dict] = []       # {name, y, plot, curve, vline, label}
        self._plots: list[pg.PlotItem] = []
        self.scene().sigMouseMoved.connect(self._on_mouse)

    # ---------------------------------------------------------------- build
    def set_signals(self, t: np.ndarray, signals: list[dict], xlabel: str = "time (s)"):
        """signals: list of {name, y, color, step(bool)}."""
        self.clear()
        self._plots = []
        self._series = []
        self._t = np.asarray(t, dtype=float)
        if not signals:
            return
        n = len(signals)
        for i, sig in enumerate(signals):
            p = self.addPlot(row=i, col=0)
            style_axes(p)
            p.setLabel("left", sig["name"], color=theme.INK_DIM)
            if i < n - 1:
                p.getAxis("bottom").setStyle(showValues=False)
            else:
                p.setLabel("bottom", xlabel, color=theme.INK_DIM)
            if self._plots:
                p.setXLink(self._plots[0])
            y = np.asarray(sig["y"], dtype=float)
            pen = pg.mkPen(sig.get("color", theme.series_color(i)), width=1.5)
            if sig.get("step"):
                curve = p.plot(self._t, y, pen=pen, stepMode="right",
                               connect="finite")
            else:
                curve = p.plot(self._t, y, pen=pen, connect="finite")
            curve.setDownsampling(auto=True, method="peak")
            curve.setClipToView(True)

            vline = pg.InfiniteLine(angle=90, movable=False,
                                    pen=pg.mkPen(theme.INK_FAINT, width=1,
                                                 style=QtCore.Qt.DashLine))
            vline.setZValue(10)
            p.addItem(vline, ignoreBounds=True)
            label = pg.TextItem(anchor=(0, 1), color=theme.INK)
            label.setZValue(11)
            p.addItem(label, ignoreBounds=True)
            label.hide()

            self._plots.append(p)
            self._series.append({"name": sig["name"], "y": y, "plot": p,
                                 "vline": vline, "label": label})
        self.newAxisRow()

    def newAxisRow(self):
        pass

    # ---------------------------------------------------------------- cursor
    def _on_mouse(self, pos):
        if not self._plots or len(self._t) == 0:
            return
        vb = self._plots[0].getViewBox()
        if not self._plots[0].sceneBoundingRect().contains(pos) and not any(
                p.sceneBoundingRect().contains(pos) for p in self._plots):
            for s in self._series:
                s["vline"].hide(); s["label"].hide()
            return
        x = vb.mapSceneToView(pos).x()
        idx = int(np.clip(np.searchsorted(self._t, x), 0, len(self._t) - 1))
        tx = float(self._t[idx])
        readouts = []
        for s in self._series:
            s["vline"].setPos(tx)
            s["vline"].show()
            val = s["y"][idx] if idx < len(s["y"]) else np.nan
            readouts.append((s["name"], val))
            yr = s["plot"].getViewBox().viewRange()[1]
            s["label"].setText(f"{val:.4g}")
            s["label"].setPos(tx, yr[1])
            s["label"].show()
        self.cursorMoved.emit(tx, readouts)

    def add_event_markers(self, plot_index: int, xs: np.ndarray,
                          color: str, y: float | None = None):
        """Drop vertical tick markers (e.g. shift events) on one plot."""
        if plot_index >= len(self._plots) or len(xs) == 0:
            return
        p = self._plots[plot_index]
        for x in xs:
            line = pg.InfiniteLine(pos=float(x), angle=90, movable=False,
                                   pen=pg.mkPen(color, width=1,
                                                style=QtCore.Qt.DotLine))
            line.setZValue(5)
            p.addItem(line, ignoreBounds=True)


def bar_item(x_idx, heights, color, width=0.6):
    return pg.BarGraphItem(x=x_idx, height=heights, width=width,
                           brush=pg.mkBrush(color), pen=pg.mkPen(color))
