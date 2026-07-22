"""Shared helpers for the Streamlit pages (path bootstrap, widgets, theming)."""
from __future__ import annotations

import sys
from pathlib import Path

# Make the `vdas` package importable no matter where Streamlit is launched from.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from vdas import datasets as ds_mod  # noqa: E402
from vdas import tags as tags_mod  # noqa: E402
from vdas.config import ROLE_LABELS, ROLES  # noqa: E402

PLOTLY_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": ["select2d", "lasso2d"],
    "toImageButtonOptions": {"format": "png", "scale": 2},
    "scrollZoom": True,
}


def page_setup(title: str, icon: str = "🚗") -> None:
    st.set_page_config(page_title=f"{title} · VDAS-Insight", page_icon=icon,
                       layout="wide", initial_sidebar_state="expanded")


def plot(fig, key: str | None = None) -> None:
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, key=key)


def dataset_selectbox(label: str = "データセット", key: str = "ds_select",
                      allow_none: bool = False):
    items = ds_mod.list_datasets()
    if not items:
        st.info("まだデータセットがありません。『Datasets』ページで登録してください。")
        return None
    options = {f"[{d.id}] {d.name}": d.id for d in items}
    if allow_none:
        options = {"— 選択 —": None, **options}
    label_sel = st.selectbox(label, list(options.keys()), key=key)
    did = options[label_sel]
    return ds_mod.get_dataset(did) if did is not None else None


def tag_multiselect(label: str = "タグ（コホート）", key: str = "tag_sel",
                    default_all: bool = True):
    items = tags_mod.list_tags()
    if not items:
        st.info("まだタグがありません。『Tags』ページで作成してください。")
        return []
    options = {f"{t.name}  ({t.dataset_count}件)": t.id for t in items}
    default = list(options.keys()) if default_all else []
    chosen = st.multiselect(label, list(options.keys()), default=default, key=key)
    return [options[c] for c in chosen]


def tag_chip(tag) -> str:
    color = tag.color or "#888"
    return (f"<span style='background:{color};color:#fff;padding:2px 10px;"
            f"border-radius:12px;font-size:0.85em;white-space:nowrap'>{tag.name}</span>")


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


def fmt(v, nd: int = 2) -> str:
    try:
        f = float(v)
        if f != f:  # NaN
            return "—"
        return f"{f:,.{nd}f}"
    except (TypeError, ValueError):
        return "—"
