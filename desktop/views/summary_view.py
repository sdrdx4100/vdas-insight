"""Summary sheet — small-multiples matrix of cohort metrics (EX-Summary style)."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from vdas import datasets as ds_mod
from vdas import derived as derived_mod
from vdas import tags as tags_mod
from vdas.analysis import groups
from vdas.analysis.groups import (CORE_METRICS, CohortDef, flag_metric_defs,
                                  numeric_metric_defs)
from .. import theme
from ..state import AppState
from ..widgets.condition_bar import ConditionBar
from ..widgets.summary_grid import MiniBarGrid


class SummaryView(QtWidgets.QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        ctl = QtWidgets.QHBoxLayout()
        cbox = QtWidgets.QVBoxLayout()
        cbox.addWidget(QtWidgets.QLabel("コホート（タグ）"))
        self.tag_list = QtWidgets.QListWidget(); self.tag_list.setFixedSize(190, 96)
        cbox.addWidget(self.tag_list)
        ctl.addLayout(cbox)

        mbox = QtWidgets.QVBoxLayout()
        mbox.addWidget(QtWidgets.QLabel("表示する指標"))
        self.metric_list = QtWidgets.QListWidget(); self.metric_list.setFixedSize(320, 96)
        mbox.addWidget(self.metric_list)
        ctl.addLayout(mbox)

        opt = QtWidgets.QFormLayout()
        self.cols_spin = QtWidgets.QSpinBox(); self.cols_spin.setRange(1, 6); self.cols_spin.setValue(3)
        opt.addRow("列数:", self.cols_spin)
        self.btn_refresh = QtWidgets.QPushButton("更新"); self.btn_refresh.setObjectName("primary")
        opt.addRow(self.btn_refresh)
        ctl.addLayout(opt)
        ctl.addStretch(1)
        lay.addLayout(ctl)

        self.cond = ConditionBar()
        lay.addWidget(self.cond)

        self.msg = QtWidgets.QLabel(); self.msg.setObjectName("dim")
        lay.addWidget(self.msg)

        self.scroll = QtWidgets.QScrollArea(); self.scroll.setWidgetResizable(True)
        self.grid = MiniBarGrid()
        self.scroll.setWidget(self.grid)
        lay.addWidget(self.scroll, 1)

        self.btn_refresh.clicked.connect(self.rebuild)
        self.cols_spin.valueChanged.connect(self._draw)
        self.tag_list.itemChanged.connect(self.rebuild)
        self.metric_list.itemChanged.connect(self._draw)
        self.cond.changed.connect(self.rebuild)
        self.state.tagsChanged.connect(self.reload_tags)
        self.state.datasetsChanged.connect(self.reload_tags)
        self._first = True
        self._df = None
        self._cohorts = []
        self._defs = {}
        self.reload_tags()

    def reload_tags(self):
        keep = set(self._checked(self.tag_list)) if not self._first else \
            {t.id for t in tags_mod.list_tags()}
        self._first = False
        self.tag_list.blockSignals(True)
        self.tag_list.clear()
        for t in tags_mod.list_tags():
            label = f"[{t.category}] {t.name}" if t.category else t.name
            it = QtWidgets.QListWidgetItem(f"{label} ({t.dataset_count})")
            it.setData(QtCore.Qt.UserRole, t.id)
            it.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
            it.setCheckState(QtCore.Qt.Checked if t.id in keep else QtCore.Qt.Unchecked)
            self.tag_list.addItem(it)
        self.tag_list.blockSignals(False)
        self.rebuild()

    def _checked(self, widget):
        return [widget.item(i).data(QtCore.Qt.UserRole) for i in range(widget.count())
                if widget.item(i).checkState() == QtCore.Qt.Checked]

    def rebuild(self):
        tag_ids = self._checked(self.tag_list)
        if not tag_ids:
            self.msg.setText("コホート（タグ）を選択してください。")
            self.grid.clear(); return
        defs = []
        for tid in tag_ids:
            t = tags_mod.get_tag(tid)
            defs.append(CohortDef(t.name if t else str(tid),
                                  tags_mod.dataset_ids_for_tag(tid),
                                  t.color if t else None))
        # available metrics
        flag_cols, num_cols = set(), set()
        for d in defs:
            for did in d.dataset_ids:
                flag_cols.update(ds_mod.flag_columns(did)); flag_cols.update(derived_mod.flag_names(did))
                num_cols.update(ds_mod.numeric_columns(did)); num_cols.update(derived_mod.numeric_names(did))
        metric_defs = list(CORE_METRICS)
        for fc in sorted(flag_cols):
            metric_defs += flag_metric_defs(fc)
        for nc in sorted(num_cols):
            metric_defs += numeric_metric_defs(nc)
        self._defs = {m.key: m for m in metric_defs}

        self.cond.set_signals(sorted(num_cols))
        predicates = self.cond.predicates()

        prev = set(self._checked(self.metric_list))
        if not prev:
            prev = _default_metrics(metric_defs)
        self.metric_list.blockSignals(True)
        self.metric_list.clear()
        for m in metric_defs:
            it = QtWidgets.QListWidgetItem(f"{m.label} [{m.unit}]" if m.unit else m.label)
            it.setData(QtCore.Qt.UserRole, m.key)
            it.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
            it.setCheckState(QtCore.Qt.Checked if m.key in prev else QtCore.Qt.Unchecked)
            self.metric_list.addItem(it)
        self.metric_list.blockSignals(False)

        self._df, self._cohorts = groups.compare_defs(
            defs, [m.key for m in metric_defs], condition=predicates)
        from vdas.analysis.conditions import label as cond_label
        cnote = f"　集計条件: {cond_label(predicates)}" if predicates else ""
        self.msg.setText(f"{len(defs)} コホート × 指標を一覧（各パネル: コホート別の値）" + cnote)
        self._draw()

    def _draw(self):
        if self._df is None or self._df.empty:
            return
        keys = [k for k in self._checked(self.metric_list) if k in self._defs]
        if not keys:
            self.grid.clear(); return
        colors = [c.color or theme.series_color(i) for i, c in enumerate(self._cohorts)]
        labels = self._df["tag"].tolist()
        panels = []
        for k in keys:
            mdef = self._defs[k]
            panels.append({"title": f"{mdef.label}" + (f" [{mdef.unit}]" if mdef.unit else ""),
                           "values": self._df[k].tolist(),
                           "is_percent": mdef.is_percent})
        self.grid.set_panels(labels, colors, panels, ncols=self.cols_spin.value())


def _default_metrics(metric_defs) -> set:
    """A sensible starting subset: rate/ratio metrics, capped."""
    keys = [m.key for m in metric_defs if m.kind in ("rate", "ratio")]
    return set(keys[:9])
