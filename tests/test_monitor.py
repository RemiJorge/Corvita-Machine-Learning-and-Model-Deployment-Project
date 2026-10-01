"""Tests for the monitoring check on API request logs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from icu.monitor import run_monitor

_UNIFORM_DECILES = [0.1] * 10 + [0.0]

_REF = {
    "missing_rate": {"HR": 0.02, "RespRate": 0.05, "Temp": 0.02},
    "partial_rate": 0.10,
    "insufficient_rate": 0.01,
    "psi_bins": {
        "temp_mean": {
            "edges": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0],
            "proportions": _UNIFORM_DECILES,
            "missing_bin": 10,
            "n_bins": 11,
        },
        "temp_last": {
            "edges": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0],
            "proportions": _UNIFORM_DECILES,
            "missing_bin": 10,
            "n_bins": 11,
        },
    },
}

_CONFIG = {
    "monitoring": {
        "window_size": 200,
        "max_partial_rate_increase": 0.15,
        "max_insufficient_rate": 0.05,
        "psi_alert": 0.25,
        "psi_min_requests": 200,
    },
}


def _log_line(
    *,
    status: str = "ok",
    missing_vitals: list[str] | None = None,
    status_code: int = 200,
    feature_bins: dict[str, int] | None = None,
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
        "feature_bins": feature_bins or {},
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


def test_monitor_psi_near_zero_with_matching_bins(tmp_path: Path) -> None:
    log_path = tmp_path / "requests.jsonl"
    lines = []
    for bin_idx in range(10):
        for _ in range(20):
            lines.append(_log_line(feature_bins={"temp_mean": bin_idx, "temp_last": bin_idx}))
    _write_log(log_path, lines)
    summary, code = run_monitor(log_path, _CONFIG, _REF)
    assert code == 0
    assert summary["status"] == "ok"
    assert summary["psi"]["temp_mean"] == pytest.approx(0.0, abs=1e-6)


def test_monitor_psi_alert_on_shifted_bins(tmp_path: Path) -> None:
    log_path = tmp_path / "requests.jsonl"
    bins = {"temp_mean": 9, "temp_last": 9}
    lines = [_log_line(feature_bins=bins) for _ in range(200)]
    _write_log(log_path, lines)
    summary, code = run_monitor(log_path, _CONFIG, _REF)
    assert code == 1
    assert summary["status"] == "alert"
    assert any("psi[temp_mean]" in alert for alert in summary["alerts"])
    assert any("psi[temp_last]" in alert for alert in summary["alerts"])


def test_monitor_psi_skipped_below_min_requests(tmp_path: Path) -> None:
    log_path = tmp_path / "requests.jsonl"
    bins = {"temp_mean": 9, "temp_last": 9}
    lines = [_log_line(feature_bins=bins) for _ in range(35)]
    _write_log(log_path, lines)
    summary, code = run_monitor(log_path, _CONFIG, _REF)
    assert code == 0
    assert summary["status"] == "ok"
    assert summary.get("psi_status") == "not_enough_data"
    assert summary["psi"] == {}
