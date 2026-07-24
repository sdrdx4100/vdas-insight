"""Main application window: docked panels + grouped analysis workspace."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from vdas import __version__
from . import theme
from .panels.dataset_panel import DatasetPanel
from .panels.properties_panel import PropertiesPanel
from .panels.signal_panel import SignalPanel
from .panels.tags_panel import TagsPanel
from .state import AppState
from .views.cohort_map_view import CohortMapView
from .views.cohort_view import CohortView
from .views.flag_view import FlagView
from .views.gear_view import GearView
from .views.map_view import MapView
from .views.measurement_view import MeasurementView
from .views.stats_view import StatsView
from .views.summary_view import SummaryView


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.state = AppState()
        self.setWindowTitle("VDAS-Insight — Vehicle Data Analysis & Statistics")
        self.resize(1560, 940)
        self.setDockOptions(QtWidgets.QMainWindow.AllowNestedDocks
                            | QtWidgets.QMainWindow.AllowTabbedDocks
                            | QtWidgets.QMainWindow.AnimatedDocks)

        self._build_docks()
        self._build_panel_actions()
        self._build_central()
        self._build_menu()
        self._build_toolbar()
        self._build_statusbar()

        self.state.currentDatasetChanged.connect(self._on_dataset_changed)
        self.state.rolesChanged.connect(lambda _id: self._on_dataset_changed(self.state.current_id))
        self.state.datasetsChanged.emit()
        if self.dataset_panel.tree.topLevelItemCount():
            self.dataset_panel.tree.setCurrentItem(
                self.dataset_panel.tree.topLevelItem(0))

    def _dock(self, title, widget, area, obj):
        d = QtWidgets.QDockWidget(title, self)
        d.setObjectName(obj)
        d.setWidget(widget)
        d.setFeatures(QtWidgets.QDockWidget.DockWidgetClosable
                      | QtWidgets.QDockWidget.DockWidgetMovable
                      | QtWidgets.QDockWidget.DockWidgetFloatable)
        self.addDockWidget(area, d)
        return d

    def _build_docks(self):
        self.dataset_panel = DatasetPanel(self.state)
        self.signal_panel = SignalPanel(self.state)
        self.properties_panel = PropertiesPanel(self.state)
        self.tags_panel = TagsPanel(self.state)

        self.dock_data = self._dock("データセット", self.dataset_panel,
                                    QtCore.Qt.LeftDockWidgetArea, "dockData")
        self.dock_sig = self._dock("信号", self.signal_panel,
                                   QtCore.Qt.LeftDockWidgetArea, "dockSignals")
        self.splitDockWidget(self.dock_data, self.dock_sig, QtCore.Qt.Vertical)

        self.dock_props = self._dock("役割 / プロパティ", self.properties_panel,
                                     QtCore.Qt.RightDockWidgetArea, "dockProps")
        self.dock_tags = self._dock("タグ / コホート", self.tags_panel,
                                    QtCore.Qt.RightDockWidgetArea, "dockTags")
        self.splitDockWidget(self.dock_props, self.dock_tags, QtCore.Qt.Vertical)

        self.resizeDocks([self.dock_data, self.dock_props], [300, 320],
                         QtCore.Qt.Horizontal)

    def _build_panel_actions(self):
        self.act_left_panels = QtGui.QAction("左パネル", self)
        self.act_left_panels.setCheckable(True)
        self.act_left_panels.setChecked(True)
        self.act_left_panels.setShortcut("Ctrl+Shift+L")
        self.act_left_panels.setToolTip(
            "データセットと信号パネルをまとめて表示 / 非表示")
        self.act_left_panels.toggled.connect(
            lambda visible: self._set_side_visible("left", visible))

        self.act_right_panels = QtGui.QAction("右パネル", self)
        self.act_right_panels.setCheckable(True)
        self.act_right_panels.setChecked(True)
        self.act_right_panels.setShortcut("Ctrl+Shift+R")
        self.act_right_panels.setToolTip(
            "役割 / プロパティとタグ / コホートをまとめて表示 / 非表示")
        self.act_right_panels.toggled.connect(
            lambda visible: self._set_side_visible("right", visible))

        for dock in self._side_docks("left") + self._side_docks("right"):
            dock.visibilityChanged.connect(
                lambda _visible: self._sync_panel_actions())
        self._sync_panel_actions()

    def _side_docks(self, side: str):
        if side == "left":
            return (self.dock_data, self.dock_sig)
        if side == "right":
            return (self.dock_props, self.dock_tags)
        raise ValueError(f"unknown dock side: {side}")

    def _set_side_visible(self, side: str, visible: bool):
        for dock in self._side_docks(side):
            dock.setVisible(visible)
        self._sync_panel_actions()

    def _sync_panel_actions(self):
        for side, action in (("left", self.act_left_panels),
                             ("right", self.act_right_panels)):
            visible = any(not dock.isHidden() for dock in self._side_docks(side))
            previous = action.blockSignals(True)
            action.setChecked(visible)
            action.blockSignals(previous)

    def _build_central(self):
        """Group the growing view list into single-data and cohort workflows."""
        self.workspace = QtWidgets.QTabWidget()
        self.workspace.setDocumentMode(True)
        self.workspace.setTabPosition(QtWidgets.QTabWidget.North)

        self.single_tabs = QtWidgets.QTabWidget()
        self.single_tabs.setDocumentMode(True)
        self.cohort_tabs = QtWidgets.QTabWidget()
        self.cohort_tabs.setDocumentMode(True)

        self.measurement = MeasurementView(self.state)
        self.measurement.set_cursor_callback(self._set_cursor_text)
        self.gears = GearView(self.state)
        self.flags = FlagView(self.state)
        self.stats = StatsView(self.state)
        self.map = MapView(self.state)
        self.cohort = CohortView(self.state)
        self.cohort_map = CohortMapView(self.state)
        self.summary = SummaryView(self.state)

        self.single_tabs.addTab(self.measurement, "📉 時系列")
        self.single_tabs.addTab(self.stats, "📊 統計")
        self.single_tabs.addTab(self.gears, "⚙️ ギア段")
        self.single_tabs.addTab(self.flags, "🚩 フラグ")
        self.single_tabs.addTab(self.map, "🗺 2Dマップ")

        self.cohort_tabs.addTab(self.cohort, "🧩 比較")
        self.cohort_tabs.addTab(self.cohort_map, "🗺 マップ")
        self.cohort_tabs.addTab(self.summary, "📋 サマリ")

        self.workspace.addTab(self.single_tabs, "単体分析")
        self.workspace.addTab(self.cohort_tabs, "コホート分析")
        self.setCentralWidget(self.workspace)

        # Compatibility alias for integrations that only need the active workspace.
        self.tabs = self.workspace

    def _show_cohort_comparison(self):
        self.workspace.setCurrentWidget(self.cohort_tabs)
        self.cohort_tabs.setCurrentWidget(self.cohort)

    def _reset_layout(self):
        for dock in (self.dock_data, self.dock_sig, self.dock_props, self.dock_tags):
            dock.setVisible(True)
            dock.setFloating(False)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.dock_data)
        self.splitDockWidget(self.dock_data, self.dock_sig, QtCore.Qt.Vertical)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.dock_props)
        self.splitDockWidget(self.dock_props, self.dock_tags, QtCore.Qt.Vertical)
        self.resizeDocks([self.dock_data, self.dock_props], [300, 320],
                         QtCore.Qt.Horizontal)
        self._sync_panel_actions()

    def _build_menu(self):
        mb = self.menuBar()
        m_file = mb.addMenu("ファイル(&F)")
        act_reg = m_file.addAction("データセットを登録…")
        act_reg.triggered.connect(self.dataset_panel.register_dialog)
        act_manage = m_file.addAction("データ管理（一括タグ・削除）…")
        act_manage.triggered.connect(self._open_manage)
        m_file.addSeparator()
        act_quit = m_file.addAction("終了")
        act_quit.triggered.connect(self.close)

        m_view = mb.addMenu("表示(&V)")
        m_view.addAction(self.act_left_panels)
        m_view.addAction(self.act_right_panels)
        m_individual = m_view.addMenu("個別パネル")
        for dock in (self.dock_data, self.dock_sig, self.dock_props, self.dock_tags):
            m_individual.addAction(dock.toggleViewAction())
        m_view.addSeparator()
        m_view.addAction("レイアウトを初期状態に戻す", self._reset_layout)

        m_help = mb.addMenu("ヘルプ(&H)")
        m_help.addAction("VDAS-Insight について", self._about)

    def _build_toolbar(self):
        tb = QtWidgets.QToolBar("main")
        tb.setObjectName("mainToolbar")
        tb.setMovable(False)
        self.addToolBar(tb)
        a_reg = tb.addAction("＋ 登録")
        a_reg.triggered.connect(self.dataset_panel.register_dialog)
        a_auto = tb.addAction("役割を自動推定")
        a_auto.triggered.connect(self.properties_panel._autodetect)
        a_manage = tb.addAction("🗂 データ管理")
        a_manage.triggered.connect(self._open_manage)
        tb.addSeparator()
        a_cmp = tb.addAction("コホート比較へ")
        a_cmp.triggered.connect(self._show_cohort_comparison)
        tb.addSeparator()
        tb.addAction(self.act_left_panels)
        tb.addAction(self.act_right_panels)

    def _open_manage(self):
        from .panels.manage_dialog import ManageDialog
        ManageDialog(self.state, self).exec()

    def _build_statusbar(self):
        sb = self.statusBar()
        self.lbl_dataset = QtWidgets.QLabel("データセット未選択")
        self.lbl_cursor = QtWidgets.QLabel("")
        self.lbl_cursor.setStyleSheet(f"color: {theme.INK};")
        sb.addWidget(self.lbl_dataset)
        sb.addPermanentWidget(self.lbl_cursor)

    def _on_dataset_changed(self, _id):
        d = self.state.current_dataset()
        if d:
            self.lbl_dataset.setText(f"▶ {d.name}   ({d.row_count:,} 行 · {d.format})")
        else:
            self.lbl_dataset.setText("データセット未選択")
        for v in (self.measurement, self.gears, self.flags, self.stats, self.map):
            try:
                v.rebuild()
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                self.statusBar().showMessage(
                    f"⚠ {type(v).__name__} の更新でエラー: {e}", 8000)

    def _set_cursor_text(self, text: str):
        self.lbl_cursor.setText(text)

    def _about(self):
        QtWidgets.QMessageBox.about(
            self, "VDAS-Insight",
            f"<b>VDAS-Insight</b> v{__version__}<br>"
            "Vehicle Data Analysis &amp; Statistics<br><br>"
            "大規模車両計測データ（J1939 等）の可視化・統計・コホート比較。<br>"
            "PySide6 + pyqtgraph + DuckDB。")