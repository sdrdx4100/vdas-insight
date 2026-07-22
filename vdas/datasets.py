"""Dataset registration, loading, and column-role management.

A *dataset* is one preprocessed file (parquet or csv) on disk. DuckDB reads it
lazily; we never copy the bulk data into the metadata DB. Only lightweight
metadata (schema, row count, role mapping) is persisted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from . import db
from .config import (
    ROLE_CATEGORY,
    ROLE_FLAG,
    ROLE_GEAR,
    ROLE_IGNORE,
    ROLE_NUMERIC,
    ROLE_SPEED,
    ROLE_TIME,
)


# --------------------------------------------------------------------------- #
#  Data classes
# --------------------------------------------------------------------------- #
@dataclass
class Dataset:
    id: int
    name: str
    path: str
    format: str
    row_count: int | None = None
    added_at: Any = None
    meta: dict = field(default_factory=dict)

    @property
    def exists(self) -> bool:
        return Path(self.path).exists()


# --------------------------------------------------------------------------- #
#  SQL helpers to read a file through DuckDB
# --------------------------------------------------------------------------- #
def _reader(path: str, fmt: str) -> str:
    """Return a DuckDB table-function expression for the file."""
    p = path.replace("'", "''")
    if fmt == "parquet":
        return f"read_parquet('{p}')"
    return f"read_csv_auto('{p}', SAMPLE_SIZE=-1)"


def detect_format(path: str) -> str:
    return "parquet" if path.lower().endswith(".parquet") else "csv"


# --------------------------------------------------------------------------- #
#  Registration / retrieval
# --------------------------------------------------------------------------- #
def register(path: str, name: str | None = None, meta: dict | None = None) -> Dataset:
    """Register a file as a dataset, auto-detecting column roles."""
    path = str(Path(path).resolve())
    if not Path(path).exists():
        raise FileNotFoundError(path)
    fmt = detect_format(path)
    name = name or Path(path).stem
    con = db.get_con()
    rc = con.execute(f"SELECT count(*) FROM {_reader(path, fmt)}").fetchone()[0]
    row = con.execute(
        "INSERT INTO datasets (name, path, format, row_count, meta) "
        "VALUES (?, ?, ?, ?, ?) RETURNING id",
        [name, path, fmt, rc, db._dumps(meta or {})],
    ).fetchone()
    ds = Dataset(id=row[0], name=name, path=path, format=fmt, row_count=rc, meta=meta or {})
    # Seed roles from auto-detection.
    roles = auto_detect_roles(ds)
    set_roles(ds.id, roles)
    return ds


def list_datasets() -> list[Dataset]:
    con = db.get_con()
    rows = con.execute(
        "SELECT id, name, path, format, row_count, added_at, meta "
        "FROM datasets ORDER BY added_at DESC, id DESC"
    ).fetchall()
    return [
        Dataset(id=r[0], name=r[1], path=r[2], format=r[3], row_count=r[4],
                added_at=r[5], meta=db._loads(r[6]))
        for r in rows
    ]


def get_dataset(dataset_id: int) -> Dataset | None:
    con = db.get_con()
    r = con.execute(
        "SELECT id, name, path, format, row_count, added_at, meta "
        "FROM datasets WHERE id = ?", [dataset_id]
    ).fetchone()
    if not r:
        return None
    return Dataset(id=r[0], name=r[1], path=r[2], format=r[3], row_count=r[4],
                   added_at=r[5], meta=db._loads(r[6]))


def rename(dataset_id: int, name: str) -> None:
    db.get_con().execute("UPDATE datasets SET name = ? WHERE id = ?", [name, dataset_id])


def delete(dataset_id: int) -> None:
    con = db.get_con()
    con.execute("DELETE FROM column_roles WHERE dataset_id = ?", [dataset_id])
    con.execute("DELETE FROM dataset_tags WHERE dataset_id = ?", [dataset_id])
    con.execute("DELETE FROM derived_signals WHERE dataset_id = ?", [dataset_id])
    con.execute("DELETE FROM datasets WHERE id = ?", [dataset_id])


# --------------------------------------------------------------------------- #
#  Schema & data access
# --------------------------------------------------------------------------- #
def schema(ds: Dataset) -> list[tuple[str, str]]:
    """Return [(column_name, duckdb_type), ...]."""
    con = db.get_con()
    rows = con.execute(f"DESCRIBE SELECT * FROM {_reader(ds.path, ds.format)}").fetchall()
    return [(r[0], r[1]) for r in rows]


def columns(ds: Dataset) -> list[str]:
    return [c for c, _ in schema(ds)]


def load(ds: Dataset, columns: list[str] | None = None, limit: int | None = None,
         order_by: str | None = None) -> pd.DataFrame:
    """Load (a subset of) a dataset into a pandas DataFrame via DuckDB."""
    con = db.get_con()
    cols = "*" if not columns else ", ".join(f'"{c}"' for c in columns)
    sql = f"SELECT {cols} FROM {_reader(ds.path, ds.format)}"
    if order_by:
        sql += f' ORDER BY "{order_by}"'
    if limit:
        sql += f" LIMIT {int(limit)}"
    return con.execute(sql).df()


def head(ds: Dataset, n: int = 50) -> pd.DataFrame:
    return load(ds, limit=n)


# --------------------------------------------------------------------------- #
#  Column-role auto-detection
# --------------------------------------------------------------------------- #
_TIME_RX = re.compile(r"(time|timestamp|datetime|^t$|_t$|sec|msec|elapsed|clock)", re.I)
_GEAR_RX = re.compile(r"(gear|shift.?pos|gear.?pos|gearstage|段|変速段)", re.I)
_SPEED_RX = re.compile(r"(veh.?speed|vehicle.?speed|speed|車速|wheel.?speed|spn.?84|kph|km.?h)", re.I)
# Engine/rotational-speed columns look "speedy" but are NOT vehicle speed.
_ENGINE_RX = re.compile(r"(engine|eng[_-]|rpm|回転|tacho|crank)", re.I)
_FLAG_RX = re.compile(r"(flag|status|_sw$|switch|enable|active|_on$|_st$|state|valid|warn|lamp)", re.I)


def _is_numeric_type(t: str) -> bool:
    t = t.upper()
    return any(k in t for k in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "REAL", "HUGEINT"))


def _is_temporal_type(t: str) -> bool:
    t = t.upper()
    return any(k in t for k in ("TIMESTAMP", "DATE", "TIME"))


def auto_detect_roles(ds: Dataset) -> dict[str, str]:
    """Heuristically assign a role to every column.

    Strategy: name patterns first, then cheap value profiling (distinct count,
    min/max) for flag / gear / numeric disambiguation.
    """
    con = db.get_con()
    sch = schema(ds)
    reader = _reader(ds.path, ds.format)
    roles: dict[str, str] = {}

    # Cheap per-column profile for numeric columns: ndistinct, min, max.
    numeric_cols = [c for c, t in sch if _is_numeric_type(t)]
    profile: dict[str, tuple[int, float, float]] = {}
    if numeric_cols:
        parts = []
        for c in numeric_cols:
            parts.append(f'count(DISTINCT "{c}") AS "nd__{c}"')
            parts.append(f'min("{c}") AS "mn__{c}"')
            parts.append(f'max("{c}") AS "mx__{c}"')
        prow = con.execute(f"SELECT {', '.join(parts)} FROM {reader}").fetchdf()
        for c in numeric_cols:
            profile[c] = (
                int(prow[f"nd__{c}"][0] or 0),
                _safe_float(prow[f"mn__{c}"][0]),
                _safe_float(prow[f"mx__{c}"][0]),
            )

    time_assigned = False
    for col, typ in sch:
        role = ROLE_NUMERIC if _is_numeric_type(typ) else ROLE_CATEGORY

        if _is_temporal_type(typ) and not time_assigned:
            role = ROLE_TIME
            time_assigned = True
        elif _TIME_RX.search(col) and _is_numeric_type(typ) and not time_assigned:
            role = ROLE_TIME
            time_assigned = True
        elif _GEAR_RX.search(col):
            role = ROLE_GEAR
        elif _SPEED_RX.search(col) and _is_numeric_type(typ) and not _ENGINE_RX.search(col):
            role = ROLE_SPEED
        elif col in profile:
            nd, mn, mx = profile[col]
            if nd <= 2 and mn >= 0 and mx <= 1:
                role = ROLE_FLAG
            elif _FLAG_RX.search(col) and nd <= 2:
                role = ROLE_FLAG
            elif _GEAR_RX.search(col) or (nd <= 24 and mn >= -3 and mx <= 24 and _looks_gearish(col)):
                role = ROLE_GEAR
        elif _FLAG_RX.search(col):
            role = ROLE_FLAG

        roles[col] = role
    return roles


def _looks_gearish(col: str) -> bool:
    return bool(re.search(r"gear|shift|段", col, re.I))


def _safe_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


# --------------------------------------------------------------------------- #
#  Role persistence
# --------------------------------------------------------------------------- #
def get_roles(dataset_id: int) -> dict[str, str]:
    con = db.get_con()
    rows = con.execute(
        "SELECT column_name, role FROM column_roles WHERE dataset_id = ?", [dataset_id]
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def get_role_params(dataset_id: int) -> dict[str, dict]:
    con = db.get_con()
    rows = con.execute(
        "SELECT column_name, params FROM column_roles WHERE dataset_id = ?", [dataset_id]
    ).fetchall()
    return {r[0]: db._loads(r[1]) for r in rows}


def set_roles(dataset_id: int, roles: dict[str, str],
              params: dict[str, dict] | None = None) -> None:
    con = db.get_con()
    con.execute("DELETE FROM column_roles WHERE dataset_id = ?", [dataset_id])
    params = params or {}
    for col, role in roles.items():
        con.execute(
            "INSERT INTO column_roles (dataset_id, column_name, role, params) "
            "VALUES (?, ?, ?, ?)",
            [dataset_id, col, role, db._dumps(params.get(col, {}))],
        )


def columns_by_role(dataset_id: int, role: str) -> list[str]:
    con = db.get_con()
    rows = con.execute(
        "SELECT column_name FROM column_roles WHERE dataset_id = ? AND role = ?",
        [dataset_id, role],
    ).fetchall()
    return [r[0] for r in rows]


def time_column(dataset_id: int) -> str | None:
    cols = columns_by_role(dataset_id, ROLE_TIME)
    return cols[0] if cols else None


def gear_column(dataset_id: int) -> str | None:
    cols = columns_by_role(dataset_id, ROLE_GEAR)
    return cols[0] if cols else None


def speed_column(dataset_id: int) -> str | None:
    cols = columns_by_role(dataset_id, ROLE_SPEED)
    return cols[0] if cols else None


def flag_columns(dataset_id: int) -> list[str]:
    return columns_by_role(dataset_id, ROLE_FLAG)


def numeric_columns(dataset_id: int) -> list[str]:
    return (columns_by_role(dataset_id, ROLE_NUMERIC)
            + columns_by_role(dataset_id, ROLE_SPEED))
