"""Tests for stratified RecordID split (F5)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from icu.config import load_config
from icu.split import stratified_split, write_split_csv
from icu.tables import ADMISSION_PARQUET


def test_split_no_overlap_and_complete() -> None:
    """Train, val, and test are disjoint and cover all record IDs."""
    n = 200
    rng = np.random.default_rng(0)
    record_ids = list(range(1000, 1000 + n))
    labels = rng.integers(0, 2, size=n).tolist()
    train, val, test = stratified_split(record_ids, labels, 0.70, 0.15, 0.15, seed=42)
    train_set = set(train)
    val_set = set(val)
    test_set = set(test)
    assert train_set.isdisjoint(val_set)
    assert train_set.isdisjoint(test_set)
    assert val_set.isdisjoint(test_set)
    assert train_set | val_set | test_set == set(record_ids)
    assert train == sorted(train)
    assert val == sorted(val)
    assert test == sorted(test)


def test_split_deterministic(tmp_path: Path) -> None:
    """Two runs with the same seed produce identical ID lists and CSV bytes."""
    record_ids = list(range(500))
    labels = [i % 7 == 0 for i in record_ids]
    labels = [int(x) for x in labels]
    first = stratified_split(record_ids, labels, 0.70, 0.15, 0.15, seed=42)
    second = stratified_split(record_ids, labels, 0.70, 0.15, 0.15, seed=42)
    assert first == second

    write_split_csv(tmp_path / "a" / "train_ids.csv", first[0])
    write_split_csv(tmp_path / "b" / "train_ids.csv", second[0])
    assert (tmp_path / "a" / "train_ids.csv").read_bytes() == (
        tmp_path / "b" / "train_ids.csv"
    ).read_bytes()


@pytest.mark.data
def test_split_death_rates_close() -> None:
    """Death rates of train, val, and test are within one percentage point."""
    config = load_config()
    admission_path = Path(config["paths"]["processed_dir"]) / ADMISSION_PARQUET
    if not admission_path.is_file():
        pytest.skip("Real admission table not present")

    admission = pd.read_parquet(admission_path, columns=["record_id", "in_hospital_death"])
    record_ids = admission["record_id"].astype(int).tolist()
    labels = admission["in_hospital_death"].astype(int).tolist()
    split_cfg = config["split"]
    train_ids, val_ids, test_ids = stratified_split(
        record_ids,
        labels,
        float(split_cfg["train"]),
        float(split_cfg["val"]),
        float(split_cfg["test"]),
        int(config["seed"]),
    )
    label_by_id = admission.set_index("record_id")["in_hospital_death"]
    rates = [
        float(label_by_id.loc[train_ids].mean()),
        float(label_by_id.loc[val_ids].mean()),
        float(label_by_id.loc[test_ids].mean()),
    ]
    assert max(rates) - min(rates) <= 0.01
