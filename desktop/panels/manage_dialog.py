"""Data-management dialog: multi-select datasets, bulk tag & bulk delete."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from vdas import datasets as ds_mod
from vdas import tags as tags_mod
from .. import services
from ..state import AppState


class ManageDialog(QtWidgets.QDialog):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("データ管理")
        self.resize(880, 560)
        lay = QtWidgets.QVBoxLayout(self)

        hint = QtWidgets.QLabel(
            "複数行を選択（Shift / Ctrl）して一括操作。名前はダブルクリックでリネームできます。")
        hint.setObjectName("dim")
        lay.addWidget(hint)

        # --- filter bar -----------------------------------------------------
        fbar = QtWidgets.QHBoxLayout()
        fbar.addWidget(QtWidgets.QLabel("検索:"))
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("名前で絞り込み…")
        self.search.setClearButtonEnabled(True)
        fbar.addWidget(self.search, 1)
        fbar.addWidget(QtWidgets.QLabel("タグ:"))
        self.filter_combo = QtWidgets.QComboBox()
        self.filter_combo.setMinimumWidth(160)
        fbar.addWidget(self.filter_combo)
        lay.addLayout(fbar)

        # --- bulk action bar ------------------------------------------------
        bar = QtWidgets.QHBoxLayout()
        bar.addWidget(QtWidgets.QLabel("タグ:"))
        self.tag_combo = QtWidgets.QComboBox()
        self.tag_combo.setMinimumWidth(200)
        bar.addWidget(self.tag_combo)
        self.btn_assign = QtWidgets.QPushButton("選択に付与")
        self.btn_assign.setObjectName("primary")
        self.btn_unassign = QtWidgets.QPushButton("選択から解除")
        bar.addWidget(self.btn_assign)
        bar.addWidget(self.btn_unassign)
        self.excl_check = QtWidgets.QCheckBox("同カテゴリを置換")
        self.excl_check.setToolTip("付与時、同じカテゴリの既存タグを外して1つだけにします")
        bar.addWidget(self.excl_check)
        bar.addStretch(1)
        self.btn_delete = QtWidgets.QPushButton("🗑 選択を一括削除")
        bar.addWidget(self.btn_delete)
        lay.addLayout(bar)

        # --- table ----------------------------------------------------------
        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["データセット", "形式", "行数", "状態", "タグ"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.table, 1)

        foot = QtWidgets.QHBoxLayout()
        self.sel_lbl = QtWidgets.QLabel("")
        self.sel_lbl.setObjectName("dim")
        foot.addWidget(self.sel_lbl)
        foot.addStretch(1)
        close = QtWidgets.QPushButton("閉じる")
        close.clicked.connect(self.accept)
        foot.addWidget(close)
        lay.addLayout(foot)

        self.btn_assign.clicked.connect(lambda: self._bulk_tag(True))
        self.btn_unassign.clicked.connect(lambda: self._bulk_tag(False))
        self.btn_delete.clicked.connect(self._bulk_delete)
        self.table.itemSelectionChanged.connect(self._update_selcount)
        self.table.cellDoubleClicked.connect(self._rename_row)
        self.search.textChanged.connect(self.reload)
        self.filter_combo.currentIndexChanged.connect(self.reload)
        self.reload()

    # ------------------------------------------------------------------ data
    def reload(self):
        cur_tag = self.tag_combo.currentData()
        cur_filter = self.filter_combo.currentData()
        # Mutating the combos fires currentIndexChanged; block it so filter_combo
        # (wired to reload) doesn't recurse into reload().
        self.tag_combo.blockSignals(True)
        self.filter_combo.blockSignals(True)
        self.tag_combo.clear()
        self.filter_combo.clear()
        self.filter_combo.addItem("（すべて）", None)
        for t in tags_mod.list_tags():
            label = f"[{t.category}] {t.name}" if t.category else t.name
            pm = QtGui.QPixmap(12, 12)
            pm.fill(QtGui.QColor(t.color or "#888"))
            self.tag_combo.addItem(QtGui.QIcon(pm), label, t.id)
            self.filter_combo.addItem(QtGui.QIcon(pm), label, t.id)
        if cur_tag is not None:
            i = self.tag_combo.findData(cur_tag)
            if i >= 0:
                self.tag_combo.setCurrentIndex(i)
        if cur_filter is not None:
            i = self.filter_combo.findData(cur_filter)
            self.filter_combo.setCurrentIndex(i if i >= 0 else 0)
        self.tag_combo.blockSignals(False)
        self.filter_combo.blockSignals(False)

        needle = self.search.text().strip().lower()
        only_tag = self.filter_combo.currentData()
        tag_map = {t.id: t for t in tags_mod.list_tags()}
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for d in ds_mod.list_datasets():
            if needle and needle not in d.name.lower():
                continue
            ds_tags = tags_mod.tag_ids_for_dataset(d.id)
            if only_tag is not None and only_tag not in ds_tags:
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            name_it = QtWidgets.QTableWidgetItem(d.name)
            name_it.setData(QtCore.Qt.UserRole, d.id)
            self.table.setItem(r, 0, name_it)
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(d.format))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(f"{d.row_count:,}"))
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem("OK" if d.exists else "⚠ 消失"))
            tnames = ", ".join(tag_map[i].name for i in ds_tags if i in tag_map)
            self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(tnames))
        self.table.blockSignals(False)
        self.table.resizeColumnsToContents()
        self._update_selcount()

    def _rename_row(self, row: int, col: int):
        it = self.table.item(row, 0)
        if it is None:
            return
        did = it.data(QtCore.Qt.UserRole)
        new, ok = QtWidgets.QInputDialog.getText(
            self, "名前を変更", "新しい名前:", text=it.text())
        if ok and new.strip():
            ds_mod.rename(did, new.strip())
            self.reload()
            self.state.datasetsChanged.emit()

    def _selected_ids(self) -> list[int]:
        ids = []
        for idx in self.table.selectionModel().selectedRows():
            it = self.table.item(idx.row(), 0)
            if it:
                ids.append(it.data(QtCore.Qt.UserRole))
        return ids

    def _update_selcount(self):
        n = len(self._selected_ids())
        self.sel_lbl.setText(f"{n} 件選択中" if n else "")

    # --------------------------------------------------------------- actions
    def _bulk_tag(self, assign: bool):
        ids = self._selected_ids()
        tid = self.tag_combo.currentData()
        if not ids or tid is None:
            return
        if assign:
            tags_mod.assign_many(ids, tid, exclusive=self.excl_check.isChecked())
        else:
            tags_mod.unassign_many(ids, tid)
        self.reload()
        self.state.tagsChanged.emit()

    def _bulk_delete(self):
        ids = self._selected_ids()
        if not ids:
            return
        if QtWidgets.QMessageBox.question(
                self, "一括削除の確認",
                f"{len(ids)} 件を登録から削除しますか？（元ファイルは削除されません）"
                ) != QtWidgets.QMessageBox.Yes:
            return
        for did in ids:
            ds_mod.delete(did)
            services.invalidate(did)
        if self.state.current_id in ids:
            self.state.set_current(-1)
        self.reload()
        self.state.datasetsChanged.emit()
        self.state.tagsChanged.emit()
