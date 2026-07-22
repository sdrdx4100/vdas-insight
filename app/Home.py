"""VDAS-Insight — Streamlit entry point.

Run with:  streamlit run app/Home.py
"""
from __future__ import annotations

import glob

from _shared import ROOT, page_setup
import streamlit as st

from vdas import datasets as ds_mod
from vdas import tags as tags_mod

page_setup("Home")

st.title("🚗 VDAS-Insight")
st.caption("Vehicle Data Analysis & Statistics — 大規模車両計測データ（J1939 等）の"
           "可視化・統計・コホート比較プラットフォーム")

c1, c2, c3 = st.columns(3)
c1.metric("登録データセット", len(ds_mod.list_datasets()))
c2.metric("タグ（コホート）", len(tags_mod.list_tags()))
n_tagged = sum(t.dataset_count for t in tags_mod.list_tags())
c3.metric("タグ付け延べ数", n_tagged)

st.divider()

left, right = st.columns([3, 2])
with left:
    st.subheader("ワークフロー")
    st.markdown(
        """
1. **📂 Datasets** — parquet / csv を登録し、各列の *役割*（時間・ギア・フラグ・
   車速・数値）を割り当てます。役割は自動推定され、手動で修正できます。
2. **📈 Explore** — 1 つのデータの統計・時系列・ギア段分析・フラグ間隔分析を
   インタラクティブに確認します。
3. **🏷️ Tags** — データセットを *コホート*（集団）としてタグ付けします。
4. **📊 Compare** — タグ同士を **レート正規化**（時間あたり・距離あたり・割合）で
   比較します。N 数が異なっても公平に比較できます。
        """
    )

with right:
    st.subheader("サンプルデータ")
    st.write("同梱の J1939 風サンプル（市街地 / 高速）で機能をすぐ試せます。")
    samples = sorted(glob.glob(str(ROOT / "sample_data" / "*.parquet")))
    st.write(f"`sample_data/` に {len(samples)} ファイル")
    if st.button("▶ サンプルを一括登録してタグ付け", type="primary",
                 disabled=not samples):
        existing = {d.path for d in ds_mod.list_datasets()}
        created = []
        for p in samples:
            import os
            if os.path.abspath(p) in existing:
                continue
            created.append(ds_mod.register(p))
        # Auto-create city / highway cohorts from filename.
        by_name = {t.name: t.id for t in tags_mod.list_tags()}
        tid_city = by_name.get("city") or tags_mod.create("city", "#2a78d6", "市街地走行").id
        tid_hw = by_name.get("highway") or tags_mod.create("highway", "#eb6834", "高速走行").id
        for d in ds_mod.list_datasets():
            tid = tid_city if d.name.startswith("city") else tid_hw if d.name.startswith("highway") else None
            if tid:
                tags_mod.assign(d.id, tid)
        st.success(f"{len(created)} 件を登録し、city / highway タグを付与しました。")
        st.rerun()

st.divider()
st.subheader("現在のデータセット")
items = ds_mod.list_datasets()
if not items:
    st.info("データセットがありません。上のボタンでサンプルを登録するか、"
            "『Datasets』ページで独自データを登録してください。")
else:
    rows = []
    for d in items:
        tg = [t for t in tags_mod.list_tags()
              if d.id in tags_mod.dataset_ids_for_tag(t.id)]
        rows.append({
            "id": d.id, "name": d.name, "format": d.format,
            "rows": d.row_count, "tags": ", ".join(t.name for t in tg) or "—",
            "exists": "✅" if d.exists else "⚠️ missing",
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)
