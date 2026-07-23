"""Cohort (tag) aggregation and comparison.

The central idea of the platform: treat every dataset carrying a tag as one
statistical population and compare populations on **rate-normalized** metrics,
so cohorts with different N (number of logs, total duration, distance) are
compared fairly.

Two complementary views are produced:

  * **Pooled rate** — sum the extensive quantities across the whole cohort,
    then form the rate once (e.g. total shifts / total hours). This is the
    correct headline number.
  * **Per-dataset distribution** — the same rate computed per dataset, giving a
    spread (mean / std / box) so you can see dispersion, not just the pooled
    point estimate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .. import datasets as ds_mod
from .. import tags as tags_mod
from .core import prepare
from .metrics import base_quantities, derived_from_pool, metrics_from_prepared


# --------------------------------------------------------------------------- #
#  Metric registry — the comparable metrics offered in the UI
# --------------------------------------------------------------------------- #
@dataclass
class MetricDef:
    key: str
    label: str
    unit: str
    kind: str            # 'rate' | 'ratio' | 'count' | 'duration'
    higher_is: str = ""  # informational

    @property
    def is_percent(self) -> bool:
        return self.kind == "ratio"


CORE_METRICS: list[MetricDef] = [
    MetricDef("shift_count", "総変速回数", "回", "count"),
    MetricDef("shifts_per_hour", "変速回数 / 時間", "回/h", "rate"),
    MetricDef("shifts_per_km", "変速回数 / 距離", "回/km", "rate"),
    MetricDef("upshift_ratio", "アップシフト比率", "%", "ratio"),
    MetricDef("downshift_ratio", "ダウンシフト比率", "%", "ratio"),
    MetricDef("duration_h", "総計測時間", "h", "duration"),
    MetricDef("distance_km", "総走行距離", "km", "duration"),
]


def flag_metric_defs(flag_col: str) -> list[MetricDef]:
    return [
        MetricDef(f"flag::{flag_col}::activations", f"{flag_col} 立上り回数", "回", "count"),
        MetricDef(f"flag::{flag_col}::activations_per_hour",
                  f"{flag_col} 立上り / 時間", "回/h", "rate"),
        MetricDef(f"flag::{flag_col}::duty_cycle", f"{flag_col} ON率", "%", "ratio"),
    ]


def numeric_metric_defs(col: str) -> list[MetricDef]:
    """Poolable numeric-signal aggregates (mean is length-weighted across N)."""
    return [
        MetricDef(f"num::{col}::mean", f"{col} 平均", "", "signal"),
        MetricDef(f"num::{col}::std", f"{col} 標準偏差", "", "signal"),
        MetricDef(f"num::{col}::max", f"{col} 最大", "", "signal"),
        MetricDef(f"num::{col}::min", f"{col} 最小", "", "signal"),
    ]


# --------------------------------------------------------------------------- #
#  Cohort computation
# --------------------------------------------------------------------------- #
@dataclass
class Cohort:
    label: str                                   # display name
    dataset_ids: list[int]                        # members
    pool: dict                                   # pooled extensive + derived rates
    per_dataset: pd.DataFrame                    # one row per dataset, full metrics
    flag_cols: list[str] = field(default_factory=list)
    color: str | None = None

    def value(self, key: str) -> float:
        return float(self.pool.get(key, np.nan))

    def spread(self, key: str) -> np.ndarray:
        if key in self.per_dataset.columns:
            return pd.to_numeric(self.per_dataset[key], errors="coerce").to_numpy(dtype=float)
        return np.array([], dtype=float)


def build_cohort_from(label: str, dataset_ids: list[int], color: str | None = None,
                      condition: list | None = None) -> Cohort:
    """Pool metrics over an explicit set of datasets (the core builder).

    ``condition`` is an optional list of ``conditions.Predicate`` applied per
    dataset as a per-sample mask (gated / conditional aggregation).
    """
    pool: dict = {}
    rows = []
    flag_cols: set[str] = set()
    used: list[int] = []
    mask = None
    if condition:
        from .conditions import compute_mask
    for did in dataset_ids:
        ds = ds_mod.get_dataset(did)
        if ds is None or not ds.exists:
            continue
        used.append(did)
        pd_data = prepare(ds)          # single read; reused for both below
        flag_cols.update(pd_data.flag_cols)
        mask = compute_mask(pd_data, condition) if condition else None
        q = base_quantities(pd_data, mask)
        for k, v in q.items():
            if v is None or (isinstance(v, float) and np.isnan(v)):
                continue
            if k.endswith("::max"):
                pool[k] = max(pool[k], v) if k in pool else v
            elif k.endswith("::min"):
                pool[k] = min(pool[k], v) if k in pool else v
            else:
                pool[k] = pool.get(k, 0.0) + v
        m = metrics_from_prepared(pd_data, mask)
        m["dataset_id"] = ds.id
        m["dataset_name"] = ds.name
        rows.append(m)

    pool.update(derived_from_pool(pool))
    per_df = pd.DataFrame(rows) if rows else pd.DataFrame()
    return Cohort(label=label, dataset_ids=used, pool=pool,
                  per_dataset=per_df, flag_cols=sorted(flag_cols), color=color)


def build_cohort(tag_id: int) -> Cohort:
    """Build a cohort from a single tag (backwards-compatible helper)."""
    tag = tags_mod.get_tag(tag_id)
    label = tag.name if tag else f"tag {tag_id}"
    color = tag.color if tag else None
    return build_cohort_from(label, tags_mod.dataset_ids_for_tag(tag_id), color)


# --------------------------------------------------------------------------- #
#  Comparison
# --------------------------------------------------------------------------- #
@dataclass
class CohortDef:
    label: str
    dataset_ids: list[int]
    color: str | None = None


def compare_defs(defs: list[CohortDef], metric_keys: list[str],
                 condition: list | None = None) -> tuple[pd.DataFrame, list[Cohort]]:
    """Compare arbitrary cohort definitions (label + dataset set) on metrics.

    ``condition`` (list of conditions.Predicate) gates every cohort's
    aggregation to in-condition samples (e.g. speed ≤ 70).
    """
    cohorts = [build_cohort_from(d.label, d.dataset_ids, d.color, condition)
               for d in defs]
    records = []
    for c in cohorts:
        rec = {"tag": c.label,
               "n_datasets": int(c.pool.get("n_datasets", 0)),
               "duration_h": c.pool.get("duration_s", 0.0) / 3600.0}
        for key in metric_keys:
            rec[key] = c.value(key)
        records.append(rec)
    return pd.DataFrame(records), cohorts


def compare(tag_ids: list[int], metric_keys: list[str]) -> tuple[pd.DataFrame, list[Cohort]]:
    """Compare one-tag cohorts (backwards-compatible)."""
    defs = []
    for tid in tag_ids:
        t = tags_mod.get_tag(tid)
        defs.append(CohortDef(t.name if t else f"tag {tid}",
                              tags_mod.dataset_ids_for_tag(tid),
                              t.color if t else None))
    return compare_defs(defs, metric_keys)


def relative_index(df: pd.DataFrame, metric_key: str, base_tag: str | None = None) -> pd.Series:
    """Index each cohort's metric to a baseline cohort (=100).

    Lets you say "cohort B upshifts 118 % as often per hour as cohort A",
    which is the fair way to compare cohorts of different N.
    """
    vals = df.set_index("tag")[metric_key]
    if base_tag and base_tag in vals.index and vals[base_tag]:
        base = vals[base_tag]
    else:
        base = vals.dropna().iloc[0] if not vals.dropna().empty else np.nan
    return (vals / base * 100.0) if base else vals * np.nan
