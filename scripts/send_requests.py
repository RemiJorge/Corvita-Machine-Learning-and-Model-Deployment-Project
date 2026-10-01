#!/usr/bin/env python3
"""Replay test-set records against the prediction API for demos."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

from icu.config import load_config

REPO_ROOT = Path(__file__).resolve().parents[1]


def minute_to_time(minute: int) -> str:
    """Convert minute offset to HH:MM for the API."""
    return f"{minute // 60:02d}:{minute % 60:02d}"


def parse_shift_arg(shift_arg: str) -> dict[str, float]:
    """Parse ``Param=+delta`` entries (for example ``Temp=+1.5``)."""
    shifts: dict[str, float] = {}
    if not shift_arg.strip():
        return shifts
    for part in shift_arg.split(","):
        piece = part.strip()
        if not piece:
            continue
        if "=" not in piece:
            msg = f"Invalid --shift entry: {piece}"
            raise ValueError(msg)
        name, delta_str = piece.split("=", 1)
        name = name.strip()
        shifts[name] = float(delta_str.strip())
    return shifts


def build_request_body(
    record_id: int,
    admission: pd.Series,
    vitals_row: pd.DataFrame,
    drop: set[str],
    shifts: dict[str, float],
) -> dict[str, object]:
    """Build a POST /predict JSON body from processed tables."""
    measurements = []
    for _, row in vitals_row.iterrows():
        parameter = str(row["parameter"])
        if parameter in drop:
            continue
        value = float(row["value"]) + shifts.get(parameter, 0.0)
        measurements.append(
            {
                "time": minute_to_time(int(row["minute"])),
                "parameter": parameter,
                "value": value,
            }
        )
    gender = admission["gender"]
    gender_val: int | None = None if pd.isna(gender) else int(gender)
    return {
        "record_id": str(record_id),
        "age": float(admission["age"]),
        "gender": gender_val,
        "icu_type": int(admission["icu_type"]),
        "measurements": measurements,
    }


def post_predict(base_url: str, body: dict[str, object]) -> int:
    """POST one predict request and return the HTTP status code."""
    url = base_url.rstrip("/") + "/predict"
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def main() -> None:
    """Send up to ``--n`` test-set predict requests to the API."""
    parser = argparse.ArgumentParser(description="Replay test records against the API")
    parser.add_argument("--n", type=int, default=100, help="Number of requests to send")
    parser.add_argument(
        "--drop",
        type=str,
        default="",
        help="Comma-separated vitals to omit (HR, RespRate, Temp)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://127.0.0.1:8080",
        help="API base URL",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=REPO_ROOT / "config" / "config.yaml",
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--shift",
        type=str,
        default="",
        help="Comma-separated vital shifts (Temp=+1.5) to simulate sensor bias",
    )
    args = parser.parse_args()
    drop = {part.strip() for part in args.drop.split(",") if part.strip()}
    try:
        shifts = parse_shift_arg(args.shift)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    config = load_config(args.config)
    processed = Path(config["paths"]["processed_dir"])
    splits_dir = Path(config["paths"]["splits_dir"])
    admission_path = processed / "admission.parquet"
    vitals_path = processed / "vitals.parquet"
    test_ids_path = splits_dir / "test_ids.csv"

    for path in (admission_path, vitals_path, test_ids_path):
        if not path.is_file():
            print(f"Missing required file: {path}", file=sys.stderr)
            raise SystemExit(1)

    admission = pd.read_parquet(admission_path)
    vitals = pd.read_parquet(vitals_path)
    test_ids = pd.read_csv(test_ids_path)["record_id"].astype(int).tolist()
    if not test_ids:
        print("No test IDs found", file=sys.stderr)
        raise SystemExit(1)

    sent = 0
    index = 0
    while sent < args.n:
        record_id = int(test_ids[index % len(test_ids)])
        index += 1
        admit_rows = admission.loc[admission["record_id"] == record_id]
        if admit_rows.empty:
            continue
        vitals_row = vitals.loc[vitals["record_id"] == record_id]
        body = build_request_body(record_id, admit_rows.iloc[0], vitals_row, drop, shifts)
        status = post_predict(args.base_url, body)
        print(f"record_id={record_id} status={status}")
        sent += 1


if __name__ == "__main__":
    main()
