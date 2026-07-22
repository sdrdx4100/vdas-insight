"""Small reusable Qt widgets: metric tiles, headers, a metric strip."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from .. import theme


class MetricTile(QtWidgets.QFrame):
    """A compact KPI tile: large value + caption + optional unit."""

    def __init__(self, label: str, value: str = "—", unit: str = ""):
        super().__init__()
        self.setStyleSheet(
            f"QFrame {{ background: {theme.BG_PANEL}; border: 1px solid {theme.BORDER};"
            f" border-radius: 6px; }}")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        self._label = QtWidgets.QLabel(label.upper())
        self._label.setObjectName("metricLabel")
        self._value = QtWidgets.QLabel(value)
        self._value.setObjectName("metricValue")
        self._unit = unit
        lay.addWidget(self._label)
        lay.addWidget(self._value)

    def set_value(self, value: str, unit: str | None = None) -> None:
        u = self._unit if unit is None else unit
        self._value.setText(f"{value} {u}".strip())


class MetricStrip(QtWidgets.QWidget):
    """A horizontal row of MetricTiles, rebuildable in place."""

    def __init__(self):
        super().__init__()
        self._lay = QtWidgets.QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(8)

    def set_metrics(self, items: list[tuple[str, str, str]]) -> None:
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        for label, value, unit in items:
            self._lay.addWidget(MetricTile(label, value, unit))
        self._lay.addStretch(1)


def section_label(text: str) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text)
    lbl.setObjectName("h2")
    lbl.setContentsMargins(0, 6, 0, 2)
    return lbl


def hline() -> QtWidgets.QFrame:
    line = QtWidgets.QFrame()
    line.setFrameShape(QtWidgets.QFrame.HLine)
    line.setStyleSheet(f"color: {theme.BORDER};")
    return line
