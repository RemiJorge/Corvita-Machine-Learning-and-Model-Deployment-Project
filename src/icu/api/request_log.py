"""Structured JSON request logging for the API (no patient values)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO


class RequestLogWriter:
    """Writes one JSON line per request to stdout and optionally to a file."""

    def __init__(self, file_path: Path | None = None) -> None:
        self._file: TextIO | None = None
        if file_path is not None:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            self._file = file_path.open("a", encoding="utf-8")

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def write_line(self, record: dict[str, Any]) -> None:
        """Serialize and emit one log record."""
        line = json.dumps(record, separators=(",", ":")) + "\n"
        sys.stdout.write(line)
        sys.stdout.flush()
        if self._file is not None:
            self._file.write(line)
            self._file.flush()


def utc_timestamp() -> str:
    """Return an ISO-8601 timestamp with millisecond precision in UTC."""
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def build_log_record(
    *,
    request_id: str,
    path: str,
    status_code: int,
    latency_ms: float,
    model_version: str | None,
    data_quality_status: str | None,
    missing_vitals: list[str] | None,
    n_measurements_used: int | None,
    n_excluded_after_cutoff: int | None,
    n_out_of_range: int | None,
    risk_flag: bool | None,
    feature_bins: dict[str, int] | None,
    error: str | None,
) -> dict[str, Any]:
    """Build a request log dict matching the API spec (section 7)."""
    severity = "ERROR" if status_code >= 500 else "INFO"
    return {
        "severity": severity,
        "ts": utc_timestamp(),
        "request_id": request_id,
        "path": path,
        "status_code": status_code,
        "latency_ms": round(latency_ms, 1),
        "model_version": model_version,
        "data_quality_status": data_quality_status,
        "missing_vitals": missing_vitals if missing_vitals is not None else [],
        "n_measurements_used": n_measurements_used,
        "n_excluded_after_cutoff": n_excluded_after_cutoff,
        "n_out_of_range": n_out_of_range,
        "risk_flag": risk_flag,
        "feature_bins": feature_bins if feature_bins is not None else {},
        "error": error,
    }
