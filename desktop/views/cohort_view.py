"""Cohort comparison view — compare tags on rate-normalized metrics."""
from __future__ import annotations

import numpy as np
from PySide6 import QtCore, QtWidgets

from vdas import datasets as ds_mod
from vdas import tags as tags_mod
from vdas.analysis import groups
from vdas.analysis.groups import CORE_METRICS, flag_metric_defs
from .. import theme
from ..state import AppState
from ..widgets.charts import BarChart
from ..widgets.common import section_label


class CohortView(QtWidgets.QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # --- controls -------------------------------------------------------
        ctl = QtWidgets.QHBoxLayout()
        ctl.addWidget(QtWidgets.QLabel("コホート:"))
        self.tag_list = QtWidgets.QListWidget()
        self.tag_list.setFixedHeight(78)
        self.tag_list.setFixedWidth(240)
        self.tag_list.setFlow(QtWidgets.QListView.TopToBottom)
        ctl.addWidget(self.tag_list)

        form = QtWidgets.QFormLayout()
        self.metric_combo = QtWidgets.QComboBox(); self.metric_combo.setMinimumWidth(240)
        self.base_combo = QtWidgets.QComboBox(); self.base_combo.setMinimumWidth(160)
        form.addRow("指標:", self.metric_combo)
        form.addRow("相対基準:", self.base_combo)
        ctl.addLayout(form)
        ctl.addStretch(1)

        btns = QtWidgets.QVBoxLayout()
        self.btn_refresh = QtWidgets.QPushButton("更新")
        self.btn_refresh.setObjectName("primary")
        self.btn_export = QtWidgets.QPushButton("CSV 出力")
        btns.addWidget(self.btn_refresh); btns.addWidget(self.btn_export)
        ctl.addLayout(btns)
        lay.addLayout(ctl)

        self.msg = QtWidgets.QLabel(); self.msg.setObjectName("dim")
        lay.addWidget(self.msg)

        # --- charts ---------------------------------------------------------
        charts = QtWidgets.QSplitter()
        lw = QtWidgets.QWidget(); lv = QtWidgets.QVBoxLayout(lw); lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(section_label("プール値（○=データ単位のばらつき）"))
        self.bar = BarChart("value")
        lv.addWidget(self.bar)
        rw = QtWidgets.QWidget(); rv = QtWidgets.QVBoxLayout(rw); rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(section_label("相対指数（基準 = 100）"))
        self.idx = BarChart("index")
        rv.addWidget(self.idx)
        charts.addWidget(lw); charts.addWidget(rw)
        lay.addWidget(charts, 1)

        # --- table ----------------------------------------------------------
        lay.addWidget(section_label("比較テーブル"))
        self.table = QtWidgets.QTableWidget(0, 0)
        self.table.verticalHeader().setVisible(False)
        self.table.setMaximumHeight(180)
        lay.addWidget(self.table)

        self.btn_refresh.clicked.connect(self.rebuild)
        self.btn_export.clicked.connect(self._export)
        self.tag_list.itemChanged.connect(self._on_change)
        self.metric_combo.currentIndexChanged.connect(self._draw)
        self.base_combo.currentIndexChanged.connect(self._draw)
        self.state.tagsChanged.connect(self.reload_tags)
        self.state.datasetsChanged.connect(self.reload_tags)
        self._df = None
        self._cohorts = []
        self.reload_tags()

    # ---------------------------------------------------------------- tags
    def reload_tags(self):
        checked = set(self._checked_tag_ids())
        self.tag_list.blockSignals(True)
        self.tag_list.clear()
        for t in tags_mod.list_tags():
            it = QtWidgets.QListWidgetItem(f"{t.name} ({t.dataset_count})")
            it.setData(QtCore.Qt.UserRole, t.id)
            it.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
            default_on = t.id in checked or (not checked)
            it.setCheckState(QtCore.Qt.Checked if default_on else QtCore.Qt.Unchecked)
            self.tag_list.addItem(it)
        self.tag_list.blockSignals(False)
        self.rebuild()

    def _checked_tag_ids(self):
        ids = []
        for i in range(self.tag_list.count()):
            it = self.tag_list.item(i)
            if it.checkState() == QtCore.Qt.Checked:
                ids.append(it.data(QtCore.Qt.UserRole))
        return ids

    def _on_change(self, *_):
        self.rebuild()

    # ------------------------------------------------------------- compute
    def rebuild(self):
        tag_ids = self._checked_tag_ids()
        if not tag_ids:
            self.msg.setText("比較するコホート（タグ）を選択してください。")
            self.bar.plot.clear(); self.idx.plot.clear()
            self.table.setRowCount(0)
            return
        # available metrics from flags present in selected cohorts
        flag_cols = set()
        for tid in tag_ids:
            for did in tags_mod.dataset_ids_for_tag(tid):
                flag_cols.update(ds_mod.flag_columns(did))
        defs = list(CORE_METRICS)
        for fc in sorted(flag_cols):
            defs += flag_metric_defs(fc)
        self._defs = {m.key: m for m in defs}

        cur_key = self.metric_combo.currentData() or "shifts_per_hour"
        self.metric_combo.blockSignals(True)
        self.metric_combo.clear()
        for m in defs:
            self.metric_combo.addItem(f"{m.label}  [{m.unit}]", m.key)
        i = self.metric_combo.findData(cur_key)
        self.metric_combo.setCurrentIndex(i if i >= 0 else 0)
        self.metric_combo.blockSignals(False)

        self._df, self._cohorts = groups.compare(tag_ids, [m.key for m in defs])
        self.base_combo.blockSignals(True)
        cur_base = self.base_combo.currentText()
        self.base_combo.clear()
        self.base_combo.addItems(self._df["tag"].tolist())
        if cur_base in self._df["tag"].tolist():
            self.base_combo.setCurrentText(cur_base)
        self.base_combo.blockSignals(False)

        self.msg.setText(
            "※ N（データ数）や総時間が異なるため、レート/割合で公平に比較します。")
        self._fill_table()
        self._draw()

    def _draw(self):
        if self._df is None or self._df.empty:
            return
        key = self.metric_combo.currentData()
        if not key or key not in self._defs:
            return
        mdef = self._defs[key]
        df = self._df
        scale = 100.0 if mdef.is_percent else 1.0
        vals = (df[key].astype(float) * scale).tolist()
        colors = [theme.series_color(i) for i in range(len(df))]
        spreads = None
        if mdef.kind not in ("duration",):
            spreads = []
            for c in self._cohorts:
                sp = c.spread(key)
                spreads.append(sp * scale if mdef.is_percent else sp)
        self.bar.plot.setLabel("left", f"{mdef.label} ({mdef.unit})", color=theme.INK_DIM)
        self.bar.set_data(df["tag"].tolist(), vals, colors=colors,
                          value_fmt="{:.2f}", scatter=spreads)

        # relative index
        base = self.base_combo.currentText() or None
        idx = groups.relative_index(df, key, base_tag=base)
        self.idx.set_data(idx.index.tolist(), idx.values.tolist(), colors=colors,
                          value_fmt="{:.0f}")

    def _fill_table(self):
        df = self._df
        keys = [m for m in self._defs]
        headers = ["tag", "N", "時間(h)"] + [self._defs[k].label for k in keys]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(df))
        for r, (_, row) in enumerate(df.iterrows()):
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(row["tag"])))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(int(row["n_datasets"]))))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(f"{row['duration_h']:.3f}"))
            for j, k in enumerate(keys):
                v = row.get(k, float("nan"))
                if self._defs[k].is_percent and v == v:
                    txt = f"{v*100:.2f}%"
                else:
                    txt = "—" if v != v else f"{v:,.3f}"
                self.table.setItem(r, 3 + j, QtWidgets.QTableWidgetItem(txt))
        self.table.resizeColumnsToContents()

    def _export(self):
        if self._df is None or self._df.empty:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "CSV に保存", "cohort_comparison.csv", "CSV (*.csv)")
        if path:
            self._df.to_csv(path, index=False, encoding="utf-8-sig")
            QtWidgets.QMessageBox.information(self, "保存", f"保存しました:\n{path}")
