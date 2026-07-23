"""2D operating-map view (engine-map / EX-Summary style contour heatmap)."""
from __future__ import annotations

from PySide6 import QtWidgets

from vdas.analysis import maps
from .. import services
from ..state import AppState
from ..widgets.charts import HeatMap2D


class MapView(QtWidgets.QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        ctl = QtWidgets.QHBoxLayout()
        self.x_combo = QtWidgets.QComboBox(); self.x_combo.setMinimumWidth(150)
        self.y_combo = QtWidgets.QComboBox(); self.y_combo.setMinimumWidth(150)
        self.mode_combo = QtWidgets.QComboBox()
        for k in (maps.MODE_DENSITY, maps.MODE_COUNT, maps.MODE_MEAN, maps.MODE_STD):
            self.mode_combo.addItem(maps.MODE_LABELS[k], k)
        self.z_combo = QtWidgets.QComboBox(); self.z_combo.setMinimumWidth(150)
        self.bins = QtWidgets.QSpinBox(); self.bins.setRange(5, 200); self.bins.setValue(40)
        for w, lbl in ((self.x_combo, "X:"), (self.y_combo, "Y:"),
                       (self.mode_combo, "色 (Z):"), (self.z_combo, "Z信号:"),
                       (self.bins, "分割数:")):
            ctl.addWidget(QtWidgets.QLabel(lbl)); ctl.addWidget(w)
        ctl.addStretch(1)
        lay.addLayout(ctl)

        self.msg = QtWidgets.QLabel(); self.msg.setObjectName("dim")
        lay.addWidget(self.msg)
        self.map = HeatMap2D()
        lay.addWidget(self.map, 1)

        for c in (self.x_combo, self.y_combo, self.z_combo):
            c.currentIndexChanged.connect(self._redraw)
        self.mode_combo.currentIndexChanged.connect(self._on_mode)
        self.bins.valueChanged.connect(self._redraw)
        self.state.currentDatasetChanged.connect(lambda _id: self.rebuild())
        self.state.rolesChanged.connect(lambda _id: self.rebuild())

    def _signals(self, pdd):
        cols = list(pdd.numeric_cols)
        if pdd.gear_col and pdd.gear_col not in cols:
            cols.append(pdd.gear_col)
        return cols

    def rebuild(self):
        d = self.state.current_dataset()
        if not d or not d.exists:
            return
        pdd = services.get_prepared(d)
        cols = self._signals(pdd)
        if len(cols) < 2:
            self.msg.setText("数値信号が2つ以上必要です。")
            return
        self.msg.setText("")
        prev = {c.objectName(): c.currentText() for c in
                (self.x_combo, self.y_combo, self.z_combo)}
        for combo, default in ((self.x_combo, pdd.speed_col or cols[0]),
                               (self.y_combo, self._default_y(pdd, cols)),
                               (self.z_combo, cols[0])):
            combo.blockSignals(True)
            combo.clear(); combo.addItems(cols)
            combo.setCurrentText(default if default in cols else cols[0])
            combo.blockSignals(False)
        self._on_mode()

    def _default_y(self, pdd, cols):
        for cand in ("engine_speed_rpm",):
            if cand in cols:
                return cand
        # prefer a non-speed numeric as Y
        for c in cols:
            if c != (pdd.speed_col or ""):
                return c
        return cols[0]

    def _on_mode(self):
        mode = self.mode_combo.currentData()
        needs_z = mode in (maps.MODE_MEAN, maps.MODE_STD)
        self.z_combo.setEnabled(needs_z)
        self._redraw()

    def _redraw(self):
        d = self.state.current_dataset()
        if not d or not d.exists:
            return
        pdd = services.get_prepared(d)
        xcol, ycol = self.x_combo.currentText(), self.y_combo.currentText()
        if not xcol or not ycol:
            return
        mode = self.mode_combo.currentData()
        zcol = self.z_combo.currentText() if mode in (maps.MODE_MEAN, maps.MODE_STD) else None
        res = maps.compute_map(pdd, xcol, ycol, mode, zcol, bins=self.bins.value())
        self.map.set_map(res, xcol, ycol)
        self.msg.setText(f"有効サンプル: {res.n_used:,}")
