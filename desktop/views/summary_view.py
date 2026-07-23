"""Summary sheet — small-multiples matrix of cohort metrics (EX-Summary style)."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from vdas import datasets as ds_mod
from vdas import derived as derived_mod
from vdas import tags as tags_mod
from vdas.analysis import groups
from vdas.analysis.groups import (CORE_METRICS, CohortDef, MetricDef,
                                   flag_metric_defs, numeric_metric_defs)
from .. import theme
from ..state import AppState
from ..widgets.condition_bar import ConditionBar
from ..widgets.summary_grid import MiniBarGrid


def _metric_category(metric: MetricDef) -> str:
    if metric.key.startswith("flag::"):
        return "フラグ"
    if metric.key.startswith("num::"):
        return "数値信号"
    if metric.key in {
        "shift_count", "shifts_per_hour", "shifts_per_km",
        "upshift_ratio", "downshift_ratio",
    }:
        return "ギア"
    return "基本"


def _metric_text(metric: MetricDef) -> str:
    unit = f" [{metric.unit}]" if metric.unit else ""
    return f"[{_metric_category(metric)}] {metric.label}{unit}"


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
        self.tag_list = QtWidgets.QListWidget()
        self.tag_list.setFixedSize(210, 112)
        cbox.addWidget(self.tag_list)
        tag_buttons = QtWidgets.QHBoxLayout()
        self.btn_tag_all = QtWidgets.QPushButton("全選択")
        self.btn_tag_clear = QtWidgets.QPushButton("全解除")
        for button in (self.btn_tag_all, self.btn_tag_clear):
            button.setFixedHeight(24)
            tag_buttons.addWidget(button)
        tag_buttons.addStretch(1)
        cbox.addLayout(tag_buttons)
        ctl.addLayout(cbox)

        mbox = QtWidgets.QVBoxLayout()
        mbox.addWidget(QtWidgets.QLabel("表示する指標"))
        self.metric_search = QtWidgets.QLineEdit()
        self.metric_search.setPlaceholderText("指標名・単位で検索")
        self.metric_search.setClearButtonEnabled(True)
        mbox.addWidget(self.metric_search)
        self.metric_list = QtWidgets.QListWidget()
        self.metric_list.setFixedSize(380, 86)
        mbox.addWidget(self.metric_list)
        metric_buttons = QtWidgets.QHBoxLayout()
        self.btn_metric_default = QtWidgets.QPushButton("標準")
        self.btn_metric_all = QtWidgets.QPushButton("全選択")
        self.btn_metric_clear = QtWidgets.QPushButton("全解除")
        for button in (
            self.btn_metric_default, self.btn_metric_all, self.btn_metric_clear
        ):
            button.setFixedHeight(24)
            metric_buttons.addWidget(button)
        metric_buttons.addStretch(1)
        mbox.addLayout(metric_buttons)
        ctl.addLayout(mbox)

        opt = QtWidgets.QFormLayout()
        self.cols_spin = QtWidgets.QSpinBox()
        self.cols_spin.setRange(1, 6)
        self.cols_spin.setValue(3)
        opt.addRow("列数:", self.cols_spin)
        self.btn_refresh = QtWidgets.QPushButton("再計算")
        self.btn_refresh.setToolTip("現在の設定でデータを読み直して再計算します")
        self.btn_refresh.setObjectName("primary")
        opt.addRow(self.btn_refresh)
        ctl.addLayout(opt)
        ctl.addStretch(1)
        lay.addLayout(ctl)

        self.cond = ConditionBar()
        lay.addWidget(self.cond)

        self.msg = QtWidgets.QLabel()
        self.msg.setObjectName("dim")
        lay.addWidget(self.msg)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.grid = MiniBarGrid()
        self.scroll.setWidget(self.grid)
        lay.addWidget(self.scroll, 1)

        self.btn_refresh.clicked.connect(self.rebuild)
        self.cols_spin.valueChanged.connect(self._draw)
        self.tag_list.itemChanged.connect(self.rebuild)
        self.metric_search.textChanged.connect(self._populate_metric_list)
        self.metric_list.itemChanged.connect(self._metric_item_changed)
        self.btn_tag_all.clicked.connect(lambda: self._set_tags_checked(True))
        self.btn_tag_clear.clicked.connect(lambda: self._set_tags_checked(False))
        self.btn_metric_default.clicked.connect(
            lambda: self._set_metric_selection("default"))
        self.btn_metric_all.clicked.connect(
            lambda: self._set_metric_selection("all"))
        self.btn_metric_clear.clicked.connect(
            lambda: self._set_metric_selection("none"))
        self.cond.changed.connect(self.rebuild)
        self.state.tagsChanged.connect(self.reload_tags)
        self.state.datasetsChanged.connect(self.reload_tags)

        self._first = True
        self._df = None
        self._cohorts = []
        self._defs: dict[str, MetricDef] = {}
        self._metric_defs: list[MetricDef] = []
        self._selected_metric_keys: set[str] = set()
        self._metrics_initialized = False
        self._condition_note = ""
        self.reload_tags()

    # ---------------------------------------------------------------- tags
    def _set_tags_checked(self, checked: bool):
        self.tag_list.blockSignals(True)
        state = QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked
        for i in range(self.tag_list.count()):
            self.tag_list.item(i).setCheckState(state)
        self.tag_list.blockSignals(False)
        self.rebuild()

    def reload_tags(self):
        keep = set(self._checked(self.tag_list)) if not self._first else \
            {t.id for t in tags_mod.list_tags()}
        self._first = False
        self.tag_list.blockSignals(True)
        self.tag_list.clear()
        for tag in tags_mod.list_tags():
            label = f"[{tag.category}] {tag.name}" if tag.category else tag.name
            item = QtWidgets.QListWidgetItem(f"{label} ({tag.dataset_count})")
            item.setData(QtCore.Qt.UserRole, tag.id)
            item.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
            item.setCheckState(
                QtCore.Qt.Checked if tag.id in keep else QtCore.Qt.Unchecked)
            self.tag_list.addItem(item)
        self.tag_list.blockSignals(False)
        self.rebuild()

    def _checked(self, widget):
        return [widget.item(i).data(QtCore.Qt.UserRole)
                for i in range(widget.count())
                if widget.item(i).checkState() == QtCore.Qt.Checked]

    # -------------------------------------------------------------- metrics
    def _populate_metric_list(self):
        query = self.metric_search.text().strip().casefold()
        self.metric_list.blockSignals(True)
        self.metric_list.clear()
        for metric in self._metric_defs:
            haystack = " ".join((
                metric.key, metric.label, metric.unit, _metric_category(metric)
            )).casefold()
            if query and query not in haystack:
                continue
            item = QtWidgets.QListWidgetItem(_metric_text(metric))
            item.setData(QtCore.Qt.UserRole, metric.key)
            item.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
            item.setCheckState(
                QtCore.Qt.Checked
                if metric.key in self._selected_metric_keys
                else QtCore.Qt.Unchecked
            )
            self.metric_list.addItem(item)
        self.metric_list.blockSignals(False)

    def _metric_item_changed(self, item: QtWidgets.QListWidgetItem):
        key = item.data(QtCore.Qt.UserRole)
        if item.checkState() == QtCore.Qt.Checked:
            self._selected_metric_keys.add(key)
        else:
            self._selected_metric_keys.discard(key)
        self._draw()

    def _set_metric_selection(self, mode: str):
        if mode == "all":
            self._selected_metric_keys = {
                metric.key for metric in self._metric_defs}
        elif mode == "default":
            self._selected_metric_keys = _default_metrics(self._metric_defs)
        else:
            self._selected_metric_keys.clear()
        self._populate_metric_list()
        self._draw()

    # ------------------------------------------------------------- compute
    def rebuild(self):
        tag_ids = self._checked(self.tag_list)
        if not tag_ids:
            self.msg.setText("コホート（タグ）を選択してください。")
            self.grid.clear()
            self._df = None
            return

        defs = []
        for tag_id in tag_ids:
            tag = tags_mod.get_tag(tag_id)
            defs.append(CohortDef(
                tag.name if tag else str(tag_id),
                tags_mod.dataset_ids_for_tag(tag_id),
                tag.color if tag else None,
            ))

        flag_cols, num_cols = set(), set()
        for cohort_def in defs:
            for did in cohort_def.dataset_ids:
                flag_cols.update(ds_mod.flag_columns(did))
                flag_cols.update(derived_mod.flag_names(did))
                num_cols.update(ds_mod.numeric_columns(did))
                num_cols.update(derived_mod.numeric_names(did))

        metric_defs = list(CORE_METRICS)
        for flag_col in sorted(flag_cols):
            metric_defs += flag_metric_defs(flag_col)
        for num_col in sorted(num_cols):
            metric_defs += numeric_metric_defs(num_col)
        self._metric_defs = metric_defs
        self._defs = {metric.key: metric for metric in metric_defs}

        available_keys = set(self._defs)
        if not self._metrics_initialized:
            self._selected_metric_keys = _default_metrics(metric_defs)
            self._metrics_initialized = True
        else:
            self._selected_metric_keys.intersection_update(available_keys)
        self._populate_metric_list()

        self.cond.set_signals(sorted(num_cols))
        predicates = self.cond.predicates()

        self._df, self._cohorts = groups.compare_defs(
            defs, [metric.key for metric in metric_defs], condition=predicates)
        from vdas.analysis.conditions import label as cond_label
        self._condition_note = (
            f"　集計条件: {cond_label(predicates)}" if predicates else "")
        self._draw()

    def _draw(self):
        if self._df is None or self._df.empty:
            return
        keys = [
            metric.key for metric in self._metric_defs
            if metric.key in self._selected_metric_keys
        ]
        if not keys:
            self.grid.clear()
            self.msg.setText("表示する指標を選択してください。")
            return
        self.msg.setText(
            f"{len(self._cohorts)} コホート × {len(keys)} 指標を表示"
            + self._condition_note
        )
        colors = [
            cohort.color or theme.series_color(i)
            for i, cohort in enumerate(self._cohorts)
        ]
        labels = self._df["tag"].tolist()
        panels = []
        for key in keys:
            metric_def = self._defs[key]
            panels.append({
                "title": metric_def.label
                         + (f" [{metric_def.unit}]" if metric_def.unit else ""),
                "values": self._df[key].tolist(),
                "is_percent": metric_def.is_percent,
            })
        self.grid.set_panels(
            labels, colors, panels, ncols=self.cols_spin.value())


def _default_metrics(metric_defs) -> set:
    """A sensible starting subset: rate/ratio metrics, capped."""
    keys = [metric.key for metric in metric_defs
            if metric.kind in ("rate", "ratio")]
    return set(keys[:9])
