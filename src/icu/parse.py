"""Parse raw PhysioNet text files into a long measurements table."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from icu.config import load_config

logger = logging.getLogger(__name__)

TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")
OUTCOMES_FILENAME = "Outcomes-a.txt"
SET_A_DIR_NAME = "set-a"
MEASUREMENTS_FILENAME = "measurements.parquet"


class ParseError(ValueError):
    """Raised when a record file line fails validation."""


def time_to_minutes(time_str: str) -> int:
    """Convert an elapsed ICU time string to integer minutes since admission.

    Args:
        time_str: Time in ``HH:MM`` format (hours may exceed 24).

    Returns:
        Minutes as ``int(hh) * 60 + int(mm)``.

    Raises:
        ParseError: If the string is not ``HH:MM``, or the minutes part is 60 or more.
    """
    if not TIME_PATTERN.match(time_str):
        msg = f"Invalid time format (expected HH:MM): {time_str!r}"
        raise ParseError(msg)
    hours_str, minutes_str = time_str.split(":", 1)
    minutes_part = int(minutes_str)
    if minutes_part >= 60:
        msg = f"Invalid time (minutes must be 0-59): {time_str!r}"
        raise ParseError(msg)
    return int(hours_str) * 60 + minutes_part


def parse_record_file(path: Path) -> list[dict[str, object]]:
    """Parse one PhysioNet record file into measurement rows.

    Args:
        path: Path to ``<RecordID>.txt``.

    Returns:
        List of dicts with keys ``record_id``, ``minute``, ``parameter``, ``value``,
        ``row_order`` (0-based line index after the header).

    Raises:
        ParseError: On time, value, or RecordID mismatch errors (includes file and line).
        ValueError: If the file name is not ``<integer>.txt``.
    """
    stem = path.stem
    if not stem.isdigit():
        msg = f"Record file name must be <RecordID>.txt: {path.name}"
        raise ValueError(msg)
    record_id_from_name = int(stem)
    rows: list[dict[str, object]] = []
    descriptor_record_id: int | None = None

    with path.open(encoding="utf-8") as handle:
        header = handle.readline()
        if not header.strip().startswith("Time,Parameter,Value"):
            msg = f"{path}: line 1: expected CSV header Time,Parameter,Value"
            raise ParseError(msg)
        for line_number, raw_line in enumerate(handle, start=2):
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split(",", 2)
            if len(parts) != 3:
                msg = f"{path}: line {line_number}: expected Time,Parameter,Value"
                raise ParseError(msg)
            time_str, parameter, value_str = parts[0].strip(), parts[1].strip(), parts[2].strip()
            try:
                minute = time_to_minutes(time_str)
            except ParseError as exc:
                msg = f"{path}: line {line_number}: {exc}"
                raise ParseError(msg) from exc
            try:
                value = float(value_str)
            except ValueError as exc:
                msg = f"{path}: line {line_number}: non-numeric value: {value_str!r}"
                raise ParseError(msg) from exc

            if parameter == "RecordID" and minute == 0:
                descriptor_record_id = int(value)
                if descriptor_record_id != record_id_from_name:
                    msg = (
                        f"{path}: line {line_number}: RecordID {descriptor_record_id} "
                        f"does not match file name {record_id_from_name}"
                    )
                    raise ParseError(msg)

            rows.append(
                {
                    "record_id": record_id_from_name,
                    "minute": minute,
                    "parameter": parameter,
                    "value": value,
                    "row_order": line_number - 2,
                }
            )

    if descriptor_record_id is None:
        msg = f"{path}: missing 00:00,RecordID descriptor row"
        raise ParseError(msg)

    return rows


def read_outcomes(path: Path) -> pd.DataFrame:
    """Read outcome labels from ``Outcomes-a.txt``.

    Args:
        path: Path to the outcomes CSV.

    Returns:
        DataFrame with columns ``record_id`` (int) and ``in_hospital_death`` (int).

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If ``In-hospital_death`` contains values other than 0 or 1.
    """
    df = pd.read_csv(path)
    required = {"RecordID", "In-hospital_death"}
    if not required.issubset(df.columns):
        missing = required - set(df.columns)
        msg = f"Outcomes file missing columns: {sorted(missing)}"
        raise ValueError(msg)
    out = df[["RecordID", "In-hospital_death"]].rename(
        columns={"RecordID": "record_id", "In-hospital_death": "in_hospital_death"}
    )
    out["record_id"] = out["record_id"].astype(int)
    out["in_hospital_death"] = out["in_hospital_death"].astype(int)
    invalid = ~out["in_hospital_death"].isin([0, 1])
    if invalid.any():
        msg = "In-hospital_death must contain only 0 and 1"
        raise ValueError(msg)
    return out


def assert_parse_integrity(
    measurements: pd.DataFrame,
    outcomes: pd.DataFrame,
    n_record_files: int,
) -> None:
    """Assert one-to-one alignment between files, measurements, and outcomes.

    Args:
        measurements: Parsed long table.
        outcomes: Outcome labels.
        n_record_files: Number of ``*.txt`` files parsed.

    Raises:
        AssertionError: If counts or joins do not match the data spec.
    """
    n_distinct = measurements["record_id"].nunique()
    assert n_record_files == n_distinct, (
        f"record files ({n_record_files}) != distinct record_id ({n_distinct})"
    )
    assert len(outcomes) == n_record_files, (
        f"outcome rows ({len(outcomes)}) != record files ({n_record_files})"
    )
    merged = outcomes.merge(
        measurements[["record_id"]].drop_duplicates(),
        on="record_id",
        how="outer",
        indicator=True,
    )
    if not (merged["_merge"] == "both").all():
        msg = "record_id join between outcomes and measurements is not one-to-one"
        raise AssertionError(msg)
    if outcomes["record_id"].duplicated().any():
        raise AssertionError("duplicate RecordID in outcomes file")


def parse_all(raw_set_a_dir: Path, outcomes_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse every record file and load outcomes.

    Args:
        raw_set_a_dir: Directory containing ``*.txt`` record files.
        outcomes_path: Path to ``Outcomes-a.txt``.

    Returns:
        Tuple of (measurements DataFrame, outcomes DataFrame).

    Raises:
        FileNotFoundError: If directories or outcomes file are missing.
        ParseError: On malformed record lines.
    """
    paths = sorted(raw_set_a_dir.glob("*.txt"), key=lambda p: p.name)
    if not paths:
        msg = f"No record files found in {raw_set_a_dir}"
        raise FileNotFoundError(msg)
    all_rows: list[dict[str, object]] = []
    for path in paths:
        all_rows.extend(parse_record_file(path))
    measurements = pd.DataFrame(all_rows)
    measurements["parameter"] = measurements["parameter"].astype(str)
    outcomes = read_outcomes(outcomes_path)
    assert_parse_integrity(measurements, outcomes, len(paths))
    return measurements, outcomes


def main(config_path: Path | str | None = None) -> None:
    """Parse raw set A into ``data/interim/measurements.parquet``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = load_config(config_path)
    raw_dir = Path(config["paths"]["raw_dir"])
    interim_dir = Path(config["paths"]["interim_dir"])
    set_a_dir = raw_dir / SET_A_DIR_NAME
    outcomes_path = raw_dir / OUTCOMES_FILENAME
    output_path = interim_dir / MEASUREMENTS_FILENAME

    measurements, outcomes = parse_all(set_a_dir, outcomes_path)
    interim_dir.mkdir(parents=True, exist_ok=True)
    measurements.to_parquet(output_path, index=False)

    n_records = outcomes["record_id"].nunique()
    n_deaths = int(outcomes["in_hospital_death"].sum())
    death_rate = n_deaths / n_records if n_records else 0.0
    logger.info(
        "Parsed %s record files, %s measurement rows; death rate %.4f (%s / %s)",
        n_records,
        len(measurements),
        death_rate,
        n_deaths,
        n_records,
    )


if __name__ == "__main__":
    main()
