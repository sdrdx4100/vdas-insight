"""Right dock: column-role editor for the current dataset."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from vdas import datasets as ds_mod
from vdas.config import ROLE_LABELS, ROLES
from .. import services
from ..state import AppState

_UNITS = ["s", "ms", "us", "ns", "min"]


class PropertiesPanel(QtWidgets.QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        self.info = QtWidgets.QLabel("—")
        self.info.setObjectName("dim")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)

        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["列", "役割", "単位"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(1, 110)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.table)

        row = QtWidgets.QHBoxLayout()
        self.btn_auto = QtWidgets.QPushButton("自動推定")
        self.btn_save = QtWidgets.QPushButton("保存")
        self.btn_save.setObjectName("primary")
        row.addWidget(self.btn_auto)
        row.addStretch(1)
        row.addWidget(self.btn_save)
        lay.addLayout(row)

        self.btn_auto.clicked.connect(self._autodetect)
        self.btn_save.clicked.connect(self._save)
        self.state.currentDatasetChanged.connect(lambda _id: self.reload())
        self.reload()

    def reload(self):
        d = self.state.current_dataset()
        self.table.setRowCount(0)
        if not d or not d.exists:
            self.info.setText("データセット未選択")
            return
        self.info.setText(f"{d.name}  ·  {d.format}  ·  {d.row_count:,} 行\n{d.path}")
        roles = ds_mod.get_roles(d.id)
        params = ds_mod.get_role_params(d.id)
        sch = dict(ds_mod.schema(d))
        self._combos: dict[str, QtWidgets.QComboBox] = {}
        self._units: dict[str, QtWidgets.QComboBox] = {}
        for col in ds_mod.columns(d):
            r = self.table.rowCount()
            self.table.insertRow(r)
            name_item = QtWidgets.QTableWidgetItem(col)
            name_item.setToolTip(sch.get(col, ""))
            self.table.setItem(r, 0, name_item)
            combo = QtWidgets.QComboBox()
            for role in ROLES:
                combo.addItem(ROLE_LABELS.get(role, role), role)
            cur = roles.get(col, "numeric")
            combo.setCurrentIndex(ROLES.index(cur) if cur in ROLES else 0)
            self.table.setCellWidget(r, 1, combo)
            self._combos[col] = combo
            unit = QtWidgets.QComboBox()
            unit.addItems(_UNITS)
            u = (params.get(col) or {}).get("unit", "s")
            unit.setCurrentText(u if u in _UNITS else "s")
            unit.setEnabled(cur == "time")
            combo.currentIndexChanged.connect(
                lambda _i, c=col: self._units[c].setEnabled(
                    self._combos[c].currentData() == "time"))
            self.table.setCellWidget(r, 2, unit)
            self._units[col] = unit

    def _autodetect(self):
        d = self.state.current_dataset()
        if not d:
            return
        ds_mod.set_roles(d.id, ds_mod.auto_detect_roles(d))
        services.invalidate(d.id)
        self.reload()
        self.state.rolesChanged.emit(d.id)

    def _save(self):
        d = self.state.current_dataset()
        if not d:
            return
        roles, params = {}, {}
        for col, combo in self._combos.items():
            roles[col] = combo.currentData()
            if roles[col] == "time":
                params[col] = {"unit": self._units[col].currentText()}
        if sum(1 for r in roles.values() if r == "time") > 1:
            QtWidgets.QMessageBox.warning(self, "役割エラー", "時間列は 1 つだけにしてください。")
            return
        ds_mod.set_roles(d.id, roles, params)
        services.invalidate(d.id)
        self.state.rolesChanged.emit(d.id)
        QtWidgets.QMessageBox.information(self, "保存", "役割を保存しました。")
