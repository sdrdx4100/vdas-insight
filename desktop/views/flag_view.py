"""Flag (0/1) analytics view: summary table, timeline, interval histograms."""
from __future__ import annotations

import numpy as np
from PySide6 import QtWidgets

from vdas.analysis import flags
from .. import services, theme
from ..state import AppState
from ..widgets.charts import Histogram
from ..widgets.common import MetricStrip, section_label
from ..widgets.plots import LinkedTimePlots


class FlagView(QtWidgets.QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("フラグ:"))
        self.combo = QtWidgets.QComboBox()
        self.combo.setMinimumWidth(200)
        top.addWidget(self.combo)
        top.addStretch(1)
        lay.addLayout(top)

        self.metrics = MetricStrip()
        lay.addWidget(self.metrics)

        self.msg = QtWidgets.QLabel()
        self.msg.setObjectName("dim")
        lay.addWidget(self.msg)

        lay.addWidget(section_label("フラグの推移"))
        self.timeline = LinkedTimePlots()
        self.timeline.setMaximumHeight(200)
        lay.addWidget(self.timeline)

        hsplit = QtWidgets.QSplitter()
        lw = QtWidgets.QWidget(); lv = QtWidgets.QVBoxLayout(lw); lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(section_label("ON 時間の分布"))
        self.on_hist = Histogram("ON 時間 (s)", color_slot=1)
        lv.addWidget(self.on_hist)
        rw = QtWidgets.QWidget(); rv = QtWidgets.QVBoxLayout(rw); rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(section_label("立上り間隔の分布"))
        self.int_hist = Histogram("間隔 (s)", color_slot=2)
        rv.addWidget(self.int_hist)
        hsplit.addWidget(lw); hsplit.addWidget(rw)
        lay.addWidget(hsplit, 1)

        self.combo.currentIndexChanged.connect(self._on_flag_change)
        self.state.currentDatasetChanged.connect(lambda _id: self.rebuild())
        self.state.rolesChanged.connect(lambda _id: self.rebuild())

    def rebuild(self):
        d = self.state.current_dataset()
        if not d or not d.exists:
            return
        pdd = services.get_prepared(d)
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItems(pdd.flag_cols)
        self.combo.blockSignals(False)
        if not pdd.flag_cols:
            self.msg.setText("フラグ役割（0/1）の列がありません。")
            self.metrics.set_metrics([])
            self.timeline.set_signals(np.array([]), [])
            self.on_hist.set_data([]); self.int_hist.set_data([])
            return
        self.msg.setText("")
        self._on_flag_change()

    def _on_flag_change(self):
        d = self.state.current_dataset()
        if not d:
            return
        col = self.combo.currentText()
        if not col:
            return
        pdd = services.get_prepared(d)
        iv = flags.intervals(pdd, col)
        self.metrics.set_metrics([
            ("activations", f"{iv['activations']:,}", ""),
            ("per hour", _fmt(iv["activations_per_hour"]), "/h"),
            ("duty", _fmt(iv["duty_cycle"] * 100), "%"),
            ("mean ON", _fmt(iv["mean_on_s"]), "s"),
            ("mean interval", _fmt(iv["mean_interval_s"]), "s"),
        ])
        y = (pdd.df[col].astype(float) > 0.5).astype(float).to_numpy()
        self.timeline.set_signals(pdd.t, [{"name": col, "y": y,
                                           "color": theme.ROLE_COLORS["flag"], "step": True}])
        self.on_hist.set_data(iv["on_durations"])
        self.int_hist.set_data(iv["between_activations"])


def _fmt(v):
    try:
        f = float(v)
        return "—" if f != f else f"{f:,.2f}"
    except (TypeError, ValueError):
        return "—"
