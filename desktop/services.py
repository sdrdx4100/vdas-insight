"""Thin service layer between the Qt UI and the ``vdas`` analysis engine.

Prepared-frame caching is owned by ``vdas.analysis.core`` so role changes,
derived-signal edits and file updates all use one self-invalidating cache.
"""
from __future__ import annotations

from vdas import datasets as ds_mod
from vdas.analysis import PreparedData, invalidate_prepared_cache, prepare
from vdas.datasets import Dataset


def get_prepared(dataset: Dataset) -> PreparedData:
    return prepare(dataset)


def invalidate(dataset_id: int | None = None) -> None:
    invalidate_prepared_cache(dataset_id)


def refresh_dataset(dataset_id: int) -> Dataset | None:
    invalidate(dataset_id)
    return ds_mod.get_dataset(dataset_id)
