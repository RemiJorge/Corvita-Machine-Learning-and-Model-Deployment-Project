"""Map API requests to features, run the model, and build responses."""

from __future__ import annotations

from typing import Any, Literal

import pandas as pd

from icu.api.schemas import DataQualityInfo, ModelInfo, PredictRequest, PredictResponse
from icu.features import FEATURE_COLUMNS, compute_features
from icu.parse import time_to_minutes
from icu.psi import feature_bins_from_row
from icu.quality import apply_physiological_bounds
from icu.tables import apply_cutoff, build_vitals_table, count_cutoff_exclusions

_VITAL_NAMES = ("HR", "RespRate", "Temp")
ABSTENTION_WARNING = (
    "No valid vital sign in the first 24 hours. The model abstains because the score "
    "would rest on age, sex and ICU type only."
)

# record_id is tracing only; feature pipeline uses a fixed internal id.
_INTERNAL_RECORD_ID = 0


def measurements_to_frame(request: PredictRequest) -> pd.DataFrame:
    """Convert API measurements to the long table used in training."""
    rid = _INTERNAL_RECORD_ID
    rows: list[dict[str, object]] = []
    for order, measurement in enumerate(request.measurements):
        minute = time_to_minutes(measurement.time)
        rows.append(
            {
                "record_id": rid,
                "minute": minute,
                "parameter": measurement.parameter,
                "value": float(measurement.value),
                "row_order": order,
            }
        )
    if not rows:
        return pd.DataFrame(columns=["record_id", "minute", "parameter", "value", "row_order"])
    return pd.DataFrame(rows)


def data_quality_status(
    hr_missing: int,
    resp_missing: int,
    temp_missing: int,
    *,
    any_vital_row_in_window: bool,
) -> tuple[Literal["ok", "partial", "insufficient"], list[str]]:
    """Derive status and missing vital names from feature missing flags.

    A record with no vital rows in the first 24 hours is ``insufficient``. If vitals
    were sent but every value is missing after bounds, status is ``partial``.
    """
    flags = {
        "HR": hr_missing,
        "RespRate": resp_missing,
        "Temp": temp_missing,
    }
    missing = [name for name, flag in flags.items() if int(flag) == 1]
    n_missing = len(missing)
    if n_missing == 0:
        return "ok", []
    if not any_vital_row_in_window:
        return "insufficient", missing
    return "partial", missing


def build_warnings(
    status: Literal["ok", "partial", "insufficient"],
    missing_vitals: list[str],
    n_excluded_after_cutoff: int,
    n_out_of_range: int,
) -> list[str]:
    """Build warning sentences in the fixed order required by the API spec."""
    warnings: list[str] = []
    if n_excluded_after_cutoff > 0:
        warnings.append(f"{n_excluded_after_cutoff} measurements after 24:00 were excluded.")
    if n_out_of_range > 0:
        noun = "value" if n_out_of_range == 1 else "values"
        verb = "was" if n_out_of_range == 1 else "were"
        warnings.append(
            f"{n_out_of_range} measurement {noun} {verb} outside physiological bounds and ignored."
        )
    if status == "partial" and missing_vitals:
        joined = ", ".join(missing_vitals)
        warnings.append(f"No valid measurement for {joined} in the first 24 hours.")
    if status == "insufficient":
        warnings.append(ABSTENTION_WARNING)
    return warnings


def model_info_from_metadata(metadata: dict[str, Any]) -> ModelInfo:
    """Map packaged metadata to the API model block."""
    return ModelInfo(
        version=str(metadata["model_version"]),
        type=str(metadata["served_model"]),
        git_commit=str(metadata["git_commit"]),
        training_data_sha256=str(metadata["training_data_sha256"]),
        trained_at=str(metadata["created_at"]),
    )


def predict_from_request(
    request: PredictRequest,
    config: dict[str, Any],
    pipeline: Any,
    metadata: dict[str, Any],
    request_id: str,
) -> tuple[PredictResponse, dict[str, int]]:
    """Run cutoff, bounds, features, and prediction for one request.

    Args:
        request: Validated API body.
        config: Loaded project configuration.
        pipeline: Fitted scikit-learn pipeline.
        metadata: Model folder metadata including threshold.
        request_id: UUID string for tracing.

    Returns:
        Response model with probability or abstention.

    """
    vitals: list[str] = list(config["vitals"])
    cutoff = int(config["cutoff_minutes"])
    bounds = config["physiological_bounds"]

    measurements = measurements_to_frame(request)
    if measurements.empty:
        exclusion_counts = {v: 0 for v in vitals}
    else:
        exclusion_counts = count_cutoff_exclusions(measurements, vitals, cutoff)
    n_excluded_after_cutoff = sum(exclusion_counts.values())

    in_window = apply_cutoff(measurements, cutoff) if not measurements.empty else measurements
    any_vital_row_in_window = not in_window.empty and in_window["parameter"].isin(vitals).any()
    vital_oob: dict[str, int] = {}
    cleaned = (
        apply_physiological_bounds(in_window, vitals, bounds, vital_oob)
        if not in_window.empty
        else in_window
    )
    n_out_of_range = sum(vital_oob.values())

    vitals_df = build_vitals_table(cleaned, vitals, cutoff)
    n_measurements_used = len(vitals_df)

    admission = pd.DataFrame(
        [
            {
                "record_id": _INTERNAL_RECORD_ID,
                "age": request.age,
                "gender": request.gender,
                "icu_type": request.icu_type,
            }
        ]
    )
    features = compute_features(admission, vitals_df)
    row = features.iloc[0]
    status, missing_vitals = data_quality_status(
        int(row["hr_missing"]),
        int(row["resp_rate_missing"]),
        int(row["temp_missing"]),
        any_vital_row_in_window=any_vital_row_in_window,
    )
    threshold = float(metadata["threshold"])
    warnings = build_warnings(status, missing_vitals, n_excluded_after_cutoff, n_out_of_range)

    psi_bins = metadata.get("training_reference", {}).get("psi_bins")
    feature_bins: dict[str, int] = (
        feature_bins_from_row(row, psi_bins) if isinstance(psi_bins, dict) and psi_bins else {}
    )

    probability: float | None
    risk_flag: bool | None
    if status == "insufficient":
        probability = None
        risk_flag = None
    else:
        x = features.loc[:, FEATURE_COLUMNS]
        proba = float(pipeline.predict_proba(x)[0, 1])
        probability = round(proba, 4)
        risk_flag = proba >= threshold

    response = PredictResponse(
        request_id=request_id,
        record_id=request.record_id,
        probability=probability,
        risk_flag=risk_flag,
        threshold=threshold,
        model=model_info_from_metadata(metadata),
        data_quality=DataQualityInfo(
            status=status,
            missing_vitals=missing_vitals,
            n_measurements_used=n_measurements_used,
            n_excluded_after_cutoff=n_excluded_after_cutoff,
            n_out_of_range=n_out_of_range,
        ),
        warnings=warnings,
    )
    return response, feature_bins
