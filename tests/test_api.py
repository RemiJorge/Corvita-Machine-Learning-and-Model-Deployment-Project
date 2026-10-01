"""Tests for the prediction API (F9)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from icu.api.service import ABSTENTION_WARNING, predict_from_request
from icu.artifacts import load_model
from icu.config import load_config
from icu.features import FEATURE_COLUMNS, compute_features
from icu.parse import parse_record_file, read_outcomes
from icu.quality import clean_measurements
from icu.tables import build_admission_table, build_vitals_table

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "examples"


def _valid_payload() -> dict[str, object]:
    return {
        "record_id": "100",
        "age": 54,
        "gender": 1,
        "icu_type": 4,
        "measurements": [
            {"time": "00:07", "parameter": "HR", "value": 73},
            {"time": "00:37", "parameter": "Temp", "value": 36.5},
            {"time": "01:07", "parameter": "RespRate", "value": 18},
        ],
    }


def test_health(api_client: TestClient) -> None:
    response = api_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["model_version"] == "test"


def test_predict_non_numeric_record_id(api_client: TestClient) -> None:
    payload_numeric = _valid_payload()
    payload_alpha = _valid_payload()
    payload_alpha["record_id"] = "patient-A12"
    response_numeric = api_client.post("/predict", json=payload_numeric)
    response_alpha = api_client.post("/predict", json=payload_alpha)
    assert response_numeric.status_code == 200
    assert response_alpha.status_code == 200
    assert response_alpha.json()["record_id"] == "patient-A12"
    assert response_alpha.json()["probability"] == response_numeric.json()["probability"]


def test_predict_valid(api_client: TestClient) -> None:
    response = api_client.post("/predict", json=_valid_payload())
    assert response.status_code == 200
    body = response.json()
    assert 0.0 <= body["probability"] <= 1.0
    assert body["data_quality"]["status"] == "ok"
    assert body["model"]["version"] == "test"
    assert body["model"]["type"] == "logistic_regression"
    assert body["model"]["git_commit"]
    assert body["model"]["training_data_sha256"]
    assert body["model"]["trained_at"]


def test_predict_invalid_icu_type(api_client: TestClient) -> None:
    payload = _valid_payload()
    payload["icu_type"] = 7
    response = api_client.post("/predict", json=payload)
    assert response.status_code == 422


def test_predict_invalid_time_format(api_client: TestClient) -> None:
    payload = _valid_payload()
    payload["measurements"] = [{"time": "25:61", "parameter": "HR", "value": 70}]
    response = api_client.post("/predict", json=payload)
    assert response.status_code == 422


def test_predict_unknown_parameter(api_client: TestClient) -> None:
    payload = _valid_payload()
    payload["measurements"] = [{"time": "00:10", "parameter": "Hr", "value": 70}]
    response = api_client.post("/predict", json=payload)
    assert response.status_code == 422


def test_predict_extra_field(api_client: TestClient) -> None:
    payload = _valid_payload()
    payload["unknown"] = True
    response = api_client.post("/predict", json=payload)
    assert response.status_code == 422


def test_predict_partial(api_client: TestClient) -> None:
    payload = json.loads((EXAMPLES / "missing_vitals.json").read_text(encoding="utf-8"))
    response = api_client.post("/predict", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["data_quality"]["status"] == "partial"
    assert "RespRate" in body["data_quality"]["missing_vitals"]
    assert "HR" in body["data_quality"]["missing_vitals"]
    assert any("No valid measurement" in w for w in body["warnings"])


def test_predict_no_vitals_abstains(api_client: TestClient) -> None:
    payload = json.loads((EXAMPLES / "no_vitals.json").read_text(encoding="utf-8"))
    response = api_client.post("/predict", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["probability"] is None
    assert body["risk_flag"] is None
    assert body["data_quality"]["status"] == "insufficient"
    assert ABSTENTION_WARNING in body["warnings"]


def test_predict_excludes_after_cutoff(api_client: TestClient) -> None:
    payload = _valid_payload()
    payload["measurements"] = [
        {"time": "00:10", "parameter": "HR", "value": 80},
        {"time": "24:01", "parameter": "HR", "value": 90},
    ]
    response = api_client.post("/predict", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["data_quality"]["n_excluded_after_cutoff"] == 1
    assert body["data_quality"]["n_measurements_used"] == 1


def test_logs_contain_no_patient_values(tmp_path: Path, api_client: TestClient) -> None:
    log_path = tmp_path / "requests.jsonl"
    payload = _valid_payload()
    payload["record_id"] = "424242"
    payload["age"] = 77
    payload["measurements"] = [
        {"time": "00:07", "parameter": "HR", "value": 123.45},
        {"time": "00:37", "parameter": "Temp", "value": 36.5},
        {"time": "01:07", "parameter": "RespRate", "value": 18},
    ]
    response = api_client.post("/predict", json=payload)
    assert response.status_code == 200
    assert log_path.is_file()
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) >= 1
    log_text = lines[-1]
    assert "424242" not in log_text
    assert "123.45" not in log_text
    assert "36.5" not in log_text
    assert f'"age": {payload["age"]}' not in log_text
    assert '"probability"' not in log_text
    record = json.loads(log_text)
    assert record["path"] == "/predict"
    assert record["request_id"]
    assert record["severity"] == "INFO"
    assert record["data_quality_status"] in ("ok", "partial", "insufficient")
    assert "feature_bins" in record
    assert isinstance(record["feature_bins"], dict)
    assert "77" not in log_text
    assert "36.5" not in log_text


def test_out_of_range_becomes_missing(api_client: TestClient) -> None:
    payload = {
        "record_id": "101",
        "age": 50,
        "gender": 1,
        "icu_type": 2,
        "measurements": [{"time": "00:10", "parameter": "HR", "value": 0}],
    }
    response = api_client.post("/predict", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["data_quality"]["status"] == "partial"
    assert body["data_quality"]["n_out_of_range"] == 1
    assert "HR" in body["data_quality"]["missing_vitals"]
    assert any("1 measurement value was" in w for w in body["warnings"])


def _minute_to_time(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


@pytest.mark.data
def test_api_matches_offline_prediction() -> None:
    """API probability matches the packaged pipeline on a real test record."""
    config = load_config(REPO_ROOT / "config" / "config.yaml")
    pipeline, metadata = load_model("1.0.1", config_path=REPO_ROOT / "config" / "config.yaml")

    test_ids = pd.read_csv(REPO_ROOT / "splits" / "test_ids.csv")["record_id"].astype(int)
    record_id = int(test_ids.iloc[0])

    raw_path = REPO_ROOT / "data" / "raw" / "set-a" / f"{record_id}.txt"
    if not raw_path.is_file():
        pytest.skip("PhysioNet set-a not available")

    rows = parse_record_file(raw_path)
    measurements = pd.DataFrame(rows)
    cleaned, _ = clean_measurements(measurements, config)
    outcomes = read_outcomes(REPO_ROOT / "data" / "raw" / "Outcomes-a.txt")
    admission = build_admission_table(cleaned, outcomes)
    admit_row = admission.loc[admission["record_id"] == record_id].iloc[0]
    vitals = build_vitals_table(cleaned, list(config["vitals"]), int(config["cutoff_minutes"]))
    vitals_row = vitals.loc[vitals["record_id"] == record_id]

    api_measurements = [
        {
            "time": _minute_to_time(int(row["minute"])),
            "parameter": row["parameter"],
            "value": float(row["value"]),
        }
        for _, row in vitals_row.iterrows()
    ]

    from icu.api.schemas import PredictRequest

    request = PredictRequest(
        record_id=str(record_id),
        age=float(admit_row["age"]),
        gender=int(admit_row["gender"]) if pd.notna(admit_row["gender"]) else None,
        icu_type=int(admit_row["icu_type"]),
        measurements=api_measurements,
    )
    response, _feature_bins = predict_from_request(
        request, config, pipeline, metadata, "offline-test"
    )
    features = compute_features(
        admission.loc[admission["record_id"] == record_id],
        vitals_row.reset_index(drop=True),
    )
    offline = float(pipeline.predict_proba(features.loc[:, FEATURE_COLUMNS])[0, 1])
    assert response.probability is not None
    assert response.data_quality.status != "insufficient"
    assert abs(response.probability - round(offline, 4)) < 1e-9
