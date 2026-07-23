"""Named condition presets — save & reuse aggregation conditions.

A preset stores a list of :class:`vdas.analysis.conditions.Predicate` under a
name (e.g. "車速≤70"), persisted in DuckDB, so common gated-aggregation
conditions can be reapplied across cohorts and tabs.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import db
from .analysis.conditions import Predicate


def serialize(predicates: list[Predicate]) -> list[dict]:
    return [{"signal": p.signal, "op": p.op, "value": p.value, "value2": p.value2}
            for p in predicates]


def deserialize(spec) -> list[Predicate]:
    spec = spec or []
    out = []
    for d in spec:
        try:
            out.append(Predicate(d["signal"], d["op"],
                                 float(d.get("value", 0.0)), float(d.get("value2", 0.0))))
        except (KeyError, TypeError, ValueError):
            continue
    return out


@dataclass
class Preset:
    id: int
    name: str
    predicates: list[Predicate]


def save(name: str, predicates: list[Predicate]) -> Preset:
    """Create or update a preset by name."""
    con = db.get_con()
    name = name.strip()
    spec = db._dumps(serialize(predicates))
    existing = con.execute("SELECT id FROM condition_presets WHERE name = ?",
                           [name]).fetchone()
    if existing:
        con.execute("UPDATE condition_presets SET spec = ? WHERE id = ?",
                    [spec, existing[0]])
        pid = existing[0]
    else:
        pid = con.execute(
            "INSERT INTO condition_presets (name, spec) VALUES (?, ?) RETURNING id",
            [name, spec]).fetchone()[0]
    return Preset(pid, name, list(predicates))


def list_presets() -> list[Preset]:
    rows = db.get_con().execute(
        "SELECT id, name, spec FROM condition_presets ORDER BY name").fetchall()
    return [Preset(r[0], r[1], deserialize(db._loads(r[2]))) for r in rows]


def delete(preset_id: int) -> None:
    db.get_con().execute("DELETE FROM condition_presets WHERE id = ?", [preset_id])
