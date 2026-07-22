"""Global configuration and constants for VDAS-Insight."""
from __future__ import annotations

import os
from pathlib import Path

# --- Paths ------------------------------------------------------------------
# Root of the project (repo root). Everything user-generated lives under DATA_DIR.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("VDAS_DATA_DIR", PROJECT_ROOT / "data")).resolve()
DB_PATH = Path(os.environ.get("VDAS_DB_PATH", DATA_DIR / "vdas.duckdb")).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# --- Column roles -----------------------------------------------------------
# A "role" tells the analysis engine how to interpret a column regardless of
# its raw name. This is what lets the platform stay schema-agnostic.
ROLE_TIME = "time"          # timestamp / seconds axis
ROLE_GEAR = "gear"          # discrete gear stage (used for shift detection)
ROLE_FLAG = "flag"          # 0/1 (or boolean) state signal
ROLE_SPEED = "speed"        # vehicle speed (km/h) — enables per-km metrics
ROLE_NUMERIC = "numeric"    # generic continuous signal
ROLE_CATEGORY = "category"  # discrete categorical signal (mode, state name...)
ROLE_IGNORE = "ignore"      # excluded from analysis

ROLES = [
    ROLE_TIME,
    ROLE_GEAR,
    ROLE_FLAG,
    ROLE_SPEED,
    ROLE_NUMERIC,
    ROLE_CATEGORY,
    ROLE_IGNORE,
]

ROLE_LABELS = {
    ROLE_TIME: "⏱ Time",
    ROLE_GEAR: "⚙️ Gear",
    ROLE_FLAG: "🚩 Flag (0/1)",
    ROLE_SPEED: "🏁 Speed",
    ROLE_NUMERIC: "📈 Numeric",
    ROLE_CATEGORY: "🔤 Category",
    ROLE_IGNORE: "🚫 Ignore",
}

# --- Data-viz palette (validated categorical palette, dataviz skill) ---------
# Fixed order, assigned by slot — never cycled. Light-mode steps.
PALETTE = [
    "#2a78d6",  # blue
    "#eb6834",  # orange
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#e87ba4",  # magenta
    "#008300",  # green
    "#4a3aa7",  # violet
    "#e34948",  # red
]

# Sequential single-hue ramp (blue), light->dark, for magnitude / heatmaps.
SEQUENTIAL = [
    "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5",
    "#256abf", "#184f95", "#104281", "#0d366b",
]

STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

# Preset colors offered when creating a tag.
TAG_COLORS = PALETTE
