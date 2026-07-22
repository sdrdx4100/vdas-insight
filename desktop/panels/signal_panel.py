"""Left dock: signal (variable) selection for the current dataset.

Mimics the INCA "variable selection" list: every signal with a colored role
badge; ticking a signal adds it to the measurement (oscilloscope) view.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from vdas import datasets as ds_mod
from .. import theme
from ..state import AppState


class SignalPanel(QtWidgets.QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        self.filter = QtWidgets.QLineEdit()
        self.filter.setPlaceholderText("信号名でフィルタ…")
        self.filter.setClearButtonEnabled(True)
        lay.addWidget(self.filter)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["信号", "役割"])
        self.tree.setRootIsDecorated(True)
        self.tree.setColumnWidth(0, 180)
        lay.addWidget(self.tree)

        row = QtWidgets.QHBoxLayout()
        self.btn_none = QtWidgets.QPushButton("全解除")
        self.btn_defaults = QtWidgets.QPushButton("既定選択")
        row.addWidget(self.btn_defaults)
        row.addWidget(self.btn_none)
        row.addStretch(1)
        lay.addLayout(row)

        self.filter.textChanged.connect(self._apply_filter)
        self.tree.itemChanged.connect(self._on_check)
        self.btn_none.clicked.connect(lambda: self._check_all(False))
        self.btn_defaults.clicked.connect(self._select_defaults)
        self.state.currentDatasetChanged.connect(lambda _id: self.reload())
        self.state.rolesChanged.connect(lambda _id: self.reload())
        self.reload()

    def reload(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        d = self.state.current_dataset()
        self._role_groups: dict[str, QtWidgets.QTreeWidgetItem] = {}
        if d and d.exists:
            roles = ds_mod.get_roles(d.id)
            order = ["speed", "gear", "flag", "numeric", "category", "time", "ignore"]
            cols = ds_mod.columns(d)
            grouped: dict[str, list[str]] = {}
            for c in cols:
                grouped.setdefault(roles.get(c, "numeric"), []).append(c)
            for role in order:
                if role not in grouped:
                    continue
                grp = QtWidgets.QTreeWidgetItem([role.upper(), ""])
                grp.setFlags(QtCore.Qt.ItemIsEnabled)
                grp.setForeground(0, QtGui.QColor(theme.INK_DIM))
                self.tree.addTopLevelItem(grp)
                grp.setExpanded(True)
                for c in grouped[role]:
                    it = QtWidgets.QTreeWidgetItem([c, role])
                    it.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
                    plottable = role != "time"
                    it.setCheckState(0, QtCore.Qt.Unchecked if plottable
                                     else QtCore.Qt.Unchecked)
                    if not plottable:
                        it.setFlags(QtCore.Qt.ItemIsEnabled)
                    it.setData(0, QtCore.Qt.UserRole, c)
                    self._badge(it, role)
                    grp.addChild(it)
        self.tree.blockSignals(False)
        self._select_defaults()

    def _badge(self, item, role):
        color = theme.ROLE_COLORS.get(role, theme.INK_DIM)
        item.setForeground(1, QtGui.QColor(color))
        pm = QtGui.QPixmap(10, 10)
        pm.fill(QtGui.QColor(color))
        item.setIcon(1, QtGui.QIcon(pm))

    # ------------------------------------------------------------- selection
    def _iter_signal_items(self):
        for i in range(self.tree.topLevelItemCount()):
            grp = self.tree.topLevelItem(i)
            for j in range(grp.childCount()):
                yield grp.child(j)

    def _on_check(self, *_):
        self.state.set_plot_signals(self._checked())

    def _checked(self) -> list[str]:
        out = []
        for it in self._iter_signal_items():
            if it.flags() & QtCore.Qt.ItemIsUserCheckable and it.checkState(0) == QtCore.Qt.Checked:
                out.append(it.data(0, QtCore.Qt.UserRole))
        return out

    def _check_all(self, on: bool):
        self.tree.blockSignals(True)
        for it in self._iter_signal_items():
            if it.flags() & QtCore.Qt.ItemIsUserCheckable:
                it.setCheckState(0, QtCore.Qt.Checked if on else QtCore.Qt.Unchecked)
        self.tree.blockSignals(False)
        self._on_check()

    def _select_defaults(self):
        d = self.state.current_dataset()
        if not d or not d.exists:
            return
        want = set()
        sp = ds_mod.speed_column(d.id)
        g = ds_mod.gear_column(d.id)
        if sp:
            want.add(sp)
        if g:
            want.add(g)
        self.tree.blockSignals(True)
        for it in self._iter_signal_items():
            if it.flags() & QtCore.Qt.ItemIsUserCheckable:
                it.setCheckState(0, QtCore.Qt.Checked
                                 if it.data(0, QtCore.Qt.UserRole) in want
                                 else QtCore.Qt.Unchecked)
        self.tree.blockSignals(False)
        self._on_check()

    def _apply_filter(self, text: str):
        text = text.lower()
        for it in self._iter_signal_items():
            name = (it.data(0, QtCore.Qt.UserRole) or "").lower()
            it.setHidden(bool(text) and text not in name)
