"""Tests for 24 h cutoff and admission/vitals tables."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from icu import parse, quality, tables
from icu.config import load_config

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_cutoff_keeps_1440() -> None:
    """Measurement at minute 1440 (24:00) is kept."""
    df = pd.DataFrame(
        {
            "record_id": [1],
            "minute": [1440],
            "parameter": ["HR"],
            "value": [80.0],
            "row_order": [1],
        }
    )
    out = tables.apply_cutoff(df, 1440)
    assert len(out) == 1
    assert int(out.iloc[0]["minute"]) == 1440


def test_cutoff_drops_1441() -> None:
    """Measurement at minute 1441 is dropped and counted as after cutoff."""
    df = pd.DataFrame(
        {
            "record_id": [1, 1],
            "minute": [1440, 1441],
            "parameter": ["HR", "HR"],
            "value": [80.0, 81.0],
            "row_order": [1, 2],
        }
    )
    out = tables.apply_cutoff(df, 1440)
    assert list(out["minute"]) == [1440]
    counts = tables.count_cutoff_exclusions(df, ["HR"], 1440)
    assert counts["HR"] == 1


def test_admission_from_descriptors_only() -> None:
    """Admission fields come from minute 0 descriptor rows only."""
    cleaned = pd.DataFrame(
        {
            "record_id": [100, 100, 100],
            "minute": [0, 60, 0],
            "parameter": ["Age", "Age", "Gender"],
            "value": [50.0, 99.0, 1.0],
            "row_order": [1, 2, 3],
        }
    )
    outcomes = pd.DataFrame({"record_id": [100], "in_hospital_death": [0]})
    admission = tables.build_admission_table(cleaned, outcomes)
    assert float(admission.iloc[0]["age"]) == 50.0
    assert float(admission.iloc[0]["gender"]) == 1.0


def test_vitals_fixture_after_cutoff() -> None:
    """Fixture 999904: in-window HR kept, post-cutoff HR and Temp excluded."""
    config = load_config()
    path = FIXTURES / "999904.txt"
    raw = pd.DataFrame(parse.parse_record_file(path))
    cleaned, _ = quality.clean_measurements(raw, config)
    vitals = list(config["vitals"])
    cutoff = int(config["cutoff_minutes"])
    vitals_df = tables.build_vitals_table(cleaned, vitals, cutoff)
    hr = vitals_df.loc[vitals_df["parameter"] == "HR"]
    assert len(hr) == 1
    assert int(hr.iloc[0]["minute"]) == 23 * 60 + 59
    assert vitals_df["minute"].max() <= cutoff
    counts = tables.count_cutoff_exclusions(cleaned, vitals, cutoff)
    assert counts["HR"] >= 1
    assert counts["Temp"] >= 1
