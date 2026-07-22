"""Dialog to define a derived signal (acceleration, jerk, derivative, ...)."""
from __future__ import annotations

from PySide6 import QtWidgets

from vdas import datasets as ds_mod
from vdas import derived
from vdas.datasets import Dataset

# Kinds whose result is a derivative / smoothed → expose a smoothing window.
_WINDOW_KINDS = {"accel_from_speed", "jerk_from_speed", "derivative",
                 "second_derivative", "rolling_mean"}


class DerivedDialog(QtWidgets.QDialog):
    def __init__(self, dataset: Dataset, parent=None):
        super().__init__(parent)
        self.dataset = dataset
        self.setWindowTitle("派生信号を追加")
        self.setMinimumWidth(420)

        form = QtWidgets.QFormLayout(self)

        # source candidates: numeric + speed columns + existing derived
        self._sources = (ds_mod.numeric_columns(dataset.id)
                         + derived.names_for_dataset(dataset.id))
        self._speed = ds_mod.speed_column(dataset.id)
        self.src_combo = QtWidgets.QComboBox()
        self.src_combo.addItems(self._sources)
        if self._speed and self._speed in self._sources:
            self.src_combo.setCurrentText(self._speed)
        form.addRow("元信号:", self.src_combo)

        self.kind_combo = QtWidgets.QComboBox()
        for k in derived.KINDS.values():
            self.kind_combo.addItem(k.label, k.key)
        form.addRow("種類:", self.kind_combo)

        self.name_edit = QtWidgets.QLineEdit()
        form.addRow("信号名:", self.name_edit)

        self.window_spin = QtWidgets.QDoubleSpinBox()
        self.window_spin.setRange(0.0, 30.0)
        self.window_spin.setSingleStep(0.1)
        self.window_spin.setSuffix(" s")
        self.window_row = QtWidgets.QLabel("平滑化窓 (移動平均):")
        form.addRow(self.window_row, self.window_spin)

        self.hint = QtWidgets.QLabel()
        self.hint.setObjectName("dim")
        self.hint.setWordWrap(True)
        form.addRow(self.hint)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        form.addRow(buttons)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        self.src_combo.currentIndexChanged.connect(self._sync)
        self.kind_combo.currentIndexChanged.connect(self._sync)
        self._name_edited = False
        self.name_edit.textEdited.connect(lambda _t: setattr(self, "_name_edited", True))
        # Default to acceleration when a speed signal exists.
        if self._speed:
            i = self.kind_combo.findData("accel_from_speed")
            if i >= 0:
                self.kind_combo.setCurrentIndex(i)
        self._sync()

    def _sync(self):
        kind = derived.KINDS[self.kind_combo.currentData()]
        src = self.src_combo.currentText()
        if not self._name_edited:
            self.name_edit.setText(derived.suggest_name(kind.key, src))
        show_win = kind.key in _WINDOW_KINDS
        self.window_row.setVisible(show_win)
        self.window_spin.setVisible(show_win)
        if show_win:
            # reset to the kind's default only if user hasn't touched it
            self.window_spin.setValue(kind.default_window_s)
        out_unit = kind.unit_fn("km/h" if src == self._speed else "")
        note = f"出力単位の目安: {out_unit}。" if out_unit else ""
        if kind.needs_speed and src != self._speed:
            note += " ※このプリセットは車速(km/h)を前提とします。"
        self.hint.setText(note)

    def _accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "入力エラー", "信号名を入力してください。")
            return
        taken = set(ds_mod.columns(self.dataset)) | set(
            derived.names_for_dataset(self.dataset.id))
        if name in taken:
            QtWidgets.QMessageBox.warning(self, "重複", "その信号名は既に使われています。")
            return
        kind = self.kind_combo.currentData()
        params = {}
        if kind in _WINDOW_KINDS:
            params["window_s"] = float(self.window_spin.value())
        derived.add(self.dataset.id, kind, self.src_combo.currentText(),
                    name=name, params=params)
        self.created_name = name
        self.accept()
