"""Left dock: dataset catalogue (register / select / delete)."""
from __future__ import annotations

import glob
import os

from PySide6 import QtCore, QtWidgets

from vdas import datasets as ds_mod
from vdas import tags as tags_mod
from .. import services
from ..state import AppState


class DatasetPanel(QtWidgets.QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton("＋ 登録")
        self.btn_add.setObjectName("primary")
        self.btn_del = QtWidgets.QPushButton("削除")
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_del)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["データセット", "行数", "タグ"])
        self.tree.setRootIsDecorated(False)
        self.tree.setColumnWidth(0, 190)
        self.tree.setColumnWidth(1, 70)
        lay.addWidget(self.tree)

        self.btn_add.clicked.connect(self.register_dialog)
        self.btn_del.clicked.connect(self.delete_current)
        self.tree.currentItemChanged.connect(self._on_select)
        self.state.datasetsChanged.connect(self.reload)
        self.state.tagsChanged.connect(self.reload)
        self.reload()

    # ------------------------------------------------------------------ data
    def reload(self):
        keep = self.state.current_id
        self.tree.blockSignals(True)
        self.tree.clear()
        target = None
        tag_map = {t.id: t for t in tags_mod.list_tags()}
        for d in ds_mod.list_datasets():
            tnames = ", ".join(tag_map[t].name for t in tags_mod.tag_ids_for_dataset(d.id)
                               if t in tag_map)
            it = QtWidgets.QTreeWidgetItem([d.name, f"{d.row_count:,}", tnames or "—"])
            it.setData(0, QtCore.Qt.UserRole, d.id)
            if not d.exists:
                it.setForeground(0, QtCore.Qt.red)
            self.tree.addTopLevelItem(it)
            if d.id == keep:
                target = it
        self.tree.blockSignals(False)
        if target:
            self.tree.setCurrentItem(target)
        elif self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _on_select(self, cur, _prev):
        if cur is None:
            return
        did = cur.data(0, QtCore.Qt.UserRole)
        if did is not None:
            self.state.set_current(int(did))

    # -------------------------------------------------------------- register
    def register_dialog(self):
        menu = QtWidgets.QMenu(self)
        act_files = menu.addAction("ファイルを選択して登録…")
        act_glob = menu.addAction("パス / グロブで登録…")
        act_sample = menu.addAction("同梱サンプルを一括登録")
        chosen = menu.exec(self.btn_add.mapToGlobal(self.btn_add.rect().bottomLeft()))
        if chosen == act_files:
            paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
                self, "データファイルを選択", os.getcwd(),
                "Telemetry (*.parquet *.csv)")
            self._register_paths(paths)
        elif chosen == act_glob:
            text, ok = QtWidgets.QInputDialog.getText(
                self, "パス / グロブ", "parquet / csv のパス（グロブ可）:",
                text=str(_sample_glob()))
            if ok and text:
                self._register_paths(sorted(glob.glob(text)))
        elif chosen == act_sample:
            self._register_paths(sorted(glob.glob(str(_sample_glob()))),
                                 tag_by_regime=True)

    def _register_paths(self, paths, tag_by_regime=False):
        if not paths:
            return
        existing = {d.path for d in ds_mod.list_datasets()}
        new_ids = []
        for p in paths:
            if os.path.abspath(p) in existing:
                continue
            try:
                new_ids.append(ds_mod.register(p).id)
            except Exception as e:  # noqa: BLE001
                QtWidgets.QMessageBox.warning(self, "登録エラー", f"{p}\n{e}")
        if tag_by_regime:
            self._auto_tag()
        services.invalidate()
        self.state.datasetsChanged.emit()
        self.state.tagsChanged.emit()
        # Offer to bulk-tag the freshly registered datasets at load time.
        if new_ids and not tag_by_regime:
            self._tag_new(new_ids)
        else:
            QtWidgets.QMessageBox.information(self, "登録完了", f"{len(new_ids)} 件を登録しました。")

    def _tag_new(self, dataset_ids):
        from .tag_pick_dialog import TagPickDialog
        dlg = TagPickDialog(
            "登録したデータにタグを付与",
            f"{len(dataset_ids)} 件を登録しました。まとめて付与するタグを選択できます"
            "（メーカー・走行条件など。後から『データ管理』でも変更可）。", self)
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg.selected_ids:
            for did in dataset_ids:
                for tid in dlg.selected_ids:
                    tags_mod.assign(did, tid)
            self.state.tagsChanged.emit()

    def _auto_tag(self):
        by = {t.name: t.id for t in tags_mod.list_tags()}
        tc = by.get("city") or tags_mod.create("city", "#3987e5", "市街地走行").id
        th = by.get("highway") or tags_mod.create("highway", "#d95926", "高速走行").id
        for d in ds_mod.list_datasets():
            if d.name.startswith("city"):
                tags_mod.assign(d.id, tc)
            elif d.name.startswith("highway"):
                tags_mod.assign(d.id, th)

    def delete_current(self):
        d = self.state.current_dataset()
        if not d:
            return
        if QtWidgets.QMessageBox.question(
                self, "削除の確認",
                f"『{d.name}』を登録から削除しますか？（元ファイルは削除されません）"
                ) == QtWidgets.QMessageBox.Yes:
            ds_mod.delete(d.id)
            services.invalidate(d.id)
            self.state.set_current(-1)
            self.state.datasetsChanged.emit()


def _sample_glob():
    from vdas.config import PROJECT_ROOT
    return PROJECT_ROOT / "sample_data" / "*.parquet"
