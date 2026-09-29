"""Tests for measurement cleaning and quality reporting."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from icu import parse, quality
from icu.config import load_config

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture_measurements() -> pd.DataFrame:
    """Parse all fixture record files into one DataFrame."""
    paths = sorted(FIXTURES.glob("9999*.txt"), key=lambda p: p.name)
    rows: list[dict[str, object]] = []
    for path in paths:
        rows.extend(parse.parse_record_file(path))
    return pd.DataFrame(rows)


def test_minus_one_becomes_missing() -> None:
    """Sentinel -1 becomes NaN and is counted for vitals and Gender."""
    df = _fixture_measurements()
    counts: dict[str, int] = {}
    cleaned = quality.apply_minus_one(df, counts)
    hr_minus = cleaned.loc[
        (cleaned["parameter"] == "HR")
        & (cleaned["minute"] == 10)
        & (cleaned["record_id"] == 999901),
        "value",
    ]
    assert np.isnan(hr_minus.iloc[0])
    assert counts.get("HR", 0) >= 1


def test_out_of_bounds_becomes_missing() -> None:
    """HR=0 and Temp=10 are outside physiological bounds and become NaN."""
    config = load_config()
    df = _fixture_measurements()
    after_sentinel = quality.apply_minus_one(df, {})
    oob: dict[str, int] = {}
    cleaned = quality.apply_physiological_bounds(
        after_sentinel,
        list(config["vitals"]),
        config["physiological_bounds"],
        oob,
    )
    hr = cleaned.loc[
        (cleaned["record_id"] == 999902) & (cleaned["parameter"] == "HR"),
        "value",
    ].iloc[0]
    temp = cleaned.loc[
        (cleaned["record_id"] == 999902) & (cleaned["parameter"] == "Temp"),
        "value",
    ].iloc[0]
    assert np.isnan(hr)
    assert np.isnan(temp)
    assert oob.get("HR", 0) >= 1
    assert oob.get("Temp", 0) >= 1


def test_exact_duplicates_dropped() -> None:
    """Two identical HR rows at the same minute collapse to one."""
    config = load_config()
    path = FIXTURES / "999903.txt"
    df = pd.DataFrame(parse.parse_record_file(path))
    dup_counts: dict[str, int] = {}
    cleaned = quality.drop_exact_duplicates(df, list(config["vitals"]), dup_counts)
    hr_rows = cleaned[(cleaned["parameter"] == "HR") & (cleaned["minute"] == 15)]
    assert len(hr_rows) == 1
    assert dup_counts.get("HR", 0) == 1
