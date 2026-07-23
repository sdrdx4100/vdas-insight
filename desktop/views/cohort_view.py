"""Cohort comparison view.

Compare tagged cohorts on rate-normalized metrics. Cohorts can be defined two
ways, and both can be narrowed by an AND-filter so that different N compares
fairly:

  * **タグごと** — each selected tag becomes a cohort.
  * **カテゴリで分割** — a tag category (e.g. メーカー) is split into one cohort
    per tag in it.

The **絞り込み (AND)** selection restricts every cohort to datasets that carry
*all* the chosen filter tags (e.g. compare makers *within* highway driving).
"""
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
from ..widgets.charts import BarChart
from ..widgets.common import section_label
from ..widgets.condition_bar import ConditionBar

_MODE_TAGS = "タグごと"
_MODE_CATEGORY = "カテゴリで分割"


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


class CohortView(QtWidgets.QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # --- controls -------------------------------------------------------
        ctl = QtWidgets.QHBoxLayout()

        mode_box = QtWidgets.QVBoxLayout()
        mode_box.addWidget(QtWidgets.QLabel("比較対象の作り方"))
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems([_MODE_TAGS, _MODE_CATEGORY])
        mode_box.addWidget(self.mode_combo)
        self.cat_combo = QtWidgets.QComboBox()
        self.cat_combo.setMinimumWidth(140)
        mode_box.addWidget(self.cat_combo)
        mode_box.addStretch(1)
        ctl.addLayout(mode_box)

        self.cohort_widget = QtWidgets.QWidget()
        coh_box = QtWidgets.QVBoxLayout(self.cohort_widget)
        coh_box.setContentsMargins(0, 0, 0, 0)
        self.coh_label = QtWidgets.QLabel("コホートにするタグ")
        coh_box.addWidget(self.coh_label)
        self.cohort_list = QtWidgets.QListWidget()
        self.cohort_list.setFixedSize(210, 92)
        coh_box.addWidget(self.cohort_list)
        coh_box.addLayout(self._check_buttons(self.cohort_list))
        ctl.addWidget(self.cohort_widget)

        flt_box = QtWidgets.QVBoxLayout()
        flt_box.addWidget(QtWidgets.QLabel("タグ絞り込み (AND)"))
        self.filter_list = QtWidgets.QListWidget()
        self.filter_list.setFixedSize(210, 92)
        flt_box.addWidget(self.filter_list)
        flt_box.addLayout(self._check_buttons(self.filter_list))
        ctl.addLayout(flt_box)

        form = QtWidgets.QFormLayout()
        self.metric_search = QtWidgets.QLineEdit()
        self.metric_search.setPlaceholderText("指標名・単位で検索")
        self.metric_search.setClearButtonEnabled(True)
        self.metric_combo = QtWidgets.QComboBox()
        self.metric_combo.setMinimumWidth(290)
        self.base_combo = QtWidgets.QComboBox()
        self.base_combo.setMinimumWidth(180)
        form.addRow("指標検索:", self.metric_search)
        form.addRow("表示指標:", self.metric_combo)
        form.addRow("相対基準:", self.base_combo)
        ctl.addLayout(form)
        ctl.addStretch(1)

        btns = QtWidgets.QVBoxLayout()
        self.btn_refresh = QtWidgets.QPushButton("再計算")
        self.btn_refresh.setToolTip("現在の設定でデータを読み直して再計算します")
        self.btn_refresh.setObjectName("primary")
        self.btn_export = QtWidgets.QPushButton("CSV 出力")
        btns.addWidget(self.btn_refresh)
        btns.addWidget(self.btn_export)
        btns.addStretch(1)
        ctl.addLayout(btns)
        lay.addLayout(ctl)

        self.cond = ConditionBar()
        lay.addWidget(self.cond)

        self.msg = QtWidgets.QLabel()
        self.msg.setObjectName("dim")
        lay.addWidget(self.msg)

        # --- charts ---------------------------------------------------------
        charts = QtWidgets.QSplitter()
        lw = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(lw)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(section_label("プール値（○=データ単位のばらつき）"))
        self.bar = BarChart("value")
        lv.addWidget(self.bar)
        rw = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(rw)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(section_label("相対指数（基準 = 100）"))
        self.idx = BarChart("index")
        rv.addWidget(self.idx)
        charts.addWidget(lw)
        charts.addWidget(rw)
        lay.addWidget(charts, 1)

        # --- table ----------------------------------------------------------
        lay.addWidget(section_label("選択中の指標"))
        self.table = QtWidgets.QTableWidget(0, 0)
        self.table.verticalHeader().setVisible(False)
        self.table.setMaximumHeight(190)
        self.table.setAlternatingRowColors(True)
        lay.addWidget(self.table)

        self.btn_refresh.clicked.connect(self.rebuild)
        self.btn_export.clicked.connect(self._export)
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        self.cat_combo.currentIndexChanged.connect(self.rebuild)
        self.cohort_list.itemChanged.connect(self.rebuild)
        self.filter_list.itemChanged.connect(self.rebuild)
        self.metric_search.textChanged.connect(self._filter_metrics)
        self.metric_combo.currentIndexChanged.connect(self._draw)
        self.base_combo.currentIndexChanged.connect(self._draw)
        self.cond.changed.connect(self.rebuild)
        self.state.tagsChanged.connect(self.reload_tags)
        self.state.datasetsChanged.connect(self.reload_tags)
        self._df = None
        self._cohorts = []
        self._defs: dict[str, MetricDef] = {}
        self._metric_defs: list[MetricDef] = []
        self._first_load = True
        self.reload_tags()
        self._mode_changed()

    # ---------------------------------------------------------------- widgets
    def _check_buttons(self, widget: QtWidgets.QListWidget) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(4)
        btn_all = QtWidgets.QPushButton("全選択")
        btn_clear = QtWidgets.QPushButton("全解除")
        for button in (btn_all, btn_clear):
            button.setFixedHeight(24)
            row.addWidget(button)
        row.addStretch(1)
        btn_all.clicked.connect(lambda: self._set_checked(widget, True))
        btn_clear.clicked.connect(lambda: self._set_checked(widget, False))
        return row

    def _set_checked(self, widget: QtWidgets.QListWidget, checked: bool):
        widget.blockSignals(True)
        state = QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked
        for i in range(widget.count()):
            widget.item(i).setCheckState(state)
        widget.blockSignals(False)
        self.rebuild()

    # ---------------------------------------------------------------- tags
    def _fill_checklist(self, widget, keep: set[int]):
        widget.blockSignals(True)
        widget.clear()
        for t in tags_mod.list_tags():
            label = f"[{t.category}] {t.name} ({t.dataset_count})" if t.category \
                else f"{t.name} ({t.dataset_count})"
            it = QtWidgets.QListWidgetItem(label)
            it.setData(QtCore.Qt.UserRole, t.id)
            it.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
            it.setCheckState(QtCore.Qt.Checked if t.id in keep else QtCore.Qt.Unchecked)
            widget.addItem(it)
        widget.blockSignals(False)

    def reload_tags(self):
        # First time, pre-check all tags as cohorts so the view shows something.
        if getattr(self, "_first_load", False):
            cohort_keep = {t.id for t in tags_mod.list_tags()}
            self._first_load = False
        else:
            cohort_keep = set(self._checked(self.cohort_list))
        self._fill_checklist(self.cohort_list, cohort_keep)
        self._fill_checklist(self.filter_list, set(self._checked(self.filter_list)))
        cur = self.cat_combo.currentText()
        self.cat_combo.blockSignals(True)
        self.cat_combo.clear()
        self.cat_combo.addItems(tags_mod.list_categories())
        if cur:
            self.cat_combo.setCurrentText(cur)
        self.cat_combo.blockSignals(False)
        self.rebuild()

    def _checked(self, widget) -> list[int]:
        return [widget.item(i).data(QtCore.Qt.UserRole)
                for i in range(widget.count())
                if widget.item(i).checkState() == QtCore.Qt.Checked]

    def _mode_changed(self):
        cat_mode = self.mode_combo.currentText() == _MODE_CATEGORY
        self.cat_combo.setVisible(cat_mode)
        self.cohort_widget.setVisible(not cat_mode)
        self.rebuild()

    # ------------------------------------------------------------- metrics
    def _filter_metrics(self):
        if not self._metric_defs:
            return
        cur_key = self.metric_combo.currentData()
        query = self.metric_search.text().strip().casefold()
        visible = []
        for metric in self._metric_defs:
            haystack = " ".join((
                metric.key, metric.label, metric.unit, _metric_category(metric)
            )).casefold()
            if not query or query in haystack:
                visible.append(metric)

        self.metric_combo.blockSignals(True)
        self.metric_combo.clear()
        for metric in visible:
            self.metric_combo.addItem(_metric_text(metric), metric.key)
        index = self.metric_combo.findData(cur_key)
        self.metric_combo.setCurrentIndex(index if index >= 0 else (0 if visible else -1))
        self.metric_combo.blockSignals(False)
        self._draw()

    # ------------------------------------------------------------- compute
    def _build_defs(self) -> list[CohortDef]:
        filter_ids = self._checked(self.filter_list)
        defs: list[CohortDef] = []
        if self.mode_combo.currentText() == _MODE_CATEGORY:
            cat = self.cat_combo.currentText()
            src_tags = tags_mod.tags_in_category(cat) if cat else []
        else:
            checked = set(self._checked(self.cohort_list))
            src_tags = [t for t in tags_mod.list_tags() if t.id in checked]
        for t in src_tags:
            ids = tags_mod.dataset_ids_matching_all(filter_ids + [t.id])
            defs.append(CohortDef(t.name, ids, t.color))
        return defs

    def rebuild(self):
        defs = self._build_defs()
        if not defs:
            self.msg.setText("比較するコホートを選択してください"
                             "（『タグごと』ならタグ、『カテゴリで分割』ならカテゴリ）。")
            self.bar.plot.clear()
            self.idx.plot.clear()
            self.table.setRowCount(0)
            self._df = None
            return

        flag_cols, num_cols = set(), set()
        for cohort_def in defs:
            for did in cohort_def.dataset_ids:
                flag_cols.update(ds_mod.flag_columns(did))
                flag_cols.update(derived_mod.flag_names(did))     # event flags
                num_cols.update(ds_mod.numeric_columns(did))
                num_cols.update(derived_mod.numeric_names(did))   # accel/jerk…
        metric_defs = list(CORE_METRICS)
        for flag_col in sorted(flag_cols):
            metric_defs += flag_metric_defs(flag_col)
        for num_col in sorted(num_cols):
            metric_defs += numeric_metric_defs(num_col)
        self._metric_defs = metric_defs
        self._defs = {metric.key: metric for metric in metric_defs}

        # Feed available signals to the condition builder.
        self.cond.set_signals(sorted(num_cols))
        predicates = self.cond.predicates()

        cur_key = self.metric_combo.currentData() or "shifts_per_hour"
        # Suppress redraws against the previous result while rebuilding controls.
        self._df = None
        self.metric_combo.blockSignals(True)
        self.metric_combo.clear()
        self.metric_combo.blockSignals(False)
        self._filter_metrics()
        if self.metric_combo.findData(cur_key) >= 0:
            self.metric_combo.setCurrentIndex(self.metric_combo.findData(cur_key))

        self._df, self._cohorts = groups.compare_defs(
            defs, [metric.key for metric in metric_defs], condition=predicates)
        self.base_combo.blockSignals(True)
        cur_base = self.base_combo.currentText()
        self.base_combo.clear()
        self.base_combo.addItems(self._df["tag"].tolist())
        if cur_base in self._df["tag"].tolist():
            self.base_combo.setCurrentText(cur_base)
        self.base_combo.blockSignals(False)

        filt = self._checked(self.filter_list)
        fnote = ""
        if filt:
            names = [t.name for t in tags_mod.list_tags() if t.id in filt]
            fnote = f"　タグ絞り込み: {' AND '.join(names)}"
        from vdas.analysis.conditions import label as cond_label
        cnote = f"　集計条件: {cond_label(predicates)}" if predicates else ""
        self.msg.setText("※ N や総時間が異なるため、レート/割合で公平に比較します。"
                         + fnote + cnote)
        self._draw()

    def _draw(self):
        if self._df is None or self._df.empty:
            return
        key = self.metric_combo.currentData()
        if not key or key not in self._defs:
            self.bar.plot.clear()
            self.idx.plot.clear()
            self.table.setRowCount(0)
            return
        metric_def = self._defs[key]
        df = self._df
        scale = 100.0 if metric_def.is_percent else 1.0
        vals = (df[key].astype(float) * scale).tolist()
        colors = [c.color or theme.series_color(i) for i, c in enumerate(self._cohorts)]
        spreads = None
        if metric_def.kind not in ("duration",):
            spreads = []
            for cohort in self._cohorts:
                spread = cohort.spread(key)
                spreads.append(spread * scale if metric_def.is_percent else spread)
        self.bar.plot.setLabel(
            "left", f"{metric_def.label} ({metric_def.unit})", color=theme.INK_DIM)
        self.bar.set_data(df["tag"].tolist(), vals, colors=colors,
                          value_fmt="{:.2f}", scatter=spreads)

        base = self.base_combo.currentText() or None
        idx = groups.relative_index(df, key, base_tag=base)
        self.idx.set_data(idx.index.tolist(), idx.values.tolist(), colors=colors,
                          value_fmt="{:.0f}")
        self._fill_table(key, idx)

    def _fill_table(self, key: str, relative_index):
        df = self._df
        metric_def = self._defs[key]
        metric_header = metric_def.label
        if metric_def.unit:
            metric_header += f" [{metric_def.unit}]"
        headers = ["コホート", "N", "時間 [h]", metric_header, "相対指数"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(df))
        index_values = relative_index.to_dict()
        for row_index, (_, row) in enumerate(df.iterrows()):
            label = str(row["tag"])
            value = row.get(key, float("nan"))
            if metric_def.is_percent and value == value:
                value_text = f"{value * 100:.2f}%"
            else:
                value_text = "—" if value != value else f"{value:,.3f}"
            relative = index_values.get(label, float("nan"))
            relative_text = "—" if relative != relative else f"{relative:,.0f}"

            values = [
                label,
                str(int(row["n_datasets"])),
                f"{row['duration_h']:.3f}",
                value_text,
                relative_text,
            ]
            for column, text in enumerate(values):
                self.table.setItem(
                    row_index, column, QtWidgets.QTableWidgetItem(text))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _export(self):
        if self._df is None or self._df.empty:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "CSV に保存", "cohort_comparison.csv", "CSV (*.csv)")
        if path:
            self._df.to_csv(path, index=False, encoding="utf-8-sig")
            QtWidgets.QMessageBox.information(self, "保存", f"保存しました:\n{path}")
