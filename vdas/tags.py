"""Tag management: create cohorts of datasets and query membership.

Tags are the mechanism for treating a *set* of datasets as a single statistical
population. A dataset may belong to many tags; a tag may contain many datasets.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import db
from .config import TAG_COLORS


@dataclass
class Tag:
    id: int
    name: str
    color: str | None = None
    description: str | None = None
    created_at: Any = None
    dataset_count: int = 0


def create(name: str, color: str | None = None, description: str | None = None) -> Tag:
    con = db.get_con()
    color = color or TAG_COLORS[0]
    row = con.execute(
        "INSERT INTO tags (name, color, description) VALUES (?, ?, ?) RETURNING id",
        [name.strip(), color, description],
    ).fetchone()
    return Tag(id=row[0], name=name.strip(), color=color, description=description)


def list_tags() -> list[Tag]:
    con = db.get_con()
    rows = con.execute(
        """
        SELECT t.id, t.name, t.color, t.description, t.created_at,
               count(dt.dataset_id) AS n
        FROM tags t
        LEFT JOIN dataset_tags dt ON dt.tag_id = t.id
        GROUP BY t.id, t.name, t.color, t.description, t.created_at
        ORDER BY t.name
        """
    ).fetchall()
    return [Tag(id=r[0], name=r[1], color=r[2], description=r[3],
               created_at=r[4], dataset_count=r[5]) for r in rows]


def get_tag(tag_id: int) -> Tag | None:
    for t in list_tags():
        if t.id == tag_id:
            return t
    return None


def update(tag_id: int, name: str | None = None, color: str | None = None,
           description: str | None = None) -> None:
    con = db.get_con()
    if name is not None:
        con.execute("UPDATE tags SET name = ? WHERE id = ?", [name.strip(), tag_id])
    if color is not None:
        con.execute("UPDATE tags SET color = ? WHERE id = ?", [color, tag_id])
    if description is not None:
        con.execute("UPDATE tags SET description = ? WHERE id = ?", [description, tag_id])


def delete(tag_id: int) -> None:
    con = db.get_con()
    con.execute("DELETE FROM dataset_tags WHERE tag_id = ?", [tag_id])
    con.execute("DELETE FROM tags WHERE id = ?", [tag_id])


# --------------------------------------------------------------------------- #
#  Membership
# --------------------------------------------------------------------------- #
def assign(dataset_id: int, tag_id: int) -> None:
    db.get_con().execute(
        "INSERT INTO dataset_tags (dataset_id, tag_id) VALUES (?, ?) "
        "ON CONFLICT DO NOTHING",
        [dataset_id, tag_id],
    )


def unassign(dataset_id: int, tag_id: int) -> None:
    db.get_con().execute(
        "DELETE FROM dataset_tags WHERE dataset_id = ? AND tag_id = ?",
        [dataset_id, tag_id],
    )


def set_dataset_tags(dataset_id: int, tag_ids: list[int]) -> None:
    con = db.get_con()
    con.execute("DELETE FROM dataset_tags WHERE dataset_id = ?", [dataset_id])
    for tid in tag_ids:
        assign(dataset_id, tid)


def dataset_ids_for_tag(tag_id: int) -> list[int]:
    rows = db.get_con().execute(
        "SELECT dataset_id FROM dataset_tags WHERE tag_id = ? ORDER BY dataset_id",
        [tag_id],
    ).fetchall()
    return [r[0] for r in rows]


def tag_ids_for_dataset(dataset_id: int) -> list[int]:
    rows = db.get_con().execute(
        "SELECT tag_id FROM dataset_tags WHERE dataset_id = ?", [dataset_id]
    ).fetchall()
    return [r[0] for r in rows]
