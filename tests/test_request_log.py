"""Tests for structured API request logging."""

from __future__ import annotations

from icu.api.request_log import build_log_record


def test_build_log_record_severity_info_for_success() -> None:
    record = build_log_record(
        request_id="abc",
        path="/predict",
        status_code=200,
        latency_ms=12.3,
        model_version="1.0.0",
        data_quality_status="ok",
        missing_vitals=[],
        n_measurements_used=3,
        n_excluded_after_cutoff=0,
        n_out_of_range=0,
        risk_flag=False,
        error=None,
    )
    assert record["severity"] == "INFO"


def test_build_log_record_severity_error_for_5xx() -> None:
    record = build_log_record(
        request_id="abc",
        path="/predict",
        status_code=500,
        latency_ms=1.0,
        model_version="1.0.0",
        data_quality_status=None,
        missing_vitals=None,
        n_measurements_used=None,
        n_excluded_after_cutoff=None,
        n_out_of_range=None,
        risk_flag=None,
        error="internal_error",
    )
    assert record["severity"] == "ERROR"
