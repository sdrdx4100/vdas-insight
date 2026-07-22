"""Statistics view: descriptive stats table + histogram / scatter explorer."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6 import QtWidgets

from vdas.analysis.metrics import numeric_stats
from .. import services, theme
from ..state import AppState
from ..widgets.charts import Histogram
from ..widgets.common import section_label
from ..widgets.plots import style_axes

_COLS = ["n", "mean", "std", "min", "p05", "p50", "p95", "max"]


class StatsView(QtWidgets.QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        lay.addWidget(section_label("数値列の記述統計"))
        self.table = QtWidgets.QTableWidget(0, len(_COLS) + 1)
        self.table.setHorizontalHeaderLabels(["column"] + _COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setMaximumHeight(230)
        lay.addWidget(self.table)

        ctl = QtWidgets.QHBoxLayout()
        ctl.addWidget(QtWidgets.QLabel("ヒストグラム:"))
        self.hist_combo = QtWidgets.QComboBox(); self.hist_combo.setMinimumWidth(160)
        ctl.addWidget(self.hist_combo)
        ctl.addSpacing(20)
        ctl.addWidget(QtWidgets.QLabel("散布図 X:"))
        self.x_combo = QtWidgets.QComboBox(); self.x_combo.setMinimumWidth(160)
        ctl.addWidget(self.x_combo)
        ctl.addWidget(QtWidgets.QLabel("Y:"))
        self.y_combo = QtWidgets.QComboBox(); self.y_combo.setMinimumWidth(160)
        ctl.addWidget(self.y_combo)
        ctl.addStretch(1)
        lay.addLayout(ctl)

        split = QtWidgets.QSplitter()
        self.hist = Histogram("")
        split.addWidget(self.hist)
        self.scatter_w = pg.GraphicsLayoutWidget()
        self.scatter_p = self.scatter_w.addPlot()
        style_axes(self.scatter_p)
        split.addWidget(self.scatter_w)
        lay.addWidget(split, 1)

        for c in (self.hist_combo, self.x_combo, self.y_combo):
            c.currentIndexChanged.connect(self._redraw)
        self.state.currentDatasetChanged.connect(lambda _id: self.rebuild())
        self.state.rolesChanged.connect(lambda _id: self.rebuild())

    def rebuild(self):
        d = self.state.current_dataset()
        if not d or not d.exists:
            return
        pdd = services.get_prepared(d)
        cols = pdd.numeric_cols
        self.table.setRowCount(0)
        for c in cols:
            s = numeric_stats(pdd, c)
            if not s.get("n"):
                continue
            r = self.table.rowCount(); self.table.insertRow(r)
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(c))
            for j, key in enumerate(_COLS):
                val = s.get(key, "")
                txt = f"{val:,.3g}" if isinstance(val, float) else str(val)
                self.table.setItem(r, j + 1, QtWidgets.QTableWidgetItem(txt))
        self.table.resizeColumnsToContents()

        for combo, default in ((self.hist_combo, 0), (self.x_combo, 0),
                               (self.y_combo, min(1, len(cols) - 1))):
            combo.blockSignals(True)
            combo.clear(); combo.addItems(cols)
            if cols:
                combo.setCurrentIndex(max(0, min(default, len(cols) - 1)))
            combo.blockSignals(False)
        self._redraw()

    def _redraw(self):
        d = self.state.current_dataset()
        if not d or not d.exists:
            return
        pdd = services.get_prepared(d)
        hc = self.hist_combo.currentText()
        if hc and hc in pdd.df:
            self.hist.set_data(pd.to_numeric(pdd.df[hc], errors="coerce").to_numpy(float),
                               xlabel=hc)
        xc, yc = self.x_combo.currentText(), self.y_combo.currentText()
        self.scatter_p.clear()
        if xc and yc and xc in pdd.df and yc in pdd.df:
            x = pd.to_numeric(pdd.df[xc], errors="coerce").to_numpy(float)
            y = pd.to_numeric(pdd.df[yc], errors="coerce").to_numpy(float)
            m = np.isfinite(x) & np.isfinite(y)
            step = max(1, int(m.sum() // 20000))  # cap points drawn
            self.scatter_p.addItem(pg.ScatterPlotItem(
                x=x[m][::step], y=y[m][::step], size=4,
                brush=pg.mkBrush(58, 135, 229, 90), pen=None))
            self.scatter_p.setLabel("bottom", xc, color=theme.INK_DIM)
            self.scatter_p.setLabel("left", yc, color=theme.INK_DIM)
