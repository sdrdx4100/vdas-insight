"""Headless smoke tests for the grouped desktop workspace.

Runs Qt with the ``offscreen`` platform so it works in CI. Skipped entirely if
PySide6 (or its platform plugin) is unavailable.
"""
from __future__ import annotations

import glob
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from vdas.config import PROJECT_ROOT  # noqa: E402


@pytest.fixture(scope="module")
def app():
    from PySide6 import QtWidgets
    from desktop import theme
    qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    theme.apply_theme(qt_app)
    return qt_app


def _load_samples():
    from vdas import datasets, tags
    paths = sorted(glob.glob(str(PROJECT_ROOT / "sample_data" / "*.parquet")))
    if not paths:
        pytest.skip("no sample data present")
    existing = {d.path for d in datasets.list_datasets()}
    for path in paths:
        if os.path.abspath(path) not in existing:
            datasets.register(path)
    tag_id = next((t.id for t in tags.list_tags() if t.name == "all"), None) \
        or tags.create("all").id
    for dataset in datasets.list_datasets():
        tags.assign(dataset.id, tag_id)


def _switch_all_tabs(tab_widget, app):
    for index in range(tab_widget.count()):
        tab_widget.setCurrentIndex(index)
        app.processEvents()


def test_mainwindow_builds_and_switches_all_nested_tabs(app):
    _load_samples()
    from desktop.main_window import MainWindow

    win = MainWindow()
    win.resize(1400, 900)
    win.show()
    app.processEvents()

    assert win.state.current_id != -1

    win.workspace.setCurrentWidget(win.single_tabs)
    _switch_all_tabs(win.single_tabs, app)
    assert win.single_tabs.count() == 5

    win.workspace.setCurrentWidget(win.cohort_tabs)
    _switch_all_tabs(win.cohort_tabs, app)
    assert win.cohort_tabs.count() == 3

    win.cohort_tabs.setCurrentWidget(win.cohort)
    win.cohort.rebuild()
    app.processEvents()
    assert win.cohort._df is not None and not win.cohort._df.empty

    win.close()


def test_new_analysis_controls_are_operable(app):
    _load_samples()
    from desktop.main_window import MainWindow

    win = MainWindow()
    win.show()
    app.processEvents()

    condition = win.cohort.cond
    assert condition.details.isHidden()
    condition.btn_toggle.setChecked(True)
    app.processEvents()
    assert not condition.details.isHidden()
    condition.btn_toggle.setChecked(False)
    app.processEvents()
    assert condition.details.isHidden()

    win.summary.metric_search.setText("ギア")
    app.processEvents()
    assert win.summary.metric_list.count() > 0
    win.summary.metric_search.clear()

    win.close()


def test_side_panels_can_be_collapsed_and_restored(app):
    _load_samples()
    from desktop.main_window import MainWindow

    win = MainWindow()
    win.show()
    app.processEvents()

    left = (win.dock_data, win.dock_sig)
    right = (win.dock_props, win.dock_tags)
    assert all(not dock.isHidden() for dock in left + right)
    assert win.act_left_panels.isChecked()
    assert win.act_right_panels.isChecked()

    win.act_right_panels.setChecked(False)
    app.processEvents()
    assert all(dock.isHidden() for dock in right)
    assert all(not dock.isHidden() for dock in left)

    win.act_left_panels.setChecked(False)
    app.processEvents()
    assert all(dock.isHidden() for dock in left)

    win.act_right_panels.setChecked(True)
    app.processEvents()
    assert all(not dock.isHidden() for dock in right)
    assert all(dock.isHidden() for dock in left)

    win._reset_layout()
    app.processEvents()
    assert all(not dock.isHidden() for dock in left + right)
    assert win.act_left_panels.isChecked()
    assert win.act_right_panels.isChecked()

    win.close()