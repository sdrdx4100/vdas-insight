"""Tag (cohort) management and dataset assignment."""
from __future__ import annotations

from _shared import page_setup, tag_chip
import streamlit as st

from vdas import datasets as ds_mod
from vdas import tags as tags_mod
from vdas.config import TAG_COLORS

page_setup("Tags", "🏷️")
st.title("🏷️ Tags")
st.caption("データセットを集団（コホート）としてタグ付けします。タグは比較の単位になります。")

tab_manage, tab_assign = st.tabs(["🏷 タグの作成・編集", "🔗 データへの割当"])

# --------------------------------------------------------------------------- #
#  Create / edit tags
# --------------------------------------------------------------------------- #
with tab_manage:
    with st.form("new_tag", clear_on_submit=True):
        st.subheader("新しいタグ")
        c1, c2 = st.columns([2, 1])
        name = c1.text_input("タグ名")
        color = c2.selectbox("色", TAG_COLORS, format_func=lambda c: c)
        desc = st.text_input("説明（任意）")
        if st.form_submit_button("作成", type="primary"):
            if not name.strip():
                st.error("タグ名を入力してください。")
            elif any(t.name == name.strip() for t in tags_mod.list_tags()):
                st.error("同名のタグが既に存在します。")
            else:
                tags_mod.create(name, color, desc)
                st.rerun()

    st.divider()
    st.subheader("既存のタグ")
    for t in tags_mod.list_tags():
        with st.expander(f"{t.name}  ·  {t.dataset_count} 件"):
            st.markdown(tag_chip(t), unsafe_allow_html=True)
            c1, c2, c3 = st.columns([2, 2, 1])
            nn = c1.text_input("名前", value=t.name, key=f"tn_{t.id}")
            nd = c2.text_input("説明", value=t.description or "", key=f"td_{t.id}")
            nc = c1.selectbox("色", TAG_COLORS,
                              index=TAG_COLORS.index(t.color) if t.color in TAG_COLORS else 0,
                              key=f"tc_{t.id}")
            if c2.button("💾 更新", key=f"tu_{t.id}"):
                tags_mod.update(t.id, name=nn, color=nc, description=nd)
                st.rerun()
            if c3.button("🗑 削除", key=f"tdel_{t.id}"):
                tags_mod.delete(t.id)
                st.rerun()
            ids = tags_mod.dataset_ids_for_tag(t.id)
            names = [ds_mod.get_dataset(i).name for i in ids if ds_mod.get_dataset(i)]
            st.write("**所属データ:** " + (", ".join(names) if names else "—"))

# --------------------------------------------------------------------------- #
#  Assign datasets <-> tags
# --------------------------------------------------------------------------- #
with tab_assign:
    datasets = ds_mod.list_datasets()
    all_tags = tags_mod.list_tags()
    if not datasets:
        st.info("データセットがありません。")
    elif not all_tags:
        st.info("タグがありません。先にタグを作成してください。")
    else:
        st.write("各データセットに付与するタグを選択します（複数可）。")
        tag_by_id = {t.id: t for t in all_tags}
        for d in datasets:
            cur = tags_mod.tag_ids_for_dataset(d.id)
            options = {t.name: t.id for t in all_tags}
            picked = st.multiselect(
                f"[{d.id}] {d.name}",
                list(options.keys()),
                default=[tag_by_id[i].name for i in cur if i in tag_by_id],
                key=f"assign_{d.id}")
            picked_ids = [options[p] for p in picked]
            if set(picked_ids) != set(cur):
                tags_mod.set_dataset_tags(d.id, picked_ids)
                st.rerun()
