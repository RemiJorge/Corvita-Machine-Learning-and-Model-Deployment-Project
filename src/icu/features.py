"""Compute model features shared by training and the prediction API."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from icu.config import load_config
from icu.tables import ADMISSION_PARQUET, VITALS_PARQUET

logger = logging.getLogger(__name__)

FEATURES_PARQUET = "features.parquet"

FEATURE_COLUMNS: list[str] = [
    "age",
    "gender_male",
    "gender_missing",
    "icu_type_1",
    "icu_type_2",
    "icu_type_3",
    "icu_type_4",
    "hr_count",
    "hr_mean",
    "hr_last",
    "hr_missing",
    "resp_rate_count",
    "resp_rate_mean",
    "resp_rate_last",
    "resp_rate_missing",
    "temp_count",
    "temp_mean",
    "temp_last",
    "temp_missing",
]

FORBIDDEN_COLUMNS: frozenset[str] = frozenset(
    {
        "SAPS-I",
        "SOFA",
        "Length_of_stay",
        "Survival",
        "In-hospital_death",
        "in_hospital_death",
    }
)

_VITAL_TO_PREFIX: dict[str, str] = {
    "HR": "hr",
    "RespRate": "resp_rate",
    "Temp": "temp",
}


def _admission_features(admission_df: pd.DataFrame) -> pd.DataFrame:
    """Build admission-derived feature columns indexed by ``record_id``."""
    admission = admission_df.sort_values("record_id").reset_index(drop=True)
    record_ids = admission["record_id"].astype(int)

    age = pd.to_numeric(admission["age"], errors="coerce").astype(float)
    gender = pd.to_numeric(admission["gender"], errors="coerce")

    gender_missing = gender.isna().astype(int)
    gender_male = np.where(gender.isna(), np.nan, np.where(gender == 1.0, 1.0, 0.0))

    icu_type = pd.to_numeric(admission["icu_type"], errors="coerce")
    icu_missing = icu_type.isna()
    icu_int = icu_type.fillna(-1).astype(int)

    out = pd.DataFrame({"record_id": record_ids})
    out["age"] = age.values
    out["gender_male"] = gender_male
    out["gender_missing"] = gender_missing.values
    for k in (1, 2, 3, 4):
        out[f"icu_type_{k}"] = np.where(icu_missing, 0, (icu_int == k).astype(int))

    return out


def _vital_features(
    vitals_df: pd.DataFrame,
    record_ids: pd.Series,
    parameter: str,
    prefix: str,
) -> pd.DataFrame:
    """Aggregate one vital for all records in ``record_ids``."""
    sub = vitals_df.loc[vitals_df["parameter"] == parameter]
    if sub.empty:
        counts = pd.Series(0, index=record_ids, dtype=int)
        means = pd.Series(np.nan, index=record_ids, dtype=float)
        lasts = pd.Series(np.nan, index=record_ids, dtype=float)
    else:
        ordered = sub.sort_values(["record_id", "minute", "row_order"])
        grouped = ordered.groupby("record_id", sort=False)
        counts = grouped.size().reindex(record_ids, fill_value=0).astype(int)
        means = grouped["value"].mean().reindex(record_ids)
        lasts = grouped["value"].last().reindex(record_ids)

    missing = (counts == 0).astype(int)
    return pd.DataFrame(
        {
            f"{prefix}_count": counts.values,
            f"{prefix}_mean": means.values,
            f"{prefix}_last": lasts.values,
            f"{prefix}_missing": missing.values,
        }
    )


def compute_features(admission_df: pd.DataFrame, vitals_df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per record_id with the columns of FEATURE_COLUMNS, in order.

    Args:
        admission_df: One row per record with ``record_id``, ``age``, ``gender``, ``icu_type``.
            May include ``in_hospital_death``; it is not used as a feature.
        vitals_df: Long vitals table with ``record_id``, ``minute``, ``parameter``, ``value``,
            ``row_order``.

    Returns:
        Feature matrix with exactly ``FEATURE_COLUMNS``.

    Raises:
        AssertionError: If output columns differ from ``FEATURE_COLUMNS`` or a forbidden
            column appears.
    """
    admission = admission_df.sort_values("record_id").reset_index(drop=True)
    record_ids = admission["record_id"].astype(int)

    admit_part = _admission_features(admission)
    vital_parts = [
        _vital_features(vitals_df, record_ids, param, _VITAL_TO_PREFIX[param])
        for param in _VITAL_TO_PREFIX
    ]
    result = pd.concat([admit_part.drop(columns=["record_id"])] + vital_parts, axis=1)
    result = result.loc[:, FEATURE_COLUMNS]

    forbidden_in_output = set(result.columns) & FORBIDDEN_COLUMNS
    if forbidden_in_output:
        msg = f"Forbidden columns in feature output: {sorted(forbidden_in_output)}"
        raise AssertionError(msg)
    if list(result.columns) != FEATURE_COLUMNS:
        msg = "Feature columns do not match FEATURE_COLUMNS"
        raise AssertionError(msg)

    return result


def main(config_path: Path | str | None = None) -> None:
    """Build ``features.parquet`` from processed admission and vitals tables."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = load_config(config_path)
    processed_dir = Path(config["paths"]["processed_dir"])

    admission_df = pd.read_parquet(processed_dir / ADMISSION_PARQUET)
    vitals_df = pd.read_parquet(processed_dir / VITALS_PARQUET)

    features = compute_features(admission_df, vitals_df)
    record_id = (
        admission_df.sort_values("record_id")["record_id"].astype(int).reset_index(drop=True)
    )
    out = pd.concat([record_id, features], axis=1)

    processed_dir.mkdir(parents=True, exist_ok=True)
    out_path = processed_dir / FEATURES_PARQUET
    out.to_parquet(out_path, index=False)
    logger.info("Wrote %s (%s rows)", out_path, len(out))


if __name__ == "__main__":
    main()
