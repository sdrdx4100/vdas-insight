"""Single-dataset exploration: stats, time series, gears, flags."""
from __future__ import annotations

import numpy as np
import pandas as pd

from _shared import PLOTLY_CONFIG, dataset_selectbox, fmt, page_setup, plot
import streamlit as st

from vdas import datasets as ds_mod
from vdas.analysis import flags, gears, prepare
from vdas.analysis.metrics import numeric_stats
from vdas.viz import charts

page_setup("Explore", "📈")
st.title("📈 Explore")
st.caption("1 つのデータセットの統計・時系列・ギア段・フラグを分析します。")

d = dataset_selectbox(key="explore_ds")
if not d:
    st.stop()
if not d.exists:
    st.error("ファイルが見つかりません。")
    st.stop()


@st.cache_data(show_spinner="読み込み中…")
def _prepared_summary(dataset_id: int, path: str, mtime: float):
    ds = ds_mod.get_dataset(dataset_id)
    pdd = prepare(ds)
    return {
        "duration_h": pdd.duration_h,
        "duration_s": pdd.duration_s,
        "n": pdd.n,
        "dt": pdd.dt,
        "dist": pdd.distance_km(),
        "gear_col": pdd.gear_col,
        "speed_col": pdd.speed_col,
        "flag_cols": pdd.flag_cols,
        "numeric_cols": pdd.numeric_cols,
        "gear_summary": gears.summary(pdd) if pdd.gear_col else None,
    }


import os
mtime = os.path.getmtime(d.path)
summ = _prepared_summary(d.id, d.path, mtime)

# --- Header metrics ---------------------------------------------------------
m = st.columns(5)
m[0].metric("行数", f"{summ['n']:,}")
m[1].metric("計測時間", f"{summ['duration_h']:.3f} h")
m[2].metric("サンプリング", f"{(1/summ['dt']) if summ['dt'] else 0:.1f} Hz")
m[3].metric("走行距離", f"{summ['dist']:.2f} km" if summ['dist'] is not None else "—")
if summ["gear_summary"]:
    m[4].metric("変速回数", f"{summ['gear_summary']['shift_count']:,}")

tabs = st.tabs(["📊 統計", "📉 時系列", "⚙️ ギア段", "🚩 フラグ"])

# =========================================================================== #
#  Stats
# =========================================================================== #
with tabs[0]:
    pdd = prepare(d)
    st.subheader("数値列の記述統計")
    rows = [numeric_stats(pdd, c) for c in pdd.numeric_cols]
    rows = [r for r in rows if r.get("n")]
    if rows:
        st.dataframe(pd.DataFrame(rows).set_index("column"),
                     use_container_width=True)
    else:
        st.info("数値列がありません。")

    st.subheader("分布 / 相関")
    cc1, cc2 = st.columns(2)
    if pdd.numeric_cols:
        hist_col = cc1.selectbox("ヒストグラム対象", pdd.numeric_cols, key="hist_col")
        vals = pd.to_numeric(pdd.df[hist_col], errors="coerce").to_numpy(float)
        plot(charts.histogram(vals[np.isfinite(vals)], f"{hist_col} の分布", hist_col),
             key="hist")
    if len(pdd.numeric_cols) >= 2:
        xcol = cc2.selectbox("散布図 X", pdd.numeric_cols, key="sc_x")
        ycol = cc2.selectbox("散布図 Y", pdd.numeric_cols,
                             index=min(1, len(pdd.numeric_cols) - 1), key="sc_y")
        x = pd.to_numeric(pdd.df[xcol], errors="coerce").to_numpy(float)
        y = pd.to_numeric(pdd.df[ycol], errors="coerce").to_numpy(float)
        plot(charts.scatter(x, y, xcol, ycol), key="scatter")

# =========================================================================== #
#  Time series
# =========================================================================== #
with tabs[1]:
    pdd = prepare(d)
    st.subheader("時系列（信号ごとにサブプロット）")
    candidates = pdd.numeric_cols + ([pdd.gear_col] if pdd.gear_col else [])
    default = [c for c in [pdd.speed_col, pdd.gear_col] if c][:2] or candidates[:2]
    sel = st.multiselect("表示する信号（最大 8）", candidates, default=default,
                         key="ts_cols", max_selections=8)
    if sel:
        plot(charts.timeseries(pdd.t, pdd.df, sel), key="ts")
    else:
        st.info("信号を選択してください。")

# =========================================================================== #
#  Gears
# =========================================================================== #
with tabs[2]:
    pdd = prepare(d)
    if not pdd.gear_col:
        st.info("ギア役割の列がありません。『Datasets』→『役割の編集』で設定してください。")
    else:
        gsum = gears.summary(pdd)
        gm = st.columns(5)
        gm[0].metric("総変速回数", f"{gsum['shift_count']:,}")
        gm[1].metric("アップシフト", f"{gsum['upshifts']:,}")
        gm[2].metric("ダウンシフト", f"{gsum['downshifts']:,}")
        gm[3].metric("変速 / 時間", fmt(gsum["shifts_per_hour"], 1))
        gm[4].metric("変速 / km", fmt(gsum["shifts_per_km"], 2))

        ev = gears.shift_events(pdd)
        st.subheader("ギア段の推移")
        plot(charts.gear_timeline(pdd.t, pdd.df[pdd.gear_col],
                                  ev["t"].to_numpy() if not ev.empty else None),
             key="gear_tl")

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("ギア段別 滞在時間")
            tig = gears.time_in_gear(pdd)
            plot(charts.time_in_gear(tig), key="tig")
        with c2:
            st.subheader("変速の遷移行列（from → to）")
            mat = gears.transition_matrix(pdd)
            if not mat.empty:
                plot(charts.transition_heatmap(mat), key="tmat")
            else:
                st.info("遷移がありません。")

# =========================================================================== #
#  Flags
# =========================================================================== #
with tabs[3]:
    pdd = prepare(d)
    if not pdd.flag_cols:
        st.info("フラグ役割（0/1）の列がありません。")
    else:
        st.subheader("フラグ別 サマリ")
        st.dataframe(flags.summary_table(pdd), use_container_width=True, hide_index=True)

        fcol = st.selectbox("詳細を見るフラグ", pdd.flag_cols, key="flag_pick")
        d_iv = flags.intervals(pdd, fcol)
        fm = st.columns(4)
        fm[0].metric("立上り回数", f"{d_iv['activations']:,}")
        fm[1].metric("立上り / 時間", fmt(d_iv["activations_per_hour"], 1))
        fm[2].metric("ON 率", fmt(d_iv["duty_cycle"] * 100, 2) + " %")
        fm[3].metric("平均 ON 時間", fmt(d_iv["mean_on_s"], 2) + " s")

        plot(charts.flag_timeline(pdd.t, pdd.df[fcol], fcol), key="flag_tl")
        c1, c2 = st.columns(2)
        with c1:
            if len(d_iv["on_durations"]):
                plot(charts.duration_histogram(d_iv["on_durations"],
                     f"{fcol} ON 時間の分布", "ON 時間 (s)", color_slot=1), key="on_hist")
        with c2:
            if len(d_iv["between_activations"]):
                plot(charts.duration_histogram(d_iv["between_activations"],
                     f"{fcol} 立上り間隔の分布", "間隔 (s)", color_slot=2), key="int_hist")
