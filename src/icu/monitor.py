"""Monitoring check on structured API request logs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from icu.artifacts import load_model
from icu.config import load_config

MIN_REQUESTS = 30
VITALS = ("HR", "RespRate", "Temp")


def read_log_lines(log_path: Path) -> list[dict[str, Any]]:
    """Parse JSON lines from the request log file.

    Args:
        log_path: Path to JSONL request log.

    Returns:
        List of parsed records; invalid lines are skipped. An empty list if the
        file does not exist yet (no traffic has been logged).
    """
    if not log_path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            records.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue
    return records


def select_window(
    records: list[dict[str, Any]],
    window_size: int,
) -> list[dict[str, Any]]:
    """Return up to ``window_size`` most recent successful ``/predict`` log entries."""
    window: list[dict[str, Any]] = []
    for record in reversed(records):
        if record.get("path") != "/predict":
            continue
        if record.get("status_code") != 200:
            continue
        window.append(record)
        if len(window) >= window_size:
            break
    return window


def compute_metrics(window: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute monitoring metrics over a window of successful predict logs."""
    n_requests = len(window)
    if n_requests == 0:
        return {
            "n_requests": 0,
            "missing_rate": {v: 0.0 for v in VITALS},
            "partial_rate": 0.0,
            "insufficient_rate": 0.0,
            "error_rate": 0.0,
            "latency_p50_ms": 0.0,
            "latency_p95_ms": 0.0,
        }

    missing_counts = {v: 0 for v in VITALS}
    partial = 0
    insufficient = 0
    errors = 0
    latencies: list[float] = []

    for record in window:
        status_code = int(record.get("status_code", 200))
        if status_code >= 400:
            errors += 1
        latencies.append(float(record.get("latency_ms", 0.0)))
        dq_status = record.get("data_quality_status")
        if dq_status == "partial":
            partial += 1
        elif dq_status == "insufficient":
            insufficient += 1
        missing = record.get("missing_vitals") or []
        for vital in VITALS:
            if vital in missing:
                missing_counts[vital] += 1

    missing_rate = {v: missing_counts[v] / n_requests for v in VITALS}
    return {
        "n_requests": n_requests,
        "missing_rate": missing_rate,
        "partial_rate": partial / n_requests,
        "insufficient_rate": insufficient / n_requests,
        "error_rate": errors / n_requests,
        "latency_p50_ms": float(np.percentile(latencies, 50)),
        "latency_p95_ms": float(np.percentile(latencies, 95)),
    }


def evaluate_alerts(
    metrics: dict[str, Any],
    training_reference: dict[str, Any],
    monitoring_config: dict[str, Any],
) -> list[str]:
    """Return human-readable alert messages when thresholds are exceeded."""
    alerts: list[str] = []
    max_partial = float(monitoring_config["max_partial_rate_increase"])
    max_insufficient = float(monitoring_config["max_insufficient_rate"])
    ref_partial = float(training_reference["partial_rate"])
    ref_missing = training_reference["missing_rate"]

    if metrics["partial_rate"] > ref_partial + max_partial:
        alerts.append(
            f"partial_rate {metrics['partial_rate']:.4f} exceeds training "
            f"{ref_partial:.4f} + {max_partial}"
        )
    if metrics["insufficient_rate"] > max_insufficient:
        alerts.append(
            f"insufficient_rate {metrics['insufficient_rate']:.4f} exceeds max {max_insufficient}"
        )
    for vital in VITALS:
        observed = metrics["missing_rate"][vital]
        baseline = float(ref_missing[vital])
        if observed > baseline + max_partial:
            alerts.append(
                f"missing_rate[{vital}] {observed:.4f} exceeds training "
                f"{baseline:.4f} + {max_partial}"
            )
    return alerts


def run_monitor(
    log_path: Path,
    config: dict[str, Any],
    training_reference: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Run the monitoring check and return a summary dict and exit code.

    Args:
        log_path: JSONL request log path.
        config: Loaded project configuration.
        training_reference: Baseline rates from model metadata.

    Returns:
        Tuple of summary dictionary and process exit code (0 or 1).
    """
    monitoring = config["monitoring"]
    window_size = int(monitoring["window_size"])
    records = read_log_lines(log_path)
    window = select_window(records, window_size)
    metrics = compute_metrics(window)

    summary: dict[str, Any] = {
        "log_path": str(log_path),
        "window_size": window_size,
        "reference": {
            "partial_rate": training_reference["partial_rate"],
            "insufficient_rate": training_reference["insufficient_rate"],
            "missing_rate": training_reference["missing_rate"],
        },
        "metrics": metrics,
        "alerts": [],
        "status": "ok",
    }

    if metrics["n_requests"] < MIN_REQUESTS:
        summary["status"] = "not_enough_data"
        return summary, 0

    alerts = evaluate_alerts(metrics, training_reference, monitoring)
    summary["alerts"] = alerts
    if alerts:
        summary["status"] = "alert"
        return summary, 1
    return summary, 0


def main(config_path: Path | str | None = None) -> None:
    """CLI entry point for the monitoring check."""
    parser = argparse.ArgumentParser(description="Run monitoring check on API request logs")
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Request log JSONL path (default: paths.request_log from config)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml",
    )
    args = parser.parse_args()
    config = load_config(args.config or config_path)
    log_path = args.log or Path(config["paths"]["request_log"])
    model_version = str(config["serving"]["model_version"])
    _, metadata = load_model(model_version, args.config or config_path)
    training_reference = metadata["training_reference"]
    summary, exit_code = run_monitor(log_path, config, training_reference)
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
