"""Reusable dialog: pick multiple tags (grouped by category) to apply."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from vdas import tags as tags_mod


class TagPickDialog(QtWidgets.QDialog):
    """Multi-select of existing tags. ``selected_ids`` holds the result."""

    def __init__(self, title: str, message: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)
        lay = QtWidgets.QVBoxLayout(self)
        if message:
            lbl = QtWidgets.QLabel(message)
            lbl.setObjectName("dim")
            lbl.setWordWrap(True)
            lay.addWidget(lbl)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        lay.addWidget(self.tree)
        self._populate()

        # inline quick-create
        add = QtWidgets.QHBoxLayout()
        self.new_name = QtWidgets.QLineEdit()
        self.new_name.setPlaceholderText("新規タグ名…")
        self.new_cat = QtWidgets.QLineEdit()
        self.new_cat.setPlaceholderText("カテゴリ(任意)")
        self.btn_new = QtWidgets.QPushButton("追加")
        add.addWidget(self.new_name, 2)
        add.addWidget(self.new_cat, 1)
        add.addWidget(self.btn_new)
        lay.addLayout(add)
        self.btn_new.clicked.connect(self._quick_create)

        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.selected_ids: list[int] = []

    def _populate(self, keep_checked: set[int] | None = None):
        keep_checked = keep_checked or set()
        self.tree.clear()
        by_cat: dict[str, list] = {}
        for t in tags_mod.list_tags():
            by_cat.setdefault(t.category or "（カテゴリなし）", []).append(t)
        for cat, items in by_cat.items():
            grp = QtWidgets.QTreeWidgetItem([cat])
            grp.setFlags(QtCore.Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(grp)
            grp.setExpanded(True)
            for t in items:
                it = QtWidgets.QTreeWidgetItem([f"{t.name}  ({t.dataset_count})"])
                it.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
                it.setCheckState(0, QtCore.Qt.Checked if t.id in keep_checked
                                 else QtCore.Qt.Unchecked)
                it.setData(0, QtCore.Qt.UserRole, t.id)
                pm = QtGui.QPixmap(12, 12)
                pm.fill(QtGui.QColor(t.color or "#888"))
                it.setIcon(0, QtGui.QIcon(pm))
                grp.addChild(it)

    def _checked_ids(self) -> list[int]:
        out = []
        for i in range(self.tree.topLevelItemCount()):
            grp = self.tree.topLevelItem(i)
            for j in range(grp.childCount()):
                it = grp.child(j)
                if it.checkState(0) == QtCore.Qt.Checked:
                    out.append(it.data(0, QtCore.Qt.UserRole))
        return out

    def _quick_create(self):
        name = self.new_name.text().strip()
        if not name:
            return
        if any(t.name == name for t in tags_mod.list_tags()):
            QtWidgets.QMessageBox.warning(self, "重複", "同名のタグが存在します。")
            return
        tags_mod.create(name, category=self.new_cat.text().strip() or None)
        self.new_name.clear(); self.new_cat.clear()
        checked = set(self._checked_ids())
        checked.add(next(t.id for t in tags_mod.list_tags() if t.name == name))
        self._populate(keep_checked=checked)

    def _accept(self):
        self.selected_ids = self._checked_ids()
        self.accept()
