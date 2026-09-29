"""Tests for feature computation (F4)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from icu import features, parse, quality, tables
from icu.config import load_config
from icu.features import FEATURE_COLUMNS, FORBIDDEN_COLUMNS

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _tables_from_fixture(
    record_path: Path,
    outcomes_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse one fixture record and build admission and vitals tables."""
    config = load_config()
    raw = pd.DataFrame(parse.parse_record_file(record_path))
    cleaned, _ = quality.clean_measurements(raw, config)
    outcomes = parse.read_outcomes(outcomes_path)
    outcomes = outcomes.loc[outcomes["record_id"] == int(record_path.stem)]
    vitals = list(config["vitals"])
    cutoff = int(config["cutoff_minutes"])
    vitals_df = tables.build_vitals_table(cleaned, vitals, cutoff)
    admission_df = tables.build_admission_table(cleaned, outcomes)
    return admission_df, vitals_df


def test_features_fixture_values() -> None:
    """Exact expected values on synthetic fixture records."""
    outcomes_path = FIXTURES / "Outcomes-fixtures.txt"

    admission, vitals = _tables_from_fixture(FIXTURES / "999901.txt", outcomes_path)
    row = features.compute_features(admission, vitals).iloc[0]
    assert float(row["age"]) == 40.0
    assert float(row["gender_male"]) == 1.0
    assert int(row["gender_missing"]) == 0
    assert int(row["icu_type_2"]) == 1
    assert int(row["hr_count"]) == 0
    assert int(row["hr_missing"]) == 1
    assert np.isnan(row["hr_mean"])
    assert int(row["resp_rate_count"]) == 1
    assert float(row["resp_rate_mean"]) == 18.0
    assert float(row["resp_rate_last"]) == 18.0
    assert int(row["resp_rate_missing"]) == 0
    assert float(row["temp_last"]) == 36.5

    admission, vitals = _tables_from_fixture(FIXTURES / "999902.txt", outcomes_path)
    row = features.compute_features(admission, vitals).iloc[0]
    assert float(row["gender_male"]) == 0.0
    assert int(row["icu_type_3"]) == 1
    assert int(row["hr_missing"]) == 1
    assert int(row["resp_rate_count"]) == 1
    assert float(row["resp_rate_last"]) == 20.0
    assert int(row["temp_missing"]) == 1

    admission, vitals = _tables_from_fixture(FIXTURES / "999904.txt", outcomes_path)
    row = features.compute_features(admission, vitals).iloc[0]
    assert int(row["icu_type_4"]) == 1
    assert int(row["hr_count"]) == 1
    assert float(row["hr_last"]) == 90.0
    assert int(row["resp_rate_missing"]) == 1
    assert int(row["temp_missing"]) == 1


def test_features_missing_vital() -> None:
    """No RespRate: count 0, mean and last NaN, flag 1."""
    admission = pd.DataFrame(
        {
            "record_id": [1],
            "age": [50.0],
            "gender": [1.0],
            "icu_type": [2.0],
            "in_hospital_death": [0],
        }
    )
    vitals = pd.DataFrame(
        {
            "record_id": [1, 1],
            "minute": [10, 20],
            "parameter": ["HR", "Temp"],
            "value": [80.0, 37.0],
            "row_order": [1, 2],
        }
    )
    row = features.compute_features(admission, vitals).iloc[0]
    assert int(row["resp_rate_count"]) == 0
    assert np.isnan(row["resp_rate_mean"])
    assert np.isnan(row["resp_rate_last"])
    assert int(row["resp_rate_missing"]) == 1


def test_features_last_value_tiebreak() -> None:
    """Same minute: higher row_order wins for last value."""
    admission = pd.DataFrame(
        {
            "record_id": [1],
            "age": [50.0],
            "gender": [0.0],
            "icu_type": [1.0],
        }
    )
    vitals = pd.DataFrame(
        {
            "record_id": [1, 1],
            "minute": [30, 30],
            "parameter": ["HR", "HR"],
            "value": [70.0, 72.0],
            "row_order": [1, 5],
        }
    )
    row = features.compute_features(admission, vitals).iloc[0]
    assert float(row["hr_last"]) == 72.0
    assert float(row["hr_mean"]) == 71.0
    assert int(row["hr_count"]) == 2


def test_features_columns_and_order() -> None:
    """Output columns equal FEATURE_COLUMNS in order."""
    admission = pd.DataFrame(
        {
            "record_id": [1],
            "age": [30.0],
            "gender": [np.nan],
            "icu_type": [np.nan],
        }
    )
    vitals = pd.DataFrame(columns=["record_id", "minute", "parameter", "value", "row_order"])
    out = features.compute_features(admission, vitals)
    assert list(out.columns) == FEATURE_COLUMNS


def test_no_forbidden_columns() -> None:
    """Label and forbidden names never appear in feature output."""
    admission = pd.DataFrame(
        {
            "record_id": [1],
            "age": [40.0],
            "gender": [1.0],
            "icu_type": [2.0],
            "in_hospital_death": [1],
        }
    )
    vitals = pd.DataFrame(
        {
            "record_id": [1],
            "minute": [5],
            "parameter": ["HR"],
            "value": [90.0],
            "row_order": [1],
        }
    )
    out = features.compute_features(admission, vitals)
    assert not (set(out.columns) & FORBIDDEN_COLUMNS)
    assert "in_hospital_death" not in out.columns
