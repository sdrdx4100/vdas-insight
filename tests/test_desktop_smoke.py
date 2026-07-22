"""Headless smoke test: the desktop app builds and switches views without error.

Runs Qt with the 'offscreen' platform so it works in CI. Skipped entirely if
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
    a = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    theme.apply_theme(a)
    return a


def _load_samples():
    from vdas import datasets, tags
    paths = sorted(glob.glob(str(PROJECT_ROOT / "sample_data" / "*.parquet")))
    if not paths:
        pytest.skip("no sample data present")
    existing = {d.path for d in datasets.list_datasets()}
    for p in paths:
        if os.path.abspath(p) not in existing:
            datasets.register(p)
    tid = next((t.id for t in tags.list_tags() if t.name == "all"), None) \
        or tags.create("all").id
    for d in datasets.list_datasets():
        tags.assign(d.id, tid)


def test_mainwindow_builds_and_switches_tabs(app):
    _load_samples()
    from desktop.main_window import MainWindow

    win = MainWindow()
    win.resize(1400, 900)
    # A dataset should auto-select; every tab must rebuild without raising.
    assert win.state.current_id != -1
    for i in range(win.tabs.count()):
        win.tabs.setCurrentIndex(i)
        app.processEvents()
    # Cohort view should have produced a comparison frame.
    win.tabs.setCurrentWidget(win.cohort)
    win.cohort.rebuild()
    app.processEvents()
    assert win.cohort._df is not None and not win.cohort._df.empty
    win.close()
