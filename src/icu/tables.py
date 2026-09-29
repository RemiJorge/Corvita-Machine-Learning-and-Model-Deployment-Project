"""Apply the 24 h cutoff and build admission and vitals tables."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from icu.config import load_config
from icu.parse import MEASUREMENTS_FILENAME, OUTCOMES_FILENAME, read_outcomes
from icu.quality import QUALITY_REPORT_FILENAME

logger = logging.getLogger(__name__)

ADMISSION_PARQUET = "admission.parquet"
VITALS_PARQUET = "vitals.parquet"
ADMISSION_PARAMETERS = ("Age", "Gender", "ICUType")


def apply_cutoff(df: pd.DataFrame, cutoff_minutes: int) -> pd.DataFrame:
    """Keep rows at or before the cutoff minute (inclusive).

    Args:
        df: Table with a ``minute`` column.
        cutoff_minutes: Last included minute (e.g. 1440 for 24:00).

    Returns:
        Filtered copy of ``df``.
    """
    return df.loc[df["minute"] <= cutoff_minutes].copy()


def count_cutoff_exclusions(
    cleaned: pd.DataFrame,
    vitals: list[str],
    cutoff_minutes: int,
) -> dict[str, int]:
    """Count vital measurements dropped because they are after the cutoff.

    Args:
        cleaned: Cleaned measurements (all parameters).
        vitals: Vital parameter names.
        cutoff_minutes: Cutoff from config.

    Returns:
        Map ``vital -> count`` of rows with ``minute > cutoff_minutes``.
    """
    vital_df = cleaned.loc[cleaned["parameter"].isin(vitals)]
    after = vital_df.loc[vital_df["minute"] > cutoff_minutes]
    counts: dict[str, int] = {}
    for vital in vitals:
        counts[vital] = int((after["parameter"] == vital).sum())
    return counts


def build_vitals_table(
    cleaned: pd.DataFrame,
    vitals: list[str],
    cutoff_minutes: int,
) -> pd.DataFrame:
    """Build the vitals table for modeling (first 24 h, non-missing values only).

    Args:
        cleaned: Cleaned long measurements.
        vitals: HR, RespRate, Temp.
        cutoff_minutes: Inclusive upper minute bound.

    Returns:
        DataFrame with columns ``record_id``, ``minute``, ``parameter``, ``value``, ``row_order``.
    """
    vital_df = cleaned.loc[cleaned["parameter"].isin(vitals)]
    in_window = apply_cutoff(vital_df, cutoff_minutes)
    used = in_window.loc[in_window["value"].notna()]
    columns = ["record_id", "minute", "parameter", "value", "row_order"]
    return used.loc[:, columns].reset_index(drop=True)


def _descriptor_row(df: pd.DataFrame, parameter: str) -> pd.Series:
    """Return minute-0 descriptor values indexed by ``record_id``."""
    mask = (df["minute"] == 0) & (df["parameter"] == parameter)
    sub = df.loc[mask, ["record_id", "value"]].drop_duplicates(subset=["record_id"], keep="first")
    return sub.set_index("record_id")["value"]


def build_admission_table(
    cleaned: pd.DataFrame,
    outcomes: pd.DataFrame,
) -> pd.DataFrame:
    """Build one admission row per record from minute-0 descriptors and outcomes.

    Args:
        cleaned: Cleaned measurements (descriptor rows at minute 0).
        outcomes: Columns ``record_id``, ``in_hospital_death``.

    Returns:
        DataFrame with ``record_id``, ``age``, ``gender``, ``icu_type``, ``in_hospital_death``.

    Raises:
        ValueError: If the join does not yield exactly one row per outcome record.
    """
    admission = pd.DataFrame({"record_id": outcomes["record_id"].astype(int)})
    admission["age"] = admission["record_id"].map(_descriptor_row(cleaned, "Age"))
    admission["gender"] = admission["record_id"].map(_descriptor_row(cleaned, "Gender"))
    admission["icu_type"] = admission["record_id"].map(_descriptor_row(cleaned, "ICUType"))
    labels = outcomes.set_index("record_id")["in_hospital_death"]
    admission["in_hospital_death"] = admission["record_id"].map(labels).astype(int)
    if len(admission) != len(outcomes):
        msg = "Admission table row count does not match outcomes"
        raise ValueError(msg)
    if admission["record_id"].duplicated().any():
        msg = "Duplicate record_id in admission table"
        raise ValueError(msg)
    return admission.sort_values("record_id").reset_index(drop=True)


def fill_cutoff_quality_fields(
    report: dict[str, Any],
    cleaned: pd.DataFrame,
    vitals_df: pd.DataFrame,
    vitals: list[str],
    cutoff_minutes: int,
) -> None:
    """Fill F3 quality report fields that depend on the 24 h window.

    Args:
        report: Quality report dict (modified in place).
        cleaned: Full cleaned measurements.
        vitals_df: Output vitals table after cutoff and NaN drop.
        vitals: Vital names from config.
        cutoff_minutes: Cutoff from config.
    """
    exclusions = count_cutoff_exclusions(cleaned, vitals, cutoff_minutes)
    all_record_ids = cleaned["record_id"].unique()

    for vital in vitals:
        vital_block = report["vitals"][vital]
        vital_block["n_after_cutoff"] = exclusions.get(vital, 0)
        vital_block["n_measurements_used"] = int((vitals_df["parameter"] == vital).sum())
        in_window = cleaned.loc[
            (cleaned["parameter"] == vital) & (cleaned["minute"] <= cutoff_minutes)
        ]
        has_value = in_window.groupby("record_id")["value"].apply(lambda s: s.notna().any())
        vital_block["records_without_any_value_in_24h"] = int(
            (~has_value.reindex(all_record_ids, fill_value=False)).sum()
        )

    missing_flags: list[pd.Series] = []
    for vital in vitals:
        in_window = cleaned.loc[
            (cleaned["parameter"] == vital) & (cleaned["minute"] <= cutoff_minutes)
        ]
        has_value = in_window.groupby("record_id")["value"].apply(lambda s: s.notna().any())
        missing_flags.append(~has_value.reindex(all_record_ids, fill_value=False))
    all_missing = missing_flags[0]
    for flag in missing_flags[1:]:
        all_missing = all_missing & flag
    report["records_with_all_vitals_missing_in_24h"] = int(all_missing.sum())


def main(config_path: Path | str | None = None) -> None:
    """Build processed tables and merge cutoff stats into the quality report."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = load_config(config_path)
    raw_dir = Path(config["paths"]["raw_dir"])
    interim_dir = Path(config["paths"]["interim_dir"])
    processed_dir = Path(config["paths"]["processed_dir"])
    reports_dir = Path(config["paths"]["reports_dir"])
    cutoff = int(config["cutoff_minutes"])
    vitals: list[str] = list(config["vitals"])

    measurements_path = interim_dir / MEASUREMENTS_FILENAME
    outcomes_path = raw_dir / OUTCOMES_FILENAME
    report_path = reports_dir / QUALITY_REPORT_FILENAME

    cleaned = pd.read_parquet(measurements_path)
    outcomes = read_outcomes(outcomes_path)

    vitals_df = build_vitals_table(cleaned, vitals, cutoff)
    admission_df = build_admission_table(cleaned, outcomes)

    processed_dir.mkdir(parents=True, exist_ok=True)
    vitals_df.to_parquet(processed_dir / VITALS_PARQUET, index=False)
    admission_df.to_parquet(processed_dir / ADMISSION_PARQUET, index=False)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    fill_cutoff_quality_fields(report, cleaned, vitals_df, vitals, cutoff)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    total_excluded = sum(count_cutoff_exclusions(cleaned, vitals, cutoff).values())
    logger.info(
        "Wrote %s (%s rows) and %s (%s rows); %s vital rows excluded after minute %s",
        processed_dir / ADMISSION_PARQUET,
        len(admission_df),
        processed_dir / VITALS_PARQUET,
        len(vitals_df),
        total_excluded,
        cutoff,
    )


if __name__ == "__main__":
    main()
