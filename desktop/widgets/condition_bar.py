"""Condition builder: compose AND predicates for gated cohort aggregation."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from vdas.analysis.conditions import OPS, Predicate


class ConditionBar(QtWidgets.QWidget):
    changed = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self._signals: list[str] = []
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        head = QtWidgets.QHBoxLayout()
        self.enable = QtWidgets.QCheckBox("集計条件 (AND)")
        self.enable.setToolTip("条件を満たすサンプルだけで集計します（例: 車速 ≤ 70）")
        head.addWidget(self.enable)
        self.btn_add = QtWidgets.QPushButton("＋条件")
        self.btn_add.setFixedWidth(64)
        head.addWidget(self.btn_add)
        head.addStretch(1)
        lay.addLayout(head)

        self.rows_box = QtWidgets.QVBoxLayout()
        self.rows_box.setSpacing(3)
        lay.addLayout(self.rows_box)
        self._rows: list[dict] = []

        self.enable.toggled.connect(self._on_enable)
        self.btn_add.clicked.connect(lambda: (self._add_row(), self._emit()))
        self._on_enable(False)

    # ---------------------------------------------------------------- signals
    def set_signals(self, cols: list[str]):
        self._signals = list(cols)
        for row in self._rows:
            cur = row["sig"].currentText()
            row["sig"].blockSignals(True)
            row["sig"].clear(); row["sig"].addItems(self._signals)
            if cur in self._signals:
                row["sig"].setCurrentText(cur)
            row["sig"].blockSignals(False)

    def _on_enable(self, on: bool):
        self.btn_add.setEnabled(on)
        for row in self._rows:
            row["w"].setEnabled(on)
        if on and not self._rows:
            self._add_row()
        self._emit()

    def _add_row(self, signal: str | None = None):
        w = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(4)
        sig = QtWidgets.QComboBox(); sig.setMinimumWidth(150); sig.addItems(self._signals)
        if signal and signal in self._signals:
            sig.setCurrentText(signal)
        op = QtWidgets.QComboBox()
        for k, lbl in OPS.items():
            op.addItem(lbl, k)
        val = QtWidgets.QDoubleSpinBox(); val.setRange(-1e9, 1e9); val.setDecimals(2)
        val2 = QtWidgets.QDoubleSpinBox(); val2.setRange(-1e9, 1e9); val2.setDecimals(2)
        val2.setVisible(False)
        rm = QtWidgets.QPushButton("✕"); rm.setFixedWidth(26)
        for x in (sig, op, val, val2):
            h.addWidget(x)
        h.addWidget(rm); h.addStretch(1)
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
        self.changed.emit()

    # ---------------------------------------------------------------- output
    def predicates(self) -> list[Predicate]:
        if not self.enable.isChecked():
            return []
        out = []
        for row in self._rows:
            sig = row["sig"].currentText()
            if not sig:
                continue
            out.append(Predicate(sig, row["op"].currentData(),
                                 float(row["val"].value()), float(row["val2"].value())))
        return out
