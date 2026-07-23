"""Tag management: create cohorts of datasets and query membership.

Tags are the mechanism for treating a *set* of datasets as a single statistical
population. A dataset may belong to many tags; a tag may contain many datasets.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import db
from .config import TAG_COLORS


#: Sentinel used to distinguish "keep the value" from "set to NULL" in update().
_UNSET = object()


@dataclass
class Tag:
    id: int
    name: str
    color: str | None = None
    description: str | None = None
    category: str | None = None
    created_at: Any = None
    dataset_count: int = 0


def create(name: str, color: str | None = None, description: str | None = None,
           category: str | None = None) -> Tag:
    con = db.get_con()
    color = color or TAG_COLORS[0]
    category = (category or "").strip() or None
    row = con.execute(
        "INSERT INTO tags (name, color, description, category) "
        "VALUES (?, ?, ?, ?) RETURNING id",
        [name.strip(), color, description, category],
    ).fetchone()
    return Tag(id=row[0], name=name.strip(), color=color,
               description=description, category=category)


def list_tags() -> list[Tag]:
    con = db.get_con()
    rows = con.execute(
        """
        SELECT t.id, t.name, t.color, t.description, t.category, t.created_at,
               count(dt.dataset_id) AS n
        FROM tags t
        LEFT JOIN dataset_tags dt ON dt.tag_id = t.id
        GROUP BY t.id, t.name, t.color, t.description, t.category, t.created_at
        ORDER BY t.category NULLS LAST, t.name
        """
    ).fetchall()
    return [Tag(id=r[0], name=r[1], color=r[2], description=r[3],
               category=r[4], created_at=r[5], dataset_count=r[6]) for r in rows]


def list_categories() -> list[str]:
    """Distinct non-empty tag categories, ordered."""
    rows = db.get_con().execute(
        "SELECT DISTINCT category FROM tags WHERE category IS NOT NULL "
        "AND category <> '' ORDER BY category"
    ).fetchall()
    return [r[0] for r in rows]


def tags_in_category(category: str) -> list[Tag]:
    return [t for t in list_tags() if (t.category or "") == category]


def get_tag(tag_id: int) -> Tag | None:
    for t in list_tags():
        if t.id == tag_id:
            return t
    return None


def update(tag_id: int, name: str | None = None, color: str | None = None,
           description: str | None = None, category=_UNSET) -> None:
    con = db.get_con()
    if name is not None:
        con.execute("UPDATE tags SET name = ? WHERE id = ?", [name.strip(), tag_id])
    if color is not None:
        con.execute("UPDATE tags SET color = ? WHERE id = ?", [color, tag_id])
    if description is not None:
        con.execute("UPDATE tags SET description = ? WHERE id = ?", [description, tag_id])
    if category is not _UNSET:
        cat = (category or "").strip() or None
        con.execute("UPDATE tags SET category = ? WHERE id = ?", [cat, tag_id])


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


def dataset_ids_matching_all(tag_ids: list[int]) -> list[int]:
    """Datasets carrying **every** tag in ``tag_ids`` (AND / intersection).

    An empty ``tag_ids`` matches all datasets. This is the basis for cohorts
    defined by a combination of tags (e.g. maker=A AND condition=highway).
    """
    if not tag_ids:
        rows = db.get_con().execute(
            "SELECT id FROM datasets ORDER BY id").fetchall()
        return [r[0] for r in rows]
    placeholders = ", ".join("?" for _ in tag_ids)
    rows = db.get_con().execute(
        f"SELECT dataset_id FROM dataset_tags WHERE tag_id IN ({placeholders}) "
        "GROUP BY dataset_id HAVING count(DISTINCT tag_id) = ? ORDER BY dataset_id",
        [*tag_ids, len(tag_ids)],
    ).fetchall()
    return [r[0] for r in rows]


# --------------------------------------------------------------------------- #
#  Bulk operations (used by the data-management screen)
# --------------------------------------------------------------------------- #
def assign_exclusive(dataset_id: int, tag_id: int) -> None:
    """Assign a tag, first removing any other tag of the same category.

    Enforces "one tag per category" (e.g. a dataset has exactly one メーカー).
    Tags without a category are assigned normally (no exclusion).
    """
    tag = get_tag(tag_id)
    if tag and tag.category:
        same = {t.id for t in tags_in_category(tag.category)} - {tag_id}
        for tid in tag_ids_for_dataset(dataset_id):
            if tid in same:
                unassign(dataset_id, tid)
    assign(dataset_id, tag_id)


def assign_many(dataset_ids: list[int], tag_id: int, exclusive: bool = False) -> int:
    for did in dataset_ids:
        if exclusive:
            assign_exclusive(did, tag_id)
        else:
            assign(did, tag_id)
    return len(dataset_ids)


def unassign_many(dataset_ids: list[int], tag_id: int) -> int:
    for did in dataset_ids:
        unassign(did, tag_id)
    return len(dataset_ids)
