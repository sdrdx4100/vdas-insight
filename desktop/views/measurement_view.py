"""Measurement view — the oscilloscope: linked time-series of chosen signals."""
from __future__ import annotations

import numpy as np
import pandas as pd
from PySide6 import QtWidgets

from vdas import datasets as ds_mod
from .. import services, theme
from ..state import AppState
from ..widgets.common import MetricStrip
from ..widgets.plots import LinkedTimePlots


class MeasurementView(QtWidgets.QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        self.metrics = MetricStrip()
        lay.addWidget(self.metrics)

        self.plots = LinkedTimePlots()
        lay.addWidget(self.plots, 1)

        self.hint = QtWidgets.QLabel(
            "左の『信号』パネルで表示したい信号にチェックを入れてください。")
        self.hint.setObjectName("dim")
        lay.addWidget(self.hint)

        self.plots.cursorMoved.connect(self._on_cursor)
        self.state.currentDatasetChanged.connect(lambda _id: self.rebuild())
        self.state.plotSelectionChanged.connect(lambda _s: self.rebuild())
        self.state.rolesChanged.connect(lambda _id: self.rebuild())
        self._cursor_cb = None

    def set_cursor_callback(self, cb):
        self._cursor_cb = cb

    def rebuild(self):
        d = self.state.current_dataset()
        if not d or not d.exists:
            self.plots.set_signals(np.array([]), [])
            self.metrics.set_metrics([])
            return
        pdd = services.get_prepared(d)
        self._update_metrics(pdd)

        names = self.state.plot_signals
        gear_col = ds_mod.gear_column(d.id)
        flag_cols = set(ds_mod.flag_columns(d.id))
        signals = []
        for i, name in enumerate(names):
            if name not in pdd.df.columns:
                continue
            y = pd.to_numeric(pdd.df[name], errors="coerce").to_numpy(float)
            step = name == gear_col or name in flag_cols
            color = (theme.ROLE_COLORS["gear"] if name == gear_col
                     else theme.ROLE_COLORS["flag"] if name in flag_cols
                     else theme.series_color(i))
            signals.append({"name": name, "y": y, "color": color, "step": step})
        self.plots.set_signals(pdd.t, signals)
        self.hint.setVisible(not signals)

    def _update_metrics(self, pdd):
        rate = (1.0 / pdd.dt) if pdd.dt else 0.0
        dist = pdd.distance_km()
        items = [
            ("rows", f"{pdd.n:,}", ""),
            ("duration", f"{pdd.duration_h:.3f}", "h"),
            ("sampling", f"{rate:.1f}", "Hz"),
        ]
        if dist is not None:
            items.append(("distance", f"{dist:.2f}", "km"))
        self.metrics.set_metrics(items)

    def _on_cursor(self, t, readouts):
        if self._cursor_cb:
            txt = "  ·  ".join(f"{n}={v:.4g}" for n, v in readouts[:6])
            self._cursor_cb(f"t = {t:.2f} s    {txt}")
