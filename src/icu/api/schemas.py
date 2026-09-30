"""Pydantic request and response schemas for the prediction API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from icu.config import load_config
from icu.parse import ParseError, time_to_minutes

_VITAL_PARAMETER = Literal["HR", "RespRate", "Temp"]

_config = load_config()
_age_bounds = _config["admission_bounds"]["Age"]
_icu_bounds = _config["admission_bounds"]["ICUType"]
_age_low, _age_high = float(_age_bounds[0]), float(_age_bounds[1])
_icu_low, _icu_high = int(_icu_bounds[0]), int(_icu_bounds[1])


class Measurement(BaseModel):
    """One vital measurement at an elapsed ICU time."""

    model_config = ConfigDict(extra="forbid")

    time: str
    parameter: _VITAL_PARAMETER
    value: float

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        """Require HH:MM with hours 0 to 47 and minutes 0 to 59."""
        try:
            minutes = time_to_minutes(value)
        except ParseError as exc:
            raise ValueError(str(exc)) from exc
        hours = minutes // 60
        if hours > 47:
            msg = f"Invalid time (hours must be 0-47): {value!r}"
            raise ValueError(msg)
        return value

    @field_validator("value")
    @classmethod
    def validate_finite(cls, value: float) -> float:
        """Reject non-finite values."""
        if value != value or value in (float("inf"), float("-inf")):
            msg = "value must be a finite number"
            raise ValueError(msg)
        return value


class PredictRequest(BaseModel):
    """POST /predict body with admission fields and raw measurements."""

    model_config = ConfigDict(extra="forbid")

    record_id: str | None = Field(default=None, min_length=1, max_length=64)
    age: float
    gender: int | None
    icu_type: int
    measurements: list[Measurement] = Field(max_length=2000)

    @field_validator("age")
    @classmethod
    def validate_age(cls, value: float) -> float:
        """Enforce admission age bounds from config."""
        if value < _age_low or value > _age_high:
            msg = f"age must be between {_age_low} and {_age_high}"
            raise ValueError(msg)
        return value

    @field_validator("icu_type")
    @classmethod
    def validate_icu_type(cls, value: int) -> int:
        """Enforce ICU type bounds from config."""
        if value < _icu_low or value > _icu_high:
            msg = f"icu_type must be between {_icu_low} and {_icu_high}"
            raise ValueError(msg)
        return value

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, value: int | None) -> int | None:
        """Allow 0, 1, or null for unknown."""
        if value is not None and value not in (0, 1):
            msg = "gender must be 0, 1, or null"
            raise ValueError(msg)
        return value


class ModelInfo(BaseModel):
    """Metadata identifying the served model."""

    model_config = ConfigDict(extra="forbid")

    version: str
    type: str
    git_commit: str
    training_data_sha256: str
    trained_at: str


class DataQualityInfo(BaseModel):
    """Counts and status for the first-24-hour measurements."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "partial", "insufficient"]
    missing_vitals: list[str]
    n_measurements_used: int
    n_excluded_after_cutoff: int
    n_out_of_range: int


class PredictResponse(BaseModel):
    """Successful prediction or abstention response."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    record_id: str | None
    probability: float | None
    risk_flag: bool | None
    threshold: float
    model: ModelInfo
    data_quality: DataQualityInfo
    warnings: list[str]


class HealthResponse(BaseModel):
    """Liveness and loaded model version."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    model_version: str


class ErrorResponse(BaseModel):
    """Internal server error payload."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    error: Literal["internal_error"]
