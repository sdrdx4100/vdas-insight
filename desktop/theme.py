"""Dark instrument theme (INCA/CANape-inspired) for the Qt app + pyqtgraph.

One place defines the palette, the Qt stylesheet, and the pyqtgraph defaults so
the whole app reads as a single measurement instrument.
"""
from __future__ import annotations

from PySide6 import QtGui, QtWidgets
import pyqtgraph as pg

# --- Core surfaces / ink ----------------------------------------------------
BG_WINDOW = "#17181c"   # outermost window
BG_PANEL = "#202329"    # docks / toolbars
BG_BASE = "#14161a"     # inputs, trees, tables
BG_PLOT = "#121316"     # plot canvas
BG_ELEV = "#282c34"     # hovered / selected rows
INK = "#c9ccd1"         # primary text
INK_DIM = "#8b9099"     # secondary text
INK_FAINT = "#5b616b"   # axes / muted
BORDER = "#2c2f36"
ACCENT = "#3987e5"      # selection / primary
GRID = "#25272d"

# --- Categorical palette (dataviz dark-mode steps, fixed order) -------------
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500",
          "#d55181", "#008300", "#9085e9", "#e66767"]

STATUS = {"good": "#0ca30c", "warning": "#fab219",
          "serious": "#ec835a", "critical": "#d03b3b"}

# Role → accent color (used for badges in the signal tree).
ROLE_COLORS = {
    "time": "#8b9099",
    "gear": "#c98500",
    "flag": "#d95926",
    "speed": "#3987e5",
    "numeric": "#199e70",
    "category": "#9085e9",
    "ignore": "#5b616b",
}


def series_color(i: int) -> str:
    return SERIES[i % len(SERIES)]


def apply_theme(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")
    pal = QtGui.QPalette()
    c = QtGui.QColor
    pal.setColor(QtGui.QPalette.Window, c(BG_WINDOW))
    pal.setColor(QtGui.QPalette.WindowText, c(INK))
    pal.setColor(QtGui.QPalette.Base, c(BG_BASE))
    pal.setColor(QtGui.QPalette.AlternateBase, c(BG_PANEL))
    pal.setColor(QtGui.QPalette.Text, c(INK))
    pal.setColor(QtGui.QPalette.Button, c(BG_PANEL))
    pal.setColor(QtGui.QPalette.ButtonText, c(INK))
    pal.setColor(QtGui.QPalette.ToolTipBase, c(BG_ELEV))
    pal.setColor(QtGui.QPalette.ToolTipText, c(INK))
    pal.setColor(QtGui.QPalette.Highlight, c(ACCENT))
    pal.setColor(QtGui.QPalette.HighlightedText, c("#ffffff"))
    pal.setColor(QtGui.QPalette.Link, c(ACCENT))
    pal.setColor(QtGui.QPalette.PlaceholderText, c(INK_FAINT))
    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, c(INK_FAINT))
    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, c(INK_FAINT))
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)

    # pyqtgraph global defaults
    pg.setConfigOptions(antialias=True, background=BG_PLOT, foreground=INK_DIM,
                        useOpenGL=False)


STYLESHEET = f"""
* {{ font-family: "Segoe UI", "Noto Sans CJK JP", system-ui, sans-serif; font-size: 12px; }}
QMainWindow, QWidget {{ background: {BG_WINDOW}; color: {INK}; }}

QToolBar {{ background: {BG_PANEL}; border: 0; border-bottom: 1px solid {BORDER}; spacing: 4px; padding: 3px; }}
QToolBar QToolButton {{ padding: 4px 8px; border-radius: 4px; color: {INK}; }}
QToolBar QToolButton:hover {{ background: {BG_ELEV}; }}
QToolBar QToolButton:pressed {{ background: {ACCENT}; }}

QMenuBar {{ background: {BG_PANEL}; color: {INK}; border-bottom: 1px solid {BORDER}; }}
QMenuBar::item:selected {{ background: {BG_ELEV}; }}
QMenu {{ background: {BG_PANEL}; color: {INK}; border: 1px solid {BORDER}; }}
QMenu::item:selected {{ background: {ACCENT}; color: #fff; }}

QDockWidget {{ color: {INK_DIM}; titlebar-close-icon: none; titlebar-normal-icon: none; }}
QDockWidget::title {{ background: {BG_PANEL}; padding: 5px 8px; border-bottom: 1px solid {BORDER};
                      text-transform: uppercase; letter-spacing: 1px; font-size: 11px; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; background: {BG_WINDOW}; }}
QTabBar::tab {{ background: {BG_PANEL}; color: {INK_DIM}; padding: 7px 16px; border: 1px solid {BORDER};
                border-bottom: 0; }}
QTabBar::tab:selected {{ background: {BG_WINDOW}; color: {INK}; border-top: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {INK}; }}

QTreeView, QListView, QTableView, QTableWidget {{ background: {BG_BASE}; alternate-background-color: {BG_PANEL};
    border: 1px solid {BORDER}; selection-background-color: {ACCENT}; selection-color: #fff;
    gridline-color: {GRID}; outline: 0; }}
QTreeView::item, QListView::item {{ padding: 3px; }}
QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {{ background: {BG_ELEV}; }}
QHeaderView::section {{ background: {BG_PANEL}; color: {INK_DIM}; padding: 5px; border: 0;
    border-right: 1px solid {BORDER}; border-bottom: 1px solid {BORDER}; }}

QPushButton {{ background: {BG_ELEV}; color: {INK}; border: 1px solid {BORDER}; border-radius: 4px;
    padding: 5px 12px; }}
QPushButton:hover {{ background: #313640; }}
QPushButton:pressed {{ background: {ACCENT}; color: #fff; }}
QPushButton#primary {{ background: {ACCENT}; color: #fff; border: 0; }}
QPushButton#primary:hover {{ background: #4a94ef; }}

QComboBox, QLineEdit, QSpinBox {{ background: {BG_BASE}; color: {INK}; border: 1px solid {BORDER};
    border-radius: 4px; padding: 4px 8px; }}
QComboBox:hover, QLineEdit:hover {{ border-color: {INK_FAINT}; }}
QComboBox QAbstractItemView {{ background: {BG_PANEL}; color: {INK}; selection-background-color: {ACCENT}; }}

QCheckBox {{ spacing: 6px; }}
QLabel#h1 {{ font-size: 17px; font-weight: 600; color: {INK}; }}
QLabel#h2 {{ font-size: 13px; font-weight: 600; color: {INK}; }}
QLabel#dim {{ color: {INK_DIM}; }}
QLabel#metricValue {{ font-size: 20px; font-weight: 600; color: {INK}; }}
QLabel#metricLabel {{ color: {INK_DIM}; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }}

QStatusBar {{ background: {BG_PANEL}; color: {INK_DIM}; border-top: 1px solid {BORDER}; }}
QStatusBar::item {{ border: 0; }}
QSplitter::handle {{ background: {BORDER}; }}
QScrollBar:vertical {{ background: {BG_WINDOW}; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 6px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {INK_FAINT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: {BG_WINDOW}; height: 12px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 6px; min-width: 30px; }}
"""
