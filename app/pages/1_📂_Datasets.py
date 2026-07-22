"""Dataset registration and column-role management."""
from __future__ import annotations

import glob
import os

from _shared import ROOT, dataset_selectbox, page_setup, role_label
import streamlit as st

from vdas import datasets as ds_mod
from vdas.config import ROLES, UPLOAD_DIR

page_setup("Datasets", "📂")
st.title("📂 Datasets")
st.caption("parquet / csv を登録し、各列の役割を割り当てます。")

tab_add, tab_manage, tab_roles = st.tabs(["➕ 登録", "🗂 一覧・管理", "🎛 役割の編集"])

# --------------------------------------------------------------------------- #
#  Add
# --------------------------------------------------------------------------- #
with tab_add:
    st.subheader("ファイルパスから登録")
    st.write("サーバー上の parquet / csv のパス（グロブ可）を指定します。")
    default_glob = str(ROOT / "sample_data" / "*.parquet")
    pattern = st.text_input("パス / グロブ", value=default_glob)
    if st.button("マッチしたファイルを登録", type="primary"):
        matches = sorted(glob.glob(pattern))
        if not matches:
            st.warning("マッチするファイルがありません。")
        else:
            existing = {d.path for d in ds_mod.list_datasets()}
            n = 0
            for p in matches:
                if os.path.abspath(p) in existing:
                    continue
                try:
                    ds_mod.register(p)
                    n += 1
                except Exception as e:  # noqa: BLE001
                    st.error(f"{p}: {e}")
            st.success(f"{n} 件を登録しました（役割は自動推定済み）。")
            st.rerun()

    st.divider()
    st.subheader("アップロードして登録")
    up = st.file_uploader("parquet / csv をアップロード", type=["parquet", "csv"],
                          accept_multiple_files=True)
    if up and st.button("アップロードを登録"):
        n = 0
        for f in up:
            dest = UPLOAD_DIR / f.name
            dest.write_bytes(f.getbuffer())
            try:
                ds_mod.register(str(dest))
                n += 1
            except Exception as e:  # noqa: BLE001
                st.error(f"{f.name}: {e}")
        st.success(f"{n} 件を登録しました。")
        st.rerun()

# --------------------------------------------------------------------------- #
#  Manage
# --------------------------------------------------------------------------- #
with tab_manage:
    items = ds_mod.list_datasets()
    if not items:
        st.info("データセットがありません。")
    for d in items:
        with st.expander(f"[{d.id}] {d.name}  ·  {d.format}  ·  {d.row_count:,} rows"
                         + ("" if d.exists else "  ⚠️ ファイルなし")):
            st.code(d.path, language="text")
            cc1, cc2, cc3 = st.columns([2, 1, 1])
            new_name = cc1.text_input("名前", value=d.name, key=f"nm_{d.id}")
            if cc2.button("名前を更新", key=f"rn_{d.id}"):
                ds_mod.rename(d.id, new_name)
                st.rerun()
            if cc3.button("🗑 削除", key=f"del_{d.id}"):
                ds_mod.delete(d.id)
                st.rerun()
            if d.exists:
                st.write("**プレビュー（先頭 30 行）**")
                st.dataframe(ds_mod.head(d, 30), use_container_width=True, height=240)

# --------------------------------------------------------------------------- #
#  Roles
# --------------------------------------------------------------------------- #
with tab_roles:
    d = dataset_selectbox(key="role_ds")
    if d:
        roles = ds_mod.get_roles(d.id)
        params = ds_mod.get_role_params(d.id)
        sch = dict(ds_mod.schema(d))
        st.write("各列の役割を設定します。**時間**列は 1 つだけ選んでください。")

        cols_a, cols_b = st.columns(2)
        if cols_a.button("🔄 役割を自動再推定"):
            ds_mod.set_roles(d.id, ds_mod.auto_detect_roles(d))
            st.rerun()

        with st.form(f"roles_{d.id}"):
            new_roles: dict[str, str] = {}
            new_params: dict[str, dict] = {}
            for col in ds_mod.columns(d):
                c1, c2, c3 = st.columns([3, 2, 2])
                c1.markdown(f"**{col}**  \n<small>{sch.get(col,'')}</small>",
                            unsafe_allow_html=True)
                cur = roles.get(col, "numeric")
                new_roles[col] = c2.selectbox(
                    "役割", ROLES, index=ROLES.index(cur) if cur in ROLES else 0,
                    format_func=role_label, key=f"role_{d.id}_{col}",
                    label_visibility="collapsed")
                if new_roles[col] == "time":
                    unit = (params.get(col) or {}).get("unit", "s")
                    u = c3.selectbox("単位", ["s", "ms", "us", "ns", "min"],
                                     index=["s", "ms", "us", "ns", "min"].index(unit),
                                     key=f"unit_{d.id}_{col}",
                                     label_visibility="collapsed")
                    new_params[col] = {"unit": u}
                else:
                    c3.write("")
            if st.form_submit_button("💾 役割を保存", type="primary"):
                n_time = sum(1 for r in new_roles.values() if r == "time")
                if n_time > 1:
                    st.error("時間列は 1 つだけにしてください。")
                else:
                    ds_mod.set_roles(d.id, new_roles, new_params)
                    st.success("保存しました。")
                    st.rerun()
