# 06. Quality, CI and monitoring

## 1. Test strategy

| Layer | Scope | Data | Runs in CI |
|---|---|---|---|
| Unit | Parsing, cleaning, cutoff, features, split, threshold, bootstrap | Synthetic fixtures | yes |
| Integration | Fixture files through the whole pipeline into a small model | Synthetic fixtures | yes |
| API | Every behaviour in the API spec with `TestClient` | Fixture model from `conftest.py` | yes |
| Data | Checks on the real dataset (counts, join, death rates, API vs offline parity) | Real files | no, marker `data`, run with `make test-data` |

Rules:

- Test names describe the behaviour: `test_cutoff_drops_1441`, not `test_cutoff_2`.
- One behaviour per test. Arrange, act, assert, with no logic in the assertions.
- No network, no sleep, no dependence on test order.
- Coverage is not a target. Every rule written in a spec has at least one test; that is the target.
- The pytest marker `data` is registered in `pyproject.toml` so unknown-marker warnings never appear.

### Fixtures

`tests/fixtures/set-a/` holds four or five tiny record files in the exact PhysioNet format and `tests/fixtures/Outcomes-a.txt` for them. Between them they cover: a normal record, a record without RespRate, a record with `-1` values, a record with an out-of-range HR and a duplicate row, a record with measurements at 24:00 and 24:01. Expected features for each are written by hand in the test file, not computed by the code under test.

The integration test needs both classes to train a model, so the fixture set generator in `conftest.py` may replicate the hand-written records with small variations and fixed seeds to reach a few dozen records. Keep that code short and commented.

## 2. Lint and format

`ruff check .` and `ruff format --check .` with the configuration from the conventions spec. `make check` runs lint then tests and is the single command agents run before any handoff.

## 3. CI workflow (`.github/workflows/ci.yml`)

Implemented in F11 (`.github/workflows/ci.yml`). The `terraform` job passes once F12 `infra/` exists and `make tf-validate` is green locally.

Triggers: `push` to any branch and `pull_request` to `main`. Three jobs.

```yaml
name: ci

on:
  push:
  pull_request:
    branches: [main]

jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6       # check the current major version at implementation time
        with:
          python-version: "3.12"
      - run: uv sync --frozen
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pytest -m "not data"

  docker:
    runs-on: ubuntu-latest
    needs: python
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t corvita-icu-api:ci .
      - run: |
          docker run -d -p 8080:8080 --name api corvita-icu-api:ci
          for i in $(seq 1 20); do curl -sf localhost:8080/health && break; sleep 1; done
          curl -sf -X POST localhost:8080/predict -H "Content-Type: application/json" -d @examples/valid.json

  terraform:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3  # check the current major version at implementation time
      - run: terraform -chdir=infra fmt -check -recursive
      - run: terraform -chdir=infra init -backend=false
      - run: terraform -chdir=infra validate
```

Notes:

- Pin action versions to a major tag that exists at implementation time.
- The Docker job builds with the committed `models/1.0.0/`, so it tests the real serving image. The smoke test proves the image starts and answers.
- No secrets are used by CI. Nothing is deployed by CI in this project; the README describes how a deploy job would be added (build, push to Artifact Registry, `terraform apply` with a workload identity, manual approval for production).

## 4. Monitoring check (`icu/monitor.py`)

Implemented in F10 (`make monitor`, `tests/test_monitor.py`).

### Purpose

Detect when incoming requests carry much more missing vital data than training, which in NOA would mean a sensor outage, a detached probe, a firmware change, or a change in clinical practice. The model's output would degrade silently in that case, so it must raise an alert.

### Inputs

- `logs/requests.jsonl` (path from config or `--log`).
- `training_reference` from the served model's `metadata.json`.

### Computation

Over the most recent `monitoring.window_size` successful `/predict` requests:

| Metric | Definition |
|---|---|
| `n_requests` | Requests in the window |
| `missing_rate[vital]` | Share of requests where that vital was missing |
| `partial_rate` | Share with status `partial` |
| `insufficient_rate` | Share with status `insufficient` |
| `error_rate` | Share of all requests in the window with status 4xx or 5xx |
| `latency_p50_ms`, `latency_p95_ms` | From `latency_ms` |

### Alert rules

- `partial_rate` exceeds the training `partial_rate` by more than `monitoring.max_partial_rate_increase` (absolute).
- `insufficient_rate` exceeds `monitoring.max_insufficient_rate`.
- For each vital, `missing_rate` exceeds its training value by more than `max_partial_rate_increase`.
- Fewer than 30 requests in the window: no alert, status `not_enough_data`, exit code 0.

### Output

A JSON summary on stdout (window, metrics, reference values, list of triggered alerts, status `ok` or `alert`). Exit code 0 when `ok` or `not_enough_data`, 1 when `alert`. The exit code makes it usable from cron, a scheduler or CI without parsing.

### Optional (O2): distribution drift

Population Stability Index per continuous feature, comparing recent requests with `training_reference.feature_quantiles`. This requires logging binned feature values, which must stay free of identifying information. Implement only after F14 and document the privacy reasoning.

### Tests

`test_monitor_ok`, `test_monitor_alert_on_missing_rate`, `test_monitor_alert_on_insufficient`, `test_monitor_not_enough_data`, each with a synthetic log file written in the test.

## 5. Demo traffic script (`scripts/send_requests.py`)

Reads test-set records from the processed tables, converts each to a request body, posts it to the API.

```
python scripts/send_requests.py --n 100                    # normal traffic
python scripts/send_requests.py --n 50 --drop RespRate     # simulate a missing sensor
python scripts/send_requests.py --n 50 --drop HR,RespRate,Temp
```

Standard library `urllib` only. Short and readable: it is a demo tool, not part of the product.

## 6. Operations procedures (content of `docs/operations.md`)

The brief asks for explanations, not automation. Write each as a short procedure with the commands.

### Detecting changing data

- Daily run of `make monitor` on the last window (in the cloud: a scheduled job reading Cloud Logging; not built here, as the brief allows).
- Watch: missing rates per vital, status rates, error rate, latency p95, share of `risk_flag = true` compared with the validation alert rate. A sudden change in alert rate with stable inputs points to a population change; a change in missing rates points to a data pipeline or sensor problem.
- Label-based checks once outcomes arrive: PR-AUC, calibration and Brier on recent labelled records, compared with the model card.

### Retraining (manual)

1. Freeze a new data snapshot and record its manifest.
2. Run `make reproduce` with the new snapshot and a new model version.
3. Compare with the current model on the same held-out data: PR-AUC, sensitivity at the operating threshold, Brier, calibration curve, alert load, missing-vitals ablation.
4. Write an ADR with the numbers and the decision.

### Releasing a model

1. Shadow: deploy the new version as a second service or revision receiving copies of requests, predictions logged, never shown. Compare for a defined period.
2. Guardrails to pass before promotion: sensitivity at the operating threshold not lower than the current model, alert rate per 100 patients not higher by more than an agreed margin, Brier not worse, p95 latency under budget, no increase in error rate.
3. Canary: send a small share of traffic (Cloud Run revision traffic split) and watch the monitoring metrics.
4. Promote to 100 %.

### Rolling back

- Cloud Run keeps previous revisions: send 100 % of traffic back to the previous revision (one command, documented in `docs/infrastructure.md`).
- Locally or with Docker: restart with the previous `MODEL_VERSION` or image tag.
- Predictions made by a version stay attributed to that version in the logs; they are never rewritten.

### Incident behaviour

If the monitoring check alerts, the API keeps serving but the alert goes to the on-call engineer; if the model or its inputs are judged unreliable, the service can be switched to a mode that returns only abstentions until fixed (described in the docs, not built in this project). In NOA, bedside alarms never depend on this cloud service.
