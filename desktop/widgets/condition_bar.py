"""Condition builder: compose AND predicates for gated cohort aggregation."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from vdas import presets as presets_mod
from vdas.analysis.conditions import OPS, Predicate


class ConditionBar(QtWidgets.QWidget):
    changed = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self._signals: list[str] = []
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        summary = QtWidgets.QHBoxLayout()
        self.enable = QtWidgets.QCheckBox("集計条件 (AND)")
        self.enable.setToolTip("条件を満たすサンプルだけで集計します（例: 車速 ≤ 70）")
        summary.addWidget(self.enable)
        self.summary_label = QtWidgets.QLabel("条件なし")
        self.summary_label.setObjectName("dim")
        self.summary_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        summary.addWidget(self.summary_label, 1)
        self.btn_toggle = QtWidgets.QToolButton()
        self.btn_toggle.setText("編集")
        self.btn_toggle.setCheckable(True)
        self.btn_toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.btn_toggle.setArrowType(QtCore.Qt.RightArrow)
        summary.addWidget(self.btn_toggle)
        lay.addLayout(summary)

        self.details = QtWidgets.QWidget()
        details_lay = QtWidgets.QVBoxLayout(self.details)
        details_lay.setContentsMargins(20, 2, 0, 0)
        details_lay.setSpacing(3)

        head = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton("＋条件")
        self.btn_add.setFixedWidth(64)
        head.addWidget(self.btn_add)
        head.addSpacing(12)
        head.addWidget(QtWidgets.QLabel("プリセット:"))
        self.preset_combo = QtWidgets.QComboBox()
        self.preset_combo.setMinimumWidth(150)
        head.addWidget(self.preset_combo)
        self.btn_save = QtWidgets.QPushButton("保存")
        self.btn_save.setFixedWidth(52)
        self.btn_del = QtWidgets.QPushButton("削除")
        self.btn_del.setFixedWidth(52)
        head.addWidget(self.btn_save)
        head.addWidget(self.btn_del)
        head.addStretch(1)
        details_lay.addLayout(head)

        self.rows_box = QtWidgets.QVBoxLayout()
        self.rows_box.setSpacing(3)
        details_lay.addLayout(self.rows_box)
        lay.addWidget(self.details)

        self._rows: list[dict] = []
        self.details.setVisible(False)

        self.enable.toggled.connect(self._on_enable)
        self.btn_toggle.toggled.connect(self._toggle_details)
        self.btn_add.clicked.connect(lambda: (self._add_row(), self._emit()))
        self.preset_combo.activated.connect(self._load_preset)
        self.btn_save.clicked.connect(self._save_preset)
        self.btn_del.clicked.connect(self._delete_preset)
        self._reload_presets()
        self._on_enable(False)

    def _toggle_details(self, expanded: bool):
        self.details.setVisible(expanded)
        self.btn_toggle.setText("閉じる" if expanded else "編集")
        self.btn_toggle.setArrowType(
            QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)

    def set_signals(self, cols: list[str]):
        self._signals = list(cols)
        for row in self._rows:
            cur = row["sig"].currentText()
            row["sig"].blockSignals(True)
            row["sig"].clear()
            row["sig"].addItems(self._signals)
            if cur in self._signals:
                row["sig"].setCurrentText(cur)
            row["sig"].blockSignals(False)
        self._update_summary()

    def _on_enable(self, on: bool):
        self.btn_add.setEnabled(on)
        self.preset_combo.setEnabled(on)
        self.btn_save.setEnabled(on)
        self.btn_del.setEnabled(on)
        for row in self._rows:
            row["w"].setEnabled(on)
        if on and not self._rows:
            self._add_row()
            self.btn_toggle.setChecked(True)
        self._emit()

    def _add_row(self, signal: str | None = None):
        w = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        sig = QtWidgets.QComboBox()
        sig.setMinimumWidth(150)
        sig.addItems(self._signals)
        if signal and signal in self._signals:
            sig.setCurrentText(signal)
        op = QtWidgets.QComboBox()
        for k, lbl in OPS.items():
            op.addItem(lbl, k)
        val = QtWidgets.QDoubleSpinBox()
        val.setRange(-1e9, 1e9)
        val.setDecimals(2)
        val2 = QtWidgets.QDoubleSpinBox()
        val2.setRange(-1e9, 1e9)
        val2.setDecimals(2)
        val2.setVisible(False)
        rm = QtWidgets.QPushButton("✕")
        rm.setFixedWidth(26)
        for x in (sig, op, val, val2):
            h.addWidget(x)
        h.addWidget(rm)
        h.addStretch(1)
        self.rows_box.addWidget(w)
        row = {"w": w, "sig": sig, "op": op, "val": val, "val2": val2}
        self._rows.append(row)

        def on_op():
            row["val2"].setVisible(op.currentData() == "between")
            self._emit()

        op.currentIndexChanged.connect(on_op)
        for x in (sig, val, val2):
            (x.valueChanged if isinstance(x, QtWidgets.QDoubleSpinBox)
             else x.currentIndexChanged).connect(self._emit)
        rm.clicked.connect(lambda: self._remove(row))
        return row

    def _remove(self, row):
        row["w"].setParent(None)
        self._rows.remove(row)
        self._emit()

    def _emit(self):
        self._update_summary()
        self.changed.emit()

    def _update_summary(self):
        if not self.enable.isChecked():
            self.summary_label.setText("条件なし")
            return
        preds = self._collect(force=True)
        if not preds:
            self.summary_label.setText("条件が未設定")
            return
        labels = []
        for p in preds:
            op_label = OPS.get(p.op, p.op)
            if p.op == "between":
                labels.append(f"{p.signal} {op_label} {p.value:g}〜{p.value2:g}")
            else:
                labels.append(f"{p.signal} {op_label} {p.value:g}")
        text = " AND ".join(labels)
        self.summary_label.setText(text if len(text) <= 100 else text[:97] + "…")
        self.summary_label.setToolTip(text)

    def set_predicates(self, preds: list[Predicate]):
        for row in list(self._rows):
            row["w"].setParent(None)
        self._rows.clear()
        self.enable.blockSignals(True)
        self.enable.setChecked(bool(preds))
        self.enable.blockSignals(False)
        self.btn_add.setEnabled(bool(preds))
        for p in preds:
            row = self._add_row(p.signal)
            i = row["op"].findData(p.op)
            if i >= 0:
                row["op"].setCurrentIndex(i)
            row["val"].setValue(p.value)
            row["val2"].setValue(p.value2)
            row["val2"].setVisible(p.op == "between")
        self.btn_toggle.setChecked(bool(preds))
        self._emit()

    def _reload_presets(self):
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("—", None)
        for pr in presets_mod.list_presets():
            self.preset_combo.addItem(pr.name, pr.id)
        self.preset_combo.blockSignals(False)

    def _load_preset(self, _idx):
        pid = self.preset_combo.currentData()
        if pid is None:
            return
        for pr in presets_mod.list_presets():
            if pr.id == pid:
                self.set_predicates(pr.predicates)
                self.set_signals(self._signals)
                break

    def _save_preset(self):
        preds = self._collect(force=True)
        if not preds:
            QtWidgets.QMessageBox.information(self, "プリセット保存", "条件がありません。")
            return
        default = self.preset_combo.currentText() if self.preset_combo.currentData() else ""
        name, ok = QtWidgets.QInputDialog.getText(
            self, "プリセット保存", "名前:", text=default)
        if ok and name.strip():
            presets_mod.save(name.strip(), preds)
            self._reload_presets()
            i = self.preset_combo.findText(name.strip())
            if i >= 0:
                self.preset_combo.setCurrentIndex(i)

    def _delete_preset(self):
        pid = self.preset_combo.currentData()
        if pid is None:
            return
        presets_mod.delete(pid)
        self._reload_presets()

    def _collect(self, force: bool = False) -> list[Predicate]:
        if not force and not self.enable.isChecked():
            return []
        out = []
        for row in self._rows:
            sig = row["sig"].currentText()
            if not sig:
                continue
            out.append(Predicate(sig, row["op"].currentData(),
                                 float(row["val"].value()), float(row["val2"].value())))
        return out

    def predicates(self) -> list[Predicate]:
        return self._collect(force=False)
