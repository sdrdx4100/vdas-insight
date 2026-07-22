"""Cohort comparison — the flagship view.

Compare tagged cohorts on rate-normalized metrics so that cohorts of different
N (log count / duration / distance) are compared fairly.
"""
from __future__ import annotations

import pandas as pd

from _shared import page_setup, plot, tag_multiselect
import streamlit as st

from vdas import datasets as ds_mod
from vdas import tags as tags_mod
from vdas.analysis import groups
from vdas.analysis.groups import CORE_METRICS, MetricDef, flag_metric_defs
from vdas.viz import charts

page_setup("Compare", "📊")
st.title("📊 Cohort Compare")
st.caption("タグ（コホート）同士を、時間あたり・距離あたり・割合で公平に比較します。")

tag_ids = tag_multiselect(key="cmp_tags")
if len(tag_ids) < 1:
    st.info("比較するタグを選択してください（2 つ以上で比較が明確になります）。")
    st.stop()

# --- Build the available metric list (core + flags present in cohorts) ------
flag_cols: set[str] = set()
for tid in tag_ids:
    for did in tags_mod.dataset_ids_for_tag(tid):
        flag_cols.update(ds_mod.flag_columns(did))

metric_defs: list[MetricDef] = list(CORE_METRICS)
for fc in sorted(flag_cols):
    metric_defs += flag_metric_defs(fc)
def_by_key = {m.key: m for m in metric_defs}

st.subheader("比較する指標")
default_metrics = ["shifts_per_hour", "shifts_per_km", "upshift_ratio"]
chosen_keys = st.multiselect(
    "指標（レート・割合で正規化済み）",
    [m.key for m in metric_defs],
    default=[k for k in default_metrics if k in def_by_key],
    format_func=lambda k: f"{def_by_key[k].label}  [{def_by_key[k].unit}]",
    key="cmp_metrics")

if not chosen_keys:
    st.info("指標を 1 つ以上選択してください。")
    st.stop()


@st.cache_data(show_spinner="集計中…")
def _compare(tag_ids: tuple[int, ...], keys: tuple[str, ...], _v: int):
    df, cohorts = groups.compare(list(tag_ids), list(keys))
    return df, cohorts


# Cache-buster: number of dataset↔tag links, so edits invalidate the cache.
link_version = sum(len(tags_mod.dataset_ids_for_tag(t)) for t in tag_ids)
df, cohorts = _compare(tuple(tag_ids), tuple(chosen_keys), link_version)

# --- Cohort overview --------------------------------------------------------
st.subheader("コホート概要")
ov = df[["tag", "n_datasets", "duration_h"]].copy()
ov.columns = ["タグ", "データ数 (N)", "総計測時間 (h)"]
st.dataframe(ov, use_container_width=True, hide_index=True)
st.caption("※ N（データ数）や総時間が異なるため、以下は原則としてレート/割合で比較します。")

# --- Per-metric comparison --------------------------------------------------
for key in chosen_keys:
    mdef = def_by_key[key]
    st.divider()
    st.subheader(f"{mdef.label}　[{mdef.unit}]")

    c1, c2 = st.columns(2)
    with c1:
        plot(charts.cohort_bar(df, key, mdef.label, mdef.unit, mdef.is_percent),
             key=f"bar_{key}")
        st.caption("プール値：コホート全体の合計量から算出したレート（公平な代表値）。")
    with c2:
        plot(charts.cohort_box(cohorts, key, mdef.label, mdef.unit, mdef.is_percent),
             key=f"box_{key}")
        st.caption("分布：データセット単位で同じ指標を計算したばらつき。")

    if len(tag_ids) >= 2 and mdef.kind in ("rate", "count"):
        base = st.selectbox("相対指数の基準コホート", df["tag"].tolist(),
                            key=f"base_{key}")
        idx = groups.relative_index(df, key, base_tag=base)
        plot(charts.relative_index_bar(idx, mdef.label), key=f"idx_{key}")
        st.caption(f"『{base}』を 100 とした相対比較。N が違っても割合で読み取れます。")

# --- Full table + export ----------------------------------------------------
st.divider()
st.subheader("比較テーブル")
disp = df.copy()
for key in chosen_keys:
    if def_by_key[key].is_percent:
        disp[key] = disp[key] * 100.0
rename = {"tag": "タグ", "n_datasets": "N", "duration_h": "時間(h)"}
rename.update({k: f"{def_by_key[k].label}[{def_by_key[k].unit}]" for k in chosen_keys})
disp = disp.drop(columns=["tag_id"]).rename(columns=rename)
st.dataframe(disp, use_container_width=True, hide_index=True)
st.download_button("⬇ CSV でエクスポート", disp.to_csv(index=False).encode("utf-8-sig"),
                   file_name="cohort_comparison.csv", mime="text/csv")
