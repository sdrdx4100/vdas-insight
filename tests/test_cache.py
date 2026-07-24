"""Prepared-frame cache behaviour and invalidation."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _make_dataset(tmp_path, name):
    from vdas import datasets

    path = tmp_path / f"{name}.parquet"
    pd.DataFrame({"t": np.arange(4.0), "v": np.arange(4.0)}).to_parquet(
        path, index=False)
    dataset = datasets.register(str(path), name=name)
    datasets.set_roles(dataset.id, {"t": "time", "v": "numeric"})
    return dataset


def test_prepared_cache_is_lru_bounded(tmp_path):
    from vdas.analysis import core

    core.invalidate_prepared_cache()
    datasets = [_make_dataset(tmp_path, f"cache_{i}") for i in range(4)]
    for dataset in datasets:
        core.prepare(dataset)

    assert len(core._PREP_CACHE) == core._PREP_CACHE_MAX
    assert datasets[0].id not in core._PREP_CACHE
    assert list(core._PREP_CACHE) == [d.id for d in datasets[1:]]


def test_prepared_cache_invalidation(tmp_path):
    from vdas.analysis import core

    core.invalidate_prepared_cache()
    dataset = _make_dataset(tmp_path, "cache_invalidate")
    first = core.prepare(dataset)
    assert dataset.id in core._PREP_CACHE
    assert core.prepare(dataset) is first

    core.invalidate_prepared_cache(dataset.id)
    assert dataset.id not in core._PREP_CACHE
    assert core.prepare(dataset) is not first
