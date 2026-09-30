"""Tests for the monitoring check on API request logs."""

from __future__ import annotations

import json
from pathlib import Path

from icu.monitor import run_monitor

_REF = {
    "missing_rate": {"HR": 0.02, "RespRate": 0.05, "Temp": 0.02},
    "partial_rate": 0.10,
    "insufficient_rate": 0.01,
}

_CONFIG = {
    "monitoring": {
        "window_size": 200,
        "max_partial_rate_increase": 0.15,
        "max_insufficient_rate": 0.05,
    },
}


def _log_line(
    *,
    status: str = "ok",
    missing_vitals: list[str] | None = None,
    status_code: int = 200,
) -> str:
    record = {
        "ts": "2026-10-03T10:15:02.114Z",
        "request_id": "00000000-0000-0000-0000-000000000001",
        "path": "/predict",
        "status_code": status_code,
        "latency_ms": 5.0,
        "model_version": "1.0.0",
        "data_quality_status": status,
        "missing_vitals": missing_vitals or [],
        "n_measurements_used": 10,
        "n_excluded_after_cutoff": 0,
        "n_out_of_range": 0,
        "risk_flag": False,
        "error": None,
    }
    return json.dumps(record) + "\n"


def _write_log(path: Path, lines: list[str]) -> None:
    path.write_text("".join(lines), encoding="utf-8")


def test_monitor_ok(tmp_path: Path) -> None:
    log_path = tmp_path / "requests.jsonl"
    lines = [_log_line(status="ok") for _ in range(35)]
    _write_log(log_path, lines)
    summary, code = run_monitor(log_path, _CONFIG, _REF)
    assert code == 0
    assert summary["status"] == "ok"
    assert summary["metrics"]["n_requests"] == 35
    assert summary["alerts"] == []


def test_monitor_alert_on_missing_rate(tmp_path: Path) -> None:
    log_path = tmp_path / "requests.jsonl"
    lines = [_log_line(status="partial", missing_vitals=["HR"]) for _ in range(35)]
    _write_log(log_path, lines)
    summary, code = run_monitor(log_path, _CONFIG, _REF)
    assert code == 1
    assert summary["status"] == "alert"
    assert any("missing_rate[HR]" in alert for alert in summary["alerts"])


def test_monitor_alert_on_insufficient(tmp_path: Path) -> None:
    log_path = tmp_path / "requests.jsonl"
    missing_all = ["HR", "RespRate", "Temp"]
    lines = [_log_line(status="insufficient", missing_vitals=missing_all) for _ in range(35)]
    _write_log(log_path, lines)
    summary, code = run_monitor(log_path, _CONFIG, _REF)
    assert code == 1
    assert summary["status"] == "alert"
    assert any("insufficient_rate" in alert for alert in summary["alerts"])


def test_monitor_missing_log_file(tmp_path: Path) -> None:
    log_path = tmp_path / "requests.jsonl"
    summary, code = run_monitor(log_path, _CONFIG, _REF)
    assert code == 0
    assert summary["status"] == "not_enough_data"
    assert summary["metrics"]["n_requests"] == 0


def test_monitor_not_enough_data(tmp_path: Path) -> None:
    log_path = tmp_path / "requests.jsonl"
    lines = [_log_line() for _ in range(10)]
    _write_log(log_path, lines)
    summary, code = run_monitor(log_path, _CONFIG, _REF)
    assert code == 0
    assert summary["status"] == "not_enough_data"
    assert summary["metrics"]["n_requests"] == 10
