"""Cohort 2D map: pooled operating map per tag, and A−B difference map."""
from __future__ import annotations

from PySide6 import QtWidgets

from vdas import datasets as ds_mod
from vdas import derived as derived_mod
from vdas import tags as tags_mod
from vdas.analysis import maps
from ..state import AppState
from ..widgets.charts import HeatMap2D
from ..widgets.condition_bar import ConditionBar

_MODE_SINGLE = "コホート単体"
_MODE_DIFF = "差分 (A − B)"


class CohortMapView(QtWidgets.QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        ctl = QtWidgets.QHBoxLayout()
        self.view_combo = QtWidgets.QComboBox(); self.view_combo.addItems([_MODE_SINGLE, _MODE_DIFF])
        self.a_combo = QtWidgets.QComboBox(); self.a_combo.setMinimumWidth(130)
        self.b_combo = QtWidgets.QComboBox(); self.b_combo.setMinimumWidth(130)
        self.x_combo = QtWidgets.QComboBox(); self.x_combo.setMinimumWidth(130)
        self.y_combo = QtWidgets.QComboBox(); self.y_combo.setMinimumWidth(130)
        self.mode_combo = QtWidgets.QComboBox()
        for k in (maps.MODE_DENSITY, maps.MODE_COUNT, maps.MODE_MEAN, maps.MODE_STD):
            self.mode_combo.addItem(maps.MODE_LABELS[k], k)
        self.z_combo = QtWidgets.QComboBox(); self.z_combo.setMinimumWidth(130)
        self.bins = QtWidgets.QSpinBox(); self.bins.setRange(5, 200); self.bins.setValue(40)
        for w, lbl in ((self.view_combo, "表示:"), (self.a_combo, "コホートA:"),
                       (self.b_combo, "コホートB:"), (self.x_combo, "X:"),
                       (self.y_combo, "Y:"), (self.mode_combo, "色(Z):"),
                       (self.z_combo, "Z信号:"), (self.bins, "分割:")):
            ctl.addWidget(QtWidgets.QLabel(lbl)); ctl.addWidget(w)
        ctl.addStretch(1)
        lay.addLayout(ctl)

        self.cond = ConditionBar()
        lay.addWidget(self.cond)
        self.msg = QtWidgets.QLabel(); self.msg.setObjectName("dim")
        lay.addWidget(self.msg)
        self.map = HeatMap2D()
        lay.addWidget(self.map, 1)

        self.view_combo.currentIndexChanged.connect(self._on_view)
        for c in (self.a_combo, self.b_combo, self.x_combo, self.y_combo, self.z_combo):
            c.currentIndexChanged.connect(self._redraw)
        self.mode_combo.currentIndexChanged.connect(self._on_mode)
        self.bins.valueChanged.connect(self._redraw)
        self.cond.changed.connect(self._redraw)
        self.state.tagsChanged.connect(self.reload)
        self.state.datasetsChanged.connect(self.reload)
        self.state.rolesChanged.connect(lambda _i: self.reload())
        self.reload()

    def reload(self):
        tags = tags_mod.list_tags()
        for combo in (self.a_combo, self.b_combo):
            cur = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for t in tags:
                label = f"[{t.category}] {t.name}" if t.category else t.name
                combo.addItem(f"{label} ({t.dataset_count})", t.id)
            if cur is not None:
                i = combo.findData(cur)
                if i >= 0:
                    combo.setCurrentIndex(i)
            combo.blockSignals(False)
        if self.b_combo.count() > 1 and self.b_combo.currentData() == self.a_combo.currentData():
            self.b_combo.setCurrentIndex(1)
        self._refresh_signals()
        self._on_view()

    def _involved_ids(self):
        ids = set(tags_mod.dataset_ids_for_tag(self.a_combo.currentData() or -1))
        if self.view_combo.currentText() == _MODE_DIFF:
            ids |= set(tags_mod.dataset_ids_for_tag(self.b_combo.currentData() or -1))
        return list(ids)

    def _refresh_signals(self):
        cols = set()
        for did in self._involved_ids():
            cols.update(ds_mod.numeric_columns(did))
            cols.update(derived_mod.numeric_names(did))
            g = ds_mod.gear_column(did)
            if g:
                cols.add(g)
        cols = sorted(cols)
        self.cond.set_signals(cols)
        for combo, default in ((self.x_combo, "engine_speed_rpm"),
                               (self.y_combo, "vehicle_speed_kph"),
                               (self.z_combo, None)):
            cur = combo.currentText()
            combo.blockSignals(True)
            combo.clear(); combo.addItems(cols)
            pick = cur if cur in cols else (default if default in cols else (cols[0] if cols else ""))
            if pick:
                combo.setCurrentText(pick)
            combo.blockSignals(False)

    def _on_view(self):
        self.b_combo.setEnabled(self.view_combo.currentText() == _MODE_DIFF)
        self._refresh_signals()
        self._redraw()

    def _on_mode(self):
        self.z_combo.setEnabled(self.mode_combo.currentData() in (maps.MODE_MEAN, maps.MODE_STD))
        self._redraw()

    def _redraw(self):
        xcol, ycol = self.x_combo.currentText(), self.y_combo.currentText()
        if not xcol or not ycol or self.a_combo.currentData() is None:
            return
        mode = self.mode_combo.currentData()
        zcol = self.z_combo.currentText() if mode in (maps.MODE_MEAN, maps.MODE_STD) else None
        cond = self.cond.predicates()
        bins = self.bins.value()
        ids_a = tags_mod.dataset_ids_for_tag(self.a_combo.currentData())
        if self.view_combo.currentText() == _MODE_DIFF:
            ids_b = tags_mod.dataset_ids_for_tag(self.b_combo.currentData())
            res = maps.compute_diff_map(ids_a, ids_b, xcol, ycol, mode, zcol, bins, cond)
            note = f"A={self.a_combo.currentText()}  −  B={self.b_combo.currentText()}"
        else:
            res = maps.compute_cohort_map(ids_a, xcol, ycol, mode, zcol, bins, cond)
            note = f"{self.a_combo.currentText()}  ({len(ids_a)} データ)"
        self.map.set_map(res, xcol, ycol)
        from vdas.analysis.conditions import label as clabel
        cnote = f"　条件: {clabel(cond)}" if cond else ""
        self.msg.setText(f"{note}　有効サンプル: {res.n_used:,}{cnote}")
