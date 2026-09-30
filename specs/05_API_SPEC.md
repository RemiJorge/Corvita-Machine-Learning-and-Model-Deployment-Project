# 05. API specification

F9 delivered the API, Docker image, and examples. F10 delivered section 7 request logging and `scripts/send_requests.py` (`make simulate`).

## 1. Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/predict` | Risk of in-hospital death for one record from raw first-day measurements |
| `GET` | `/health` | Liveness and loaded model version |

FastAPI's generated docs stay enabled at `/docs` for the demo.

The API takes raw measurements, not precomputed features. It applies the same cutoff, cleaning and feature functions as training. This is deliberate: a client can never send features computed differently from training.

## 2. Request schema

```json
{
  "record_id": "132539",
  "age": 54,
  "gender": 1,
  "icu_type": 4,
  "measurements": [
    {"time": "00:07", "parameter": "HR", "value": 73},
    {"time": "00:37", "parameter": "Temp", "value": 35.1},
    {"time": "01:07", "parameter": "RespRate", "value": 18}
  ]
}
```

| Field | Type | Required | Rules |
|---|---|---|---|
| `record_id` | string | no | 1 to 64 characters. Echoed back and logged for tracing. Never a feature. |
| `age` | number | yes | Within `admission_bounds.Age`, else 422 |
| `gender` | integer or null | yes (may be null) | 0 = female, 1 = male, null = unknown |
| `icu_type` | integer | yes | 1 to 4, else 422 |
| `measurements` | array | yes (may be empty) | At most 2000 items |
| `measurements[].time` | string | yes | `HH:MM`, minutes 00 to 59, hours 00 to 47, else 422 |
| `measurements[].parameter` | string | yes | One of `HR`, `RespRate`, `Temp`, else 422 |
| `measurements[].value` | number | yes | Finite number, else 422 |

Pydantic models in `icu/api/schemas.py` with `model_config = ConfigDict(extra="forbid")`, so unknown fields are rejected with 422. Using `Literal["HR", "RespRate", "Temp"]` for `parameter`.

### Why unknown parameters are rejected rather than ignored

A typo such as `"Hr"` would otherwise be silently dropped and the patient would look like it has no heart rate. Failing loudly is safer. Written in `docs/api.md`.

## 3. Processing steps (`icu/api/service.py`)

1. Convert the request into the same long-format DataFrame used in training (`record_id`, `minute`, `parameter`, `value`, `row_order` = position in the array).
2. Apply `apply_cutoff` (minute <= 1440). Count excluded measurements.
3. Apply the physiological bounds from `quality.py`. Count values turned missing.
4. Build the admission row and call `compute_features`.
5. Compute the data-quality status (section 5).
6. If the status is `insufficient`, abstain (section 6). Otherwise predict with the loaded pipeline and compare with the model's threshold.
7. Build the response and log the request (section 7).

No step may reimplement logic that exists in `quality.py`, `tables.py` or `features.py`.

## 4. Response schema (200)

```json
{
  "request_id": "5f1c0e7a-6a3c-4e0e-9a55-2f1b9c1d2e11",
  "record_id": "132539",
  "probability": 0.083,
  "risk_flag": false,
  "threshold": 0.12,
  "model": {
    "version": "1.0.0",
    "type": "logistic_regression",
    "git_commit": "abc1234",
    "training_data_sha256": "…",
    "trained_at": "2026-10-02T15:40:00Z"
  },
  "data_quality": {
    "status": "ok",
    "missing_vitals": [],
    "n_measurements_used": 57,
    "n_excluded_after_cutoff": 12,
    "n_out_of_range": 0
  },
  "warnings": [
    "12 measurements after 24:00 were excluded."
  ]
}
```

- `probability` is rounded to 4 decimals. `risk_flag` is `probability >= threshold`.
- `model` answers the brief's question "which data and model version produced this prediction".
- `warnings` are short English sentences, in a fixed order, generated from the counts.

## 5. Data-quality status

| Status | Condition | Behaviour |
|---|---|---|
| `ok` | All three vitals have at least one valid measurement in the window | Normal prediction |
| `partial` | One or two vitals have no valid measurement | Prediction returned, missing vitals listed, warning added |
| `insufficient` | None of the three vitals has a valid measurement | Abstention (section 6) |

Out-of-range values that are removed can change the status (a record whose only HR value is 0 becomes `partial`). The warning says so.

## 6. Abstention rule

When the status is `insufficient`, the API returns 200 with `probability: null`, `risk_flag: null`, and a warning: "No valid vital sign in the first 24 hours. The model abstains because such inputs are outside what it was trained on."

Reasoning for the ADR: the training data contains very few or no records without any vital in the first day (the quality report gives the exact number). A probability computed from age, gender and ICU type alone would look like a normal output to a clinician while resting on almost nothing. In a clinical tool, an explicit "cannot assess" is safer than a number that looks trustworthy. The endpoint still returns 200 because the request was valid; abstaining is a correct answer, not an error.

If the F2 quality report shows that a meaningful share of training records have no vitals, reconsider this rule with the human owner before implementing it.

## 7. Request logging

Implemented in F10 (`icu/api/request_log.py`). One JSON line per request to stdout and, when `REQUEST_LOG_PATH` is set, appended to that file. Stdout is what Cloud Run sends to Cloud Logging; the file is what `make monitor` reads locally.

```json
{"ts": "2026-10-03T10:15:02.114Z", "request_id": "…", "path": "/predict", "status_code": 200,
 "latency_ms": 7.4, "model_version": "1.0.0", "data_quality_status": "partial",
 "missing_vitals": ["RespRate"], "n_measurements_used": 41, "n_excluded_after_cutoff": 3,
 "n_out_of_range": 0, "risk_flag": false, "error": null}
```

- Written by a FastAPI middleware so that 422 and 500 responses are logged too (with `error` set to the error type).
- Never logged: `record_id`, age, gender, ICU type, measurement values, probability. The log carries enough to monitor quality and latency, and nothing that identifies or describes a patient. This is stated in `docs/api.md` and `docs/operations.md`.
- Latency measured with `time.perf_counter()` around the whole request.

## 8. Errors

| Case | Status | Body |
|---|---|---|
| Schema violation (missing field, wrong type, unknown field, bad time format, unknown parameter, age or ICU type out of bounds) | 422 | FastAPI's standard validation detail |
| Unexpected exception | 500 | `{"request_id": "…", "error": "internal_error"}`; stack trace in the log only |
| Model file missing or scikit-learn version mismatch at startup | process exits with a clear message | The container fails its health check instead of serving wrong predictions |

## 9. Configuration

Environment variables, read once at startup:

| Variable | Default | Purpose |
|---|---|---|
| `MODEL_VERSION` | `serving.model_version` from config | Folder under `models/` to load |
| `MODELS_DIR` | `models` | Base folder |
| `REQUEST_LOG_PATH` | unset | Also append logs to this file |
| `PORT` | `8080` | Listening port (Cloud Run sets it) |

Rollback is a change of `MODEL_VERSION` or of the deployed image tag. Nothing else changes.

## 10. Docker image

- Multi-stage build. Builder stage: `python:3.12-slim` with `uv`, `uv sync --frozen --no-dev` into a virtual environment. Runtime stage: `python:3.12-slim`, copies the virtual environment, `src/`, `config/`, and `models/<version>/` only.
- Runs as a non-root user.
- `EXPOSE 8080`, command `uvicorn icu.api.app:app --host 0.0.0.0 --port ${PORT}`.
- `HEALTHCHECK` calling `/health` with Python's `urllib` (no curl in the image).
- `.dockerignore` excludes `data/`, `logs/`, `.git/`, `tests/`, `reports/`, `infra/`, caches.
- The model is baked into the image. Reason for the ADR: an image tag then fully identifies code plus model, which makes deployments immutable and rollback a single operation. The alternative (loading from a bucket at startup) is described in `docs/infrastructure.md` as the option for frequent model updates.
- Record the final image size in the README.

## 11. Examples

`examples/valid.json`, `examples/invalid.json` (for example `icu_type: 7` and a time `"25:61"`), `examples/missing_vitals.json` (only Temp present, to show `partial`), and `examples/no_vitals.json` (to show abstention). `docs/api.md` shows the `curl` command and the exact response for each, copied from a real run.

```bash
curl -s -X POST localhost:8080/predict \
  -H "Content-Type: application/json" \
  -d @examples/valid.json | python -m json.tool
```

## 12. Tests (`tests/test_api.py`, FastAPI `TestClient`)

| Test | Expects |
|---|---|
| `test_health` | 200, model version present |
| `test_predict_valid` | 200, probability in [0, 1], status `ok`, model block complete |
| `test_predict_invalid_icu_type` | 422 |
| `test_predict_invalid_time_format` | 422 |
| `test_predict_unknown_parameter` | 422 |
| `test_predict_extra_field` | 422 |
| `test_predict_partial` | 200, status `partial`, missing vital listed, warning present |
| `test_predict_no_vitals_abstains` | 200, probability null, status `insufficient` |
| `test_predict_excludes_after_cutoff` | Measurement at 24:01 counted as excluded and not used |
| `test_out_of_range_becomes_missing` | HR = 0 only -> status `partial` |
| `test_logs_contain_no_patient_values` | Captured log line has none of the request's values or record_id |
| `test_api_matches_offline_prediction` (data marker) | Same probability as offline pipeline for a test record, tolerance 1e-9 |

Tests use a small model trained on fixtures, created in `conftest.py`, so the API tests run in CI without the real dataset.
