"""Unit tests for the VDAS-Insight analysis engine.

These use tiny hand-built datasets with known answers, so the metrics are
verified by construction rather than by eyeballing charts.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def make_dataset(tmp_path):
    """Factory: write a DataFrame to parquet, register it, return the Dataset."""
    from vdas import datasets

    def _make(df: pd.DataFrame, name: str, roles: dict | None = None,
              params: dict | None = None):
        path = tmp_path / f"{name}.parquet"
        df.to_parquet(path, index=False)
        ds = datasets.register(str(path), name=name)
        if roles:
            datasets.set_roles(ds.id, roles, params)
        return ds

    return _make


def test_shift_detection_counts_transitions(make_dataset):
    from vdas.analysis import gears, prepare

    # gear sequence: 1 1 2 2 2 3 2 1  -> 4 transitions (2 up, 2 down)
    seq = [1, 1, 2, 2, 2, 3, 2, 1]
    df = pd.DataFrame({"t": np.arange(len(seq), dtype=float), "current_gear": seq})
    ds = make_dataset(df, "gears", {"t": "time", "current_gear": "gear"})
    p = prepare(ds)
    s = gears.summary(p)
    assert s["shift_count"] == 4
    assert s["upshifts"] == 2
    assert s["downshifts"] == 2


def test_shift_count_ignores_repeats(make_dataset):
    from vdas.analysis import gears, prepare

    seq = [3, 3, 3, 3]  # constant -> no shifts
    df = pd.DataFrame({"t": np.arange(4.0), "current_gear": seq})
    ds = make_dataset(df, "const_gear", {"t": "time", "current_gear": "gear"})
    assert gears.summary(prepare(ds))["shift_count"] == 0


def test_time_in_gear_shares_sum_to_one(make_dataset):
    from vdas.analysis import gears, prepare

    seq = [1, 1, 2, 2]
    df = pd.DataFrame({"t": np.arange(4.0), "current_gear": seq})
    ds = make_dataset(df, "tig", {"t": "time", "current_gear": "gear"})
    tig = gears.time_in_gear(prepare(ds))
    assert abs(tig["share"].sum() - 1.0) < 1e-9


def test_flag_intervals(make_dataset):
    from vdas.analysis import flags, prepare

    # 1 Hz sampling; ON blocks: samples 2-3 and 6-7 => 2 activations.
    flag = [0, 0, 1, 1, 0, 0, 1, 1, 0, 0]
    df = pd.DataFrame({"t": np.arange(len(flag), dtype=float), "f": flag})
    ds = make_dataset(df, "flags", {"t": "time", "f": "flag"})
    p = prepare(ds)
    d = flags.intervals(p, "f")
    assert d["activations"] == 2
    # each ON run spans 2 s (from its start to the next sample after it ends)
    assert d["on_durations"].tolist() == pytest.approx([2.0, 2.0])
    # between activations: onset at t=2 and t=6 -> 4 s
    assert d["between_activations"].tolist() == pytest.approx([4.0])


def test_time_unit_scaling(make_dataset):
    from vdas.analysis import prepare

    # times in milliseconds; 0..9000 ms => 9 s duration
    df = pd.DataFrame({"t_ms": np.arange(10, dtype=float) * 1000.0,
                       "x": np.arange(10.0)})
    ds = make_dataset(df, "ms", {"t_ms": "time", "x": "numeric"},
                      {"t_ms": {"unit": "ms"}})
    p = prepare(ds)
    assert p.duration_s == pytest.approx(9.0)


def test_cohort_pooling_uses_pooled_rate(make_dataset):
    """A cohort's pooled rate must weight by duration, not average per-dataset."""
    from vdas import tags
    from vdas.analysis import groups

    # Dataset A: 2 shifts over 1 s (huge rate but tiny). B: 2 shifts over 3600 s.
    a = pd.DataFrame({"t": [0.0, 1.0], "current_gear": [1, 2]})
    # B: gear toggles twice across an hour
    tb = np.linspace(0, 3600, 5)
    b = pd.DataFrame({"t": tb, "current_gear": [1, 2, 2, 3, 3]})
    dsa = make_dataset(a, "A", {"t": "time", "current_gear": "gear"})
    dsb = make_dataset(b, "B", {"t": "time", "current_gear": "gear"})

    tid = tags.create("cohort").id
    tags.assign(dsa.id, tid)
    tags.assign(dsb.id, tid)

    c = groups.build_cohort(tid)
    # pooled shift_count = 1 (A) + 2 (B) = 3 ; pooled hours = (1 + 3600)/3600
    assert c.pool["shift_count"] == pytest.approx(3.0)
    pooled_hours = (1.0 + 3600.0) / 3600.0
    assert c.pool["shifts_per_hour"] == pytest.approx(3.0 / pooled_hours)


def test_derived_acceleration_and_jerk(make_dataset):
    from vdas import derived
    from vdas.analysis import prepare

    # Constant acceleration: speed rises 0..100 km/h over 10 s.
    n = 101
    t = np.linspace(0, 10, n)
    kph = np.linspace(0, 100, n)          # 10 km/h per s
    df = pd.DataFrame({"t": t, "vehicle_speed_kph": kph})
    ds = make_dataset(df, "accel", {"t": "time", "vehicle_speed_kph": "speed"})

    derived.add(ds.id, "accel_from_speed", "vehicle_speed_kph", name="a")
    derived.add(ds.id, "jerk_from_speed", "vehicle_speed_kph", name="j")
    p = prepare(ds)
    assert "a" in p.df.columns and "j" in p.df.columns
    assert "a" in p.numeric_cols
    # 10 (km/h)/s = 10 * 1000/3600 ≈ 2.778 m/s² (ignore smoothed edges)
    a = p.df["a"].to_numpy()
    assert np.nanmedian(a[5:-5]) == pytest.approx(2.7778, abs=0.05)
    # constant acceleration -> jerk ~ 0 in the interior
    j = p.df["j"].to_numpy()
    assert abs(np.nanmedian(j[5:-5])) < 0.05


def test_tag_categories_and_and_matching(make_dataset):
    from vdas import tags

    # three datasets with maker/condition combinations
    def mk(name):
        df = pd.DataFrame({"t": np.arange(3.0), "vehicle_speed_kph": [0, 10, 20]})
        return make_dataset(df, name, {"t": "time", "vehicle_speed_kph": "speed"})

    d1, d2, d3 = mk("d1"), mk("d2"), mk("d3")
    mA = tags.create("A", category="maker").id
    mB = tags.create("B", category="maker").id
    hwy = tags.create("hwy", category="cond").id

    tags.assign(d1.id, mA); tags.assign(d1.id, hwy)
    tags.assign(d2.id, mB); tags.assign(d2.id, hwy)
    tags.assign(d3.id, mA)               # A but not hwy

    assert tags.list_categories() == ["cond", "maker"]
    assert {t.name for t in tags.tags_in_category("maker")} == {"A", "B"}
    # A AND hwy -> only d1 (d3 is A but not hwy)
    assert tags.dataset_ids_matching_all([mA, hwy]) == [d1.id]
    # empty filter -> all datasets
    assert set(tags.dataset_ids_matching_all([])) >= {d1.id, d2.id, d3.id}


def test_cohort_from_dataset_ids(make_dataset):
    from vdas.analysis import groups

    def mk(name, gears):
        df = pd.DataFrame({"t": np.arange(len(gears), dtype=float), "g": gears})
        return make_dataset(df, name, {"t": "time", "g": "gear"})

    a = mk("ca", [1, 2, 3])       # 2 shifts
    b = mk("cb", [1, 1, 2])       # 1 shift
    c = groups.build_cohort_from("grp", [a.id, b.id])
    assert c.pool["shift_count"] == 3
    assert c.label == "grp" and set(c.dataset_ids) == {a.id, b.id}


def test_derived_persist_and_delete(make_dataset):
    from vdas import derived

    df = pd.DataFrame({"t": np.arange(10.0), "vehicle_speed_kph": np.arange(10.0)})
    ds = make_dataset(df, "persist", {"t": "time", "vehicle_speed_kph": "speed"})
    d = derived.add(ds.id, "derivative", "vehicle_speed_kph", name="spd_ddt")
    assert "spd_ddt" in derived.names_for_dataset(ds.id)
    derived.delete(d.id)
    assert "spd_ddt" not in derived.names_for_dataset(ds.id)


def test_speed_vs_engine_role_detection(make_dataset):
    from vdas import datasets

    df = pd.DataFrame({
        "timestamp_s": np.arange(5.0),
        "vehicle_speed_kph": [0, 10, 20, 30, 40],
        "engine_speed_rpm": [800, 1200, 1600, 2000, 2400],
    })
    ds = make_dataset(df, "roles")  # rely on auto-detection
    roles = datasets.get_roles(ds.id)
    assert roles["vehicle_speed_kph"] == "speed"
    assert roles["engine_speed_rpm"] == "numeric"  # not mistaken for speed
    assert roles["timestamp_s"] == "time"
