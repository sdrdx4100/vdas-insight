"""DuckDB-backed metadata store.

DuckDB doubles as (1) the analytics engine that reads parquet/csv directly and
(2) the persistent store for datasets, column-role mappings, and tags.

The connection is process-local. Streamlit reruns the script per interaction,
so we cache a single connection via ``get_con``.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

import duckdb

from .config import DB_PATH

_LOCK = threading.Lock()
_CON: duckdb.DuckDBPyConnection | None = None


SCHEMA = """
CREATE SEQUENCE IF NOT EXISTS seq_dataset_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_tag_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_derived_id START 1;

CREATE TABLE IF NOT EXISTS datasets (
    id           BIGINT PRIMARY KEY DEFAULT nextval('seq_dataset_id'),
    name         VARCHAR NOT NULL,
    path         VARCHAR NOT NULL,
    format       VARCHAR NOT NULL,          -- 'parquet' | 'csv'
    row_count    BIGINT,
    added_at     TIMESTAMP DEFAULT now(),
    meta         JSON                       -- free-form (source, notes, ...)
);

CREATE TABLE IF NOT EXISTS column_roles (
    dataset_id   BIGINT NOT NULL,
    column_name  VARCHAR NOT NULL,
    role         VARCHAR NOT NULL,
    params       JSON,                      -- role-specific (e.g. time unit)
    PRIMARY KEY (dataset_id, column_name)
);

CREATE TABLE IF NOT EXISTS tags (
    id           BIGINT PRIMARY KEY DEFAULT nextval('seq_tag_id'),
    name         VARCHAR NOT NULL UNIQUE,
    color        VARCHAR,
    description  VARCHAR,
    category     VARCHAR,                   -- optional dimension (メーカー / 走行条件…)
    created_at   TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dataset_tags (
    dataset_id   BIGINT NOT NULL,
    tag_id       BIGINT NOT NULL,
    PRIMARY KEY (dataset_id, tag_id)
);

CREATE TABLE IF NOT EXISTS derived_signals (
    id           BIGINT PRIMARY KEY DEFAULT nextval('seq_derived_id'),
    dataset_id   BIGINT NOT NULL,
    name         VARCHAR NOT NULL,        -- output signal name (unique per dataset)
    kind         VARCHAR NOT NULL,        -- registry key (see vdas.derived)
    source       VARCHAR,                 -- source column (file col or another derived)
    params       JSON,                    -- kind-specific (window_s, ...)
    ordinal      BIGINT DEFAULT 0         -- evaluation order
);
"""


def get_con() -> duckdb.DuckDBPyConnection:
    """Return the shared DuckDB connection, creating & migrating it once."""
    global _CON
    with _LOCK:
        if _CON is None:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            con = duckdb.connect(str(DB_PATH))
            con.execute(SCHEMA)
            _migrate(con)
            _CON = con
        return _CON


def _migrate(con: duckdb.DuckDBPyConnection) -> None:
    """Lightweight in-place migrations for DBs created by older versions."""
    cols = {r[1] for r in con.execute("PRAGMA table_info('tags')").fetchall()}
    if "category" not in cols:
        con.execute("ALTER TABLE tags ADD COLUMN category VARCHAR")


def now() -> datetime:
    return datetime.now(timezone.utc)


def _dumps(obj: Any) -> str | None:
    return None if obj is None else json.dumps(obj, ensure_ascii=False, default=str)


def _loads(txt: Any) -> Any:
    if txt in (None, ""):
        return {}
    if isinstance(txt, (dict, list)):
        return txt
    try:
        return json.loads(txt)
    except (TypeError, json.JSONDecodeError):
        return {}
