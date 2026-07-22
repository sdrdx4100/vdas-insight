"""Right dock: tag (cohort) management and membership for the current dataset."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from vdas import tags as tags_mod
from vdas.config import TAG_COLORS
from ..state import AppState


class TagsPanel(QtWidgets.QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        # New-tag row (name + category + color)
        add_row = QtWidgets.QHBoxLayout()
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("新しいタグ名…")
        self.cat_edit = QtWidgets.QComboBox()
        self.cat_edit.setEditable(True)
        self.cat_edit.lineEdit().setPlaceholderText("カテゴリ(任意)")
        self.cat_edit.setMinimumWidth(110)
        self.color_combo = QtWidgets.QComboBox()
        for c in TAG_COLORS:
            pm = QtGui.QPixmap(12, 12)
            pm.fill(QtGui.QColor(c))
            self.color_combo.addItem(QtGui.QIcon(pm), "", c)
        self.btn_create = QtWidgets.QPushButton("作成")
        self.btn_create.setObjectName("primary")
        add_row.addWidget(self.name_edit, 2)
        add_row.addWidget(self.cat_edit, 1)
        add_row.addWidget(self.color_combo)
        add_row.addWidget(self.btn_create)
        lay.addLayout(add_row)

        lbl = QtWidgets.QLabel("このデータセットの所属タグ:")
        lbl.setObjectName("dim")
        lay.addWidget(lbl)

        self.list = QtWidgets.QListWidget()
        lay.addWidget(self.list)

        self.btn_del = QtWidgets.QPushButton("選択タグを削除")
        lay.addWidget(self.btn_del)

        self.btn_create.clicked.connect(self._create)
        self.list.itemChanged.connect(self._on_toggle)
        self.btn_del.clicked.connect(self._delete_selected)
        self.state.currentDatasetChanged.connect(lambda _id: self.reload())
        self.state.tagsChanged.connect(self.reload)
        self.reload()

    def reload(self):
        self.list.blockSignals(True)
        self.list.clear()
        d = self.state.current_dataset()
        member = set(tags_mod.tag_ids_for_dataset(d.id)) if d else set()
        # refresh category suggestions
        cur_cat = self.cat_edit.currentText()
        self.cat_edit.blockSignals(True)
        self.cat_edit.clear()
        self.cat_edit.addItems([""] + tags_mod.list_categories())
        self.cat_edit.setCurrentText(cur_cat)
        self.cat_edit.blockSignals(False)

        last_cat = object()
        for t in tags_mod.list_tags():
            cat = t.category or "（カテゴリなし）"
            if cat != last_cat:
                hdr = QtWidgets.QListWidgetItem(f"— {cat} —")
                hdr.setFlags(QtCore.Qt.NoItemFlags)
                hdr.setForeground(QtGui.QColor("#8b9099"))
                self.list.addItem(hdr)
                last_cat = cat
            it = QtWidgets.QListWidgetItem(f"{t.name}  ({t.dataset_count})")
            it.setData(QtCore.Qt.UserRole, t.id)
            pm = QtGui.QPixmap(12, 12)
            pm.fill(QtGui.QColor(t.color or "#888"))
            it.setIcon(QtGui.QIcon(pm))
            it.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled
                        | QtCore.Qt.ItemIsSelectable)
            it.setCheckState(QtCore.Qt.Checked if t.id in member else QtCore.Qt.Unchecked)
            if d is None:
                it.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            self.list.addItem(it)
        self.list.blockSignals(False)

    def _create(self):
        name = self.name_edit.text().strip()
        if not name:
            return
        if any(t.name == name for t in tags_mod.list_tags()):
            QtWidgets.QMessageBox.warning(self, "重複", "同名のタグが存在します。")
            return
        tags_mod.create(name, self.color_combo.currentData(),
                        category=self.cat_edit.currentText().strip() or None)
        self.name_edit.clear()
        self.state.tagsChanged.emit()

    def _on_toggle(self, item):
        d = self.state.current_dataset()
        if not d:
            return
        tid = item.data(QtCore.Qt.UserRole)
        if tid is None:
            return
        if item.checkState() == QtCore.Qt.Checked:
            tags_mod.assign(d.id, tid)
        else:
            tags_mod.unassign(d.id, tid)
        self.state.tagsChanged.emit()

    def _delete_selected(self):
        it = self.list.currentItem()
        if not it:
            return
        tid = it.data(QtCore.Qt.UserRole)
        if tid is None:
            return
        name = it.text()
        if QtWidgets.QMessageBox.question(
                self, "タグ削除", f"タグ『{name}』を削除しますか？") == QtWidgets.QMessageBox.Yes:
            tags_mod.delete(tid)
            self.state.tagsChanged.emit()
