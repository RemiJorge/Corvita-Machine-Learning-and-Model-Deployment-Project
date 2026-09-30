# Prediction API

FastAPI service that scores in-hospital death risk from the first 24 hours of ICU vitals. Clients send raw measurements; the server applies the same cutoff, bounds, and feature code as training (`icu.tables`, `icu.quality`, `icu.features`).

Request JSON logging is added in F10. This page covers F9 endpoints and behaviour.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/predict` | Risk score for one patient |
| `GET` | `/health` | Liveness and loaded model version |

Interactive OpenAPI docs: `http://localhost:8080/docs`.

## Unknown parameters

Measurement `parameter` must be exactly `HR`, `RespRate`, or `Temp`. Typos such as `Hr` are rejected with HTTP 422 instead of being dropped, so a client cannot silently omit a vital.

## Data quality and abstention

| Status | Meaning |
|---|---|
| `ok` | All three vitals have at least one valid value in the first 24 hours |
| `partial` | One or two vitals lack a valid value; a probability is still returned |
| `insufficient` | No vital rows in the window; the model abstains (`probability` and `risk_flag` are null) |

If vitals were sent but every value is out of range, status is `partial` (see ADR 008). See `docs/decisions/008-api-abstention.md`.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `MODEL_VERSION` | `serving.model_version` in config | Folder under `models/` |
| `MODELS_DIR` | `models` | Base directory for model folders |
| `PORT` | `8080` | Listen port |

## Errors

| Case | Status |
|---|---|
| Schema violation | 422 (FastAPI validation detail) |
| Unexpected server error | 500 with `{"request_id", "error": "internal_error"}` |
| Missing model or sklearn mismatch at startup | Process exits (container health check fails) |

## Examples

Run the API with `make api` or `make docker-run`, then:

### Valid request

```bash
curl -s -X POST localhost:8080/predict \
  -H "Content-Type: application/json" \
  -d @examples/valid.json | python3 -m json.tool
```

Response (2026-09-30, model 1.0.0):

```json
{
    "request_id": "b4345a33-c1f9-4231-b2ff-dad9d4947ac5",
    "record_id": "132539",
    "probability": 0.0902,
    "risk_flag": false,
    "threshold": 0.13113858330514636,
    "model": {
        "version": "1.0.0",
        "type": "logistic_regression",
        "git_commit": "7d004194cb7a5e6efc433fd877596e1a6d77b3a0",
        "training_data_sha256": "62e4ef454575a8341342869172429646bb73c25fa46ec19b291612caf0c41eb7",
        "trained_at": "2026-09-30T15:00:11Z"
    },
    "data_quality": {
        "status": "ok",
        "missing_vitals": [],
        "n_measurements_used": 5,
        "n_excluded_after_cutoff": 0,
        "n_out_of_range": 0
    },
    "warnings": []
}
```

### Partial vitals (`examples/missing_vitals.json`)

```bash
curl -s -X POST localhost:8080/predict \
  -H "Content-Type: application/json" \
  -d @examples/missing_vitals.json | python3 -m json.tool
```

```json
{
    "request_id": "9c956001-ac1d-42b4-805a-60a31693fa58",
    "record_id": "200001",
    "probability": 0.1037,
    "risk_flag": false,
    "threshold": 0.13113858330514636,
    "model": {
        "version": "1.0.0",
        "type": "logistic_regression",
        "git_commit": "7d004194cb7a5e6efc433fd877596e1a6d77b3a0",
        "training_data_sha256": "62e4ef454575a8341342869172429646bb73c25fa46ec19b291612caf0c41eb7",
        "trained_at": "2026-09-30T15:00:11Z"
    },
    "data_quality": {
        "status": "partial",
        "missing_vitals": [
            "HR",
            "RespRate"
        ],
        "n_measurements_used": 2,
        "n_excluded_after_cutoff": 0,
        "n_out_of_range": 0
    },
    "warnings": [
        "No valid measurement for HR, RespRate in the first 24 hours."
    ]
}
```

### Abstention (`examples/no_vitals.json`)

```bash
curl -s -X POST localhost:8080/predict \
  -H "Content-Type: application/json" \
  -d @examples/no_vitals.json | python3 -m json.tool
```

```json
{
    "request_id": "62a0ef3d-818a-4b8b-9cfd-a05b8aa1fe6d",
    "record_id": "200002",
    "probability": null,
    "risk_flag": null,
    "threshold": 0.13113858330514636,
    "model": {
        "version": "1.0.0",
        "type": "logistic_regression",
        "git_commit": "7d004194cb7a5e6efc433fd877596e1a6d77b3a0",
        "training_data_sha256": "62e4ef454575a8341342869172429646bb73c25fa46ec19b291612caf0c41eb7",
        "trained_at": "2026-09-30T15:00:11Z"
    },
    "data_quality": {
        "status": "insufficient",
        "missing_vitals": [
            "HR",
            "RespRate",
            "Temp"
        ],
        "n_measurements_used": 0,
        "n_excluded_after_cutoff": 0,
        "n_out_of_range": 0
    },
    "warnings": [
        "No valid vital sign in the first 24 hours. The model abstains because such inputs are outside what it was trained on."
    ]
}
```

### Invalid request (`examples/invalid.json`)

```bash
curl -s -X POST localhost:8080/predict \
  -H "Content-Type: application/json" \
  -d @examples/invalid.json | python3 -m json.tool
```

Returns HTTP 422 with validation errors for `icu_type` and `time`.

### Health

```bash
curl -s localhost:8080/health
```

```json
{"status":"ok","model_version":"1.0.0"}
```
