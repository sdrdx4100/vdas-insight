"""Gear analytics view: shift metrics, gear timeline, time-in-gear, transitions."""
from __future__ import annotations

import numpy as np
from PySide6 import QtWidgets

from vdas.analysis import gears
from .. import services, theme
from ..state import AppState
from ..widgets.charts import BarChart, Heatmap
from ..widgets.common import MetricStrip, section_label
from ..widgets.plots import LinkedTimePlots


class GearView(QtWidgets.QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        self.metrics = MetricStrip()
        lay.addWidget(self.metrics)

        self.msg = QtWidgets.QLabel()
        self.msg.setObjectName("dim")
        lay.addWidget(self.msg)

        split = QtWidgets.QSplitter()  # horizontal by default
        lay.addWidget(split, 1)

        # left: gear timeline
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(section_label("ギア段の推移（変速マーカー付き）"))
        self.timeline = LinkedTimePlots()
        lv.addWidget(self.timeline, 1)
        split.addWidget(left)

        # right: time-in-gear + transition matrix
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(section_label("ギア段別 滞在時間（%）"))
        self.tig = BarChart("share (%)")
        rv.addWidget(self.tig, 1)
        rv.addWidget(section_label("変速の遷移行列 (from → to)"))
        self.heat = Heatmap("to gear", "from gear")
        rv.addWidget(self.heat, 1)
        split.addWidget(right)
        split.setSizes([700, 500])

        self.state.currentDatasetChanged.connect(lambda _id: self.rebuild())
        self.state.rolesChanged.connect(lambda _id: self.rebuild())

    def rebuild(self):
        d = self.state.current_dataset()
        if not d or not d.exists:
            return
        pdd = services.get_prepared(d)
        if not pdd.gear_col:
            self.msg.setText("ギア役割の列がありません。右の『役割』で gear を割り当ててください。")
            self.metrics.set_metrics([])
            self.timeline.set_signals(np.array([]), [])
            return
        self.msg.setText("")
        s = gears.summary(pdd)
        self.metrics.set_metrics([
            ("shifts", f"{s['shift_count']:,}", ""),
            ("upshifts", f"{s['upshifts']:,}", ""),
            ("downshifts", f"{s['downshifts']:,}", ""),
            ("per hour", _fmt(s["shifts_per_hour"]), "/h"),
            ("per km", _fmt(s["shifts_per_km"]), "/km"),
        ])
        # timeline
        y = pdd.df[pdd.gear_col].to_numpy(dtype=float)
        self.timeline.set_signals(pdd.t, [{"name": pdd.gear_col, "y": y,
                                           "color": theme.ROLE_COLORS["gear"], "step": True}])
        ev = gears.shift_events(pdd)
        if not ev.empty:
            self.timeline.add_event_markers(0, ev["t"].to_numpy(), theme.STATUS["serious"])
        # time in gear
        tig = gears.time_in_gear(pdd)
        if not tig.empty:
            self.tig.set_data([_glabel(g) for g in tig["gear"]],
                              (tig["share"] * 100).tolist(),
                              colors=[theme.ROLE_COLORS["gear"]] * len(tig),
                              value_fmt="{:.1f}")
        # transition matrix
        mat = gears.transition_matrix(pdd)
        if not mat.empty:
            self.heat.set_matrix(mat.values,
                                 [_glabel(g) for g in mat.index],
                                 [_glabel(g) for g in mat.columns])


def _fmt(v):
    try:
        f = float(v)
        return "—" if f != f else f"{f:,.2f}"
    except (TypeError, ValueError):
        return "—"


def _glabel(g):
    """Render a gear value as a clean label (N for neutral, int when whole)."""
    try:
        f = float(g)
    except (TypeError, ValueError):
        return str(g)
    if f != f:
        return "NaN"
    return "N" if f == 0 else (str(int(f)) if f.is_integer() else f"{f:g}")
