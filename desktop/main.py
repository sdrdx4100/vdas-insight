"""VDAS-Insight desktop entry point.

Run with:  python -m desktop.main    (or ./run.sh)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the repo root importable when launched as a script.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from PySide6 import QtWidgets  # noqa: E402

from desktop import theme  # noqa: E402
from desktop.main_window import MainWindow  # noqa: E402


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("VDAS-Insight")
    app.setOrganizationName("VDAS")
    theme.apply_theme(app)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
