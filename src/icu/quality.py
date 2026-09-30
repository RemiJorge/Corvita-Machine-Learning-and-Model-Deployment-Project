"""Apply physiological bounds, handle sentinel values, and build the data quality report."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from icu.config import load_config
from icu.parse import MEASUREMENTS_FILENAME, OUTCOMES_FILENAME, read_outcomes

logger = logging.getLogger(__name__)

QUALITY_REPORT_FILENAME = "data_quality.json"
PERCENTILE_KEYS = ("p0.1", "p1", "p50", "p99", "p99.9")
PERCENTILE_QUANTILES = (0.001, 0.01, 0.5, 0.99, 0.999)


def compute_percentiles(series: pd.Series) -> dict[str, float]:
    """Compute fixed percentiles for a numeric series (finite values only).

    Args:
        series: Values to summarize.

    Returns:
        Dict with keys ``p0.1``, ``p1``, ``p50``, ``p99``, ``p99.9``. Empty if no data.
    """
    values = series.dropna().astype(float)
    if values.empty:
        return {}
    quantiles = values.quantile(list(PERCENTILE_QUANTILES))
    return {key: float(quantiles.iloc[i]) for i, key in enumerate(PERCENTILE_KEYS)}


def apply_minus_one(
    df: pd.DataFrame,
    counts: dict[str, int],
) -> pd.DataFrame:
    """Replace sentinel ``-1`` with NaN and count occurrences per parameter.

    Args:
        df: Measurements with a ``value`` column.
        counts: Map ``parameter -> count`` updated in place.

    Returns:
        Copy of ``df`` with ``-1`` values set to NaN.
    """
    out = df.copy()
    mask = out["value"] == -1
    if mask.any():
        for param, n in out.loc[mask, "parameter"].value_counts().items():
            counts[str(param)] = counts.get(str(param), 0) + int(n)
    out.loc[mask, "value"] = np.nan
    return out


def apply_physiological_bounds(
    df: pd.DataFrame,
    vitals: list[str],
    bounds: dict[str, list[float]],
    counts: dict[str, int],
) -> pd.DataFrame:
    """Set vital values outside inclusive physiological bounds to NaN.

    Args:
        df: Measurements table.
        vitals: Vital parameter names to check.
        bounds: Config map ``parameter -> [low, high]`` inclusive.
        counts: Per-vital out-of-bounds counts updated in place.

    Returns:
        Copy with out-of-range vital values set to NaN.
    """
    out = df.copy()
    for vital in vitals:
        low, high = bounds[vital]
        vital_mask = out["parameter"] == vital
        values = out.loc[vital_mask, "value"]
        finite = values.notna()
        oob = finite & ((values < low) | (values > high))
        n_oob = int(oob.sum())
        if n_oob:
            counts[vital] = counts.get(vital, 0) + n_oob
            out.loc[vital_mask & oob, "value"] = np.nan
    return out


def apply_admission_bounds(
    df: pd.DataFrame,
    admission_bounds: dict[str, list[int]],
    counts: dict[str, int],
) -> pd.DataFrame:
    """Invalidate admission descriptors at minute 0 outside allowed ranges.

    Args:
        df: Measurements table.
        admission_bounds: Config with at least ``Age`` as ``[low, high]`` inclusive.
        counts: Per-field out-of-bounds counts updated in place.

    Returns:
        Copy with invalid admission values set to NaN.
    """
    out = df.copy()
    desc = out["minute"] == 0

    age_low, age_high = admission_bounds["Age"]
    age_mask = desc & (out["parameter"] == "Age")
    age_values = out.loc[age_mask, "value"]
    age_oob = age_values.notna() & ((age_values < age_low) | (age_values > age_high))
    counts["Age"] = int(age_oob.sum())
    out.loc[age_mask & age_oob, "value"] = np.nan

    gender_mask = desc & (out["parameter"] == "Gender")
    gender_values = out.loc[gender_mask, "value"]
    gender_oob = gender_values.notna() & ~gender_values.isin([0.0, 1.0])
    counts["Gender"] = int(gender_oob.sum())
    out.loc[gender_mask & gender_oob, "value"] = np.nan

    icu_mask = desc & (out["parameter"] == "ICUType")
    icu_values = out.loc[icu_mask, "value"]
    icu_oob = icu_values.notna() & ~icu_values.isin([1.0, 2.0, 3.0, 4.0])
    counts["ICUType"] = int(icu_oob.sum())
    out.loc[icu_mask & icu_oob, "value"] = np.nan

    return out


def drop_exact_duplicates(
    df: pd.DataFrame,
    vitals: list[str],
    counts: dict[str, int],
) -> pd.DataFrame:
    """Drop exact duplicate measurement rows and count duplicates per vital.

    Args:
        df: Measurements table.
        vitals: Vital names for duplicate counts.
        counts: Per-vital duplicate row counts updated in place.

    Returns:
        Deduplicated table (lowest ``row_order`` kept).
    """
    sorted_df = df.sort_values(["record_id", "minute", "parameter", "value", "row_order"])
    subset = ["record_id", "minute", "parameter", "value"]
    dup_mask = sorted_df.duplicated(subset=subset, keep="first")
    for vital in vitals:
        vital_dups = dup_mask & (sorted_df["parameter"] == vital)
        counts[vital] = int(vital_dups.sum())
    return sorted_df.loc[~dup_mask].reset_index(drop=True)


def _descriptor_row(df: pd.DataFrame, parameter: str) -> pd.Series:
    """Return minute-0 descriptor values indexed by ``record_id``."""
    mask = (df["minute"] == 0) & (df["parameter"] == parameter)
    sub = df.loc[mask, ["record_id", "value"]].drop_duplicates(subset=["record_id"], keep="first")
    return sub.set_index("record_id")["value"]


def build_quality_report(
    measurements_raw: pd.DataFrame,
    measurements_clean: pd.DataFrame,
    outcomes: pd.DataFrame,
    config: dict[str, Any],
    *,
    minus_one_counts: dict[str, int],
    vital_oob_counts: dict[str, int],
    admission_oob_counts: dict[str, int],
    duplicate_counts: dict[str, int],
    vital_percentiles: dict[str, dict[str, float]],
    age_percentiles: dict[str, float],
) -> dict[str, Any]:
    """Assemble the JSON quality report from spec section 6."""
    vitals: list[str] = list(config["vitals"])
    n_records = int(outcomes["record_id"].nunique())
    n_deaths = int(outcomes["in_hospital_death"].sum())
    death_rate = n_deaths / n_records if n_records else 0.0

    age_series = _descriptor_row(measurements_clean, "Age")
    gender_series = _descriptor_row(measurements_clean, "Gender")
    icu_series = _descriptor_row(measurements_clean, "ICUType")

    descriptors: dict[str, Any] = {
        "Age": {
            "missing": int(age_series.isna().sum()),
            "out_of_bounds": admission_oob_counts.get("Age", 0),
            "percentiles": age_percentiles,
        },
        "Gender": {
            "missing": int(gender_series.isna().sum()),
            "counts": {
                "0": int((gender_series == 0).sum()),
                "1": int((gender_series == 1).sum()),
            },
        },
        "ICUType": {
            "missing": int(icu_series.isna().sum()),
            "counts": {
                "1": int((icu_series == 1).sum()),
                "2": int((icu_series == 2).sum()),
                "3": int((icu_series == 3).sum()),
                "4": int((icu_series == 4).sum()),
            },
        },
    }

    vitals_report: dict[str, Any] = {}
    for vital in vitals:
        raw_n = int((measurements_raw["parameter"] == vital).sum())
        vitals_report[vital] = {
            "n_measurements_raw": raw_n,
            "n_minus_one": minus_one_counts.get(vital, 0),
            "n_out_of_bounds": vital_oob_counts.get(vital, 0),
            "n_exact_duplicates": duplicate_counts.get(vital, 0),
            "n_after_cutoff": 0,
            "n_measurements_used": 0,
            "records_without_any_value_in_24h": 0,
            "percentiles": vital_percentiles.get(vital, {}),
        }

    return {
        "n_records": n_records,
        "n_deaths": n_deaths,
        "death_rate": death_rate,
        "descriptors": descriptors,
        "vitals": vitals_report,
        "records_with_all_vitals_missing_in_24h": 0,
    }


def clean_measurements(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply all F2 cleaning rules and collect counts for the quality report.

    Args:
        df: Parsed measurements (raw floats, including ``-1``).
        config: Loaded project config.

    Returns:
        Tuple of (cleaned DataFrame, context dict with counts and percentiles).
    """
    vitals: list[str] = list(config["vitals"])
    minus_one_counts: dict[str, int] = {}
    after_minus_one = apply_minus_one(df, minus_one_counts)

    vital_percentiles: dict[str, dict[str, float]] = {}
    for vital in vitals:
        vital_values = after_minus_one.loc[after_minus_one["parameter"] == vital, "value"]
        vital_percentiles[vital] = compute_percentiles(vital_values)

    age_percentiles = compute_percentiles(
        after_minus_one.loc[
            (after_minus_one["minute"] == 0) & (after_minus_one["parameter"] == "Age"),
            "value",
        ]
    )

    vital_oob: dict[str, int] = {}
    after_bounds = apply_physiological_bounds(
        after_minus_one,
        vitals,
        config["physiological_bounds"],
        vital_oob,
    )
    admission_oob: dict[str, int] = {}
    after_admission = apply_admission_bounds(
        after_bounds, config["admission_bounds"], admission_oob
    )

    dup_counts: dict[str, int] = {}
    cleaned = drop_exact_duplicates(after_admission, vitals, dup_counts)

    context = {
        "minus_one_counts": minus_one_counts,
        "vital_oob_counts": vital_oob,
        "admission_oob_counts": admission_oob,
        "duplicate_counts": dup_counts,
        "vital_percentiles": vital_percentiles,
        "age_percentiles": age_percentiles,
    }
    return cleaned, context


def main(config_path: Path | str | None = None) -> None:
    """Clean measurements and write ``reports/data_quality.json``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = load_config(config_path)
    raw_dir = Path(config["paths"]["raw_dir"])
    interim_dir = Path(config["paths"]["interim_dir"])
    reports_dir = Path(config["paths"]["reports_dir"])
    measurements_path = interim_dir / MEASUREMENTS_FILENAME
    outcomes_path = raw_dir / OUTCOMES_FILENAME
    report_path = reports_dir / QUALITY_REPORT_FILENAME

    raw_df = pd.read_parquet(measurements_path)
    outcomes = read_outcomes(outcomes_path)
    cleaned, ctx = clean_measurements(raw_df, config)
    report = build_quality_report(
        raw_df,
        cleaned,
        outcomes,
        config,
        minus_one_counts=ctx["minus_one_counts"],
        vital_oob_counts=ctx["vital_oob_counts"],
        admission_oob_counts=ctx["admission_oob_counts"],
        duplicate_counts=ctx["duplicate_counts"],
        vital_percentiles=ctx["vital_percentiles"],
        age_percentiles=ctx["age_percentiles"],
    )

    cleaned.to_parquet(measurements_path, index=False)
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    logger.info(
        "Wrote quality report %s (%s records, death rate %.4f)",
        report_path,
        report["n_records"],
        report["death_rate"],
    )


if __name__ == "__main__":
    main()
