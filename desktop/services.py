"""Thin service layer between the Qt UI and the ``vdas`` analysis engine.

Caches ``PreparedData`` per dataset (keyed by file mtime) so repeated view
switches don't re-read large parquet files.
"""
from __future__ import annotations

import os

from vdas import datasets as ds_mod
from vdas.analysis import PreparedData, prepare
from vdas.datasets import Dataset

_CACHE: dict[int, tuple[float, PreparedData]] = {}


def get_prepared(dataset: Dataset) -> PreparedData:
    try:
        mtime = os.path.getmtime(dataset.path)
    except OSError:
        mtime = 0.0
    hit = _CACHE.get(dataset.id)
    if hit and hit[0] == mtime:
        return hit[1]
    pdd = prepare(dataset)
    _CACHE[dataset.id] = (mtime, pdd)
    return pdd


def invalidate(dataset_id: int | None = None) -> None:
    if dataset_id is None:
        _CACHE.clear()
    else:
        _CACHE.pop(dataset_id, None)


def refresh_dataset(dataset_id: int) -> Dataset | None:
    invalidate(dataset_id)
    return ds_mod.get_dataset(dataset_id)
