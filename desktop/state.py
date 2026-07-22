"""Application state & signal bus shared by panels and views."""
from __future__ import annotations

from PySide6 import QtCore

from vdas import datasets as ds_mod
from vdas.datasets import Dataset


class AppState(QtCore.QObject):
    # Emitted when the dataset catalogue changes (added / removed / renamed).
    datasetsChanged = QtCore.Signal()
    # Emitted when the active dataset changes; carries dataset id (or -1).
    currentDatasetChanged = QtCore.Signal(int)
    # Emitted when the user changes which signals are plotted.
    plotSelectionChanged = QtCore.Signal(list)   # list[str]
    # Emitted when tags / memberships change.
    tagsChanged = QtCore.Signal()
    # Emitted when a dataset's roles change (id).
    rolesChanged = QtCore.Signal(int)

    def __init__(self):
        super().__init__()
        self._current_id: int = -1
        self._plot_signals: list[str] = []

    @property
    def current_id(self) -> int:
        return self._current_id

    def current_dataset(self) -> Dataset | None:
        if self._current_id < 0:
            return None
        return ds_mod.get_dataset(self._current_id)

    def set_current(self, dataset_id: int) -> None:
        if dataset_id != self._current_id:
            self._current_id = dataset_id
            self._plot_signals = []
            self.currentDatasetChanged.emit(dataset_id)

    @property
    def plot_signals(self) -> list[str]:
        return list(self._plot_signals)

    def set_plot_signals(self, names: list[str]) -> None:
        self._plot_signals = list(names)
        self.plotSelectionChanged.emit(self._plot_signals)
