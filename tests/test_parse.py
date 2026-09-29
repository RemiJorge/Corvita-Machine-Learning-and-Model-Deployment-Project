"""Tests for PhysioNet record parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from icu import parse

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_time_to_minutes() -> None:
    """Elapsed times convert to minutes; invalid minute part raises."""
    assert parse.time_to_minutes("00:00") == 0
    assert parse.time_to_minutes("24:00") == 1440
    assert parse.time_to_minutes("47:59") == 2879
    with pytest.raises(parse.ParseError):
        parse.time_to_minutes("12:60")


def test_parse_fixture_file() -> None:
    """Synthetic record file yields expected rows and row_order."""
    path = FIXTURES / "999901.txt"
    rows = parse.parse_record_file(path)
    assert len(rows) == 9
    hr_row = next(r for r in rows if r["parameter"] == "HR" and r["minute"] == 10)
    assert hr_row["value"] == -1.0
    assert hr_row["row_order"] == 6
    assert all(r["record_id"] == 999901 for r in rows)


def test_record_id_mismatch_raises(tmp_path: Path) -> None:
    """Descriptor RecordID must match the file name."""
    bad = tmp_path / "100.txt"
    bad.write_text(
        "Time,Parameter,Value\n00:00,RecordID,999\n00:00,Age,50\n",
        encoding="utf-8",
    )
    with pytest.raises(parse.ParseError, match="does not match file name"):
        parse.parse_record_file(bad)


def test_outcomes_join_one_to_one() -> None:
    """Real set A: file count, outcomes, and record_id join are one-to-one."""
    raw_dir = Path("data/raw")
    set_a = raw_dir / "set-a"
    outcomes_path = raw_dir / "Outcomes-a.txt"
    if not set_a.is_dir() or not outcomes_path.is_file():
        pytest.skip("Real PhysioNet data not present")
    measurements, outcomes = parse.parse_all(set_a, outcomes_path)
    n_files = len(list(set_a.glob("*.txt")))
    parse.assert_parse_integrity(measurements, outcomes, n_files)


@pytest.mark.data
def test_outcomes_join_one_to_one_marked() -> None:
    """Wrapper so ``pytest -m data`` runs the real-data integrity check."""
    test_outcomes_join_one_to_one()
