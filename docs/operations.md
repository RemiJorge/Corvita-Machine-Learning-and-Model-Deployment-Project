# Operations

Procedures for monitoring, retraining, release, and rollback. The API keeps serving during a monitoring alert unless operators decide otherwise (see Incidents).

## Request log privacy

Structured logs contain request metadata (latency, data-quality status, missing vitals, risk flag) and never patient identifiers or measurements. They do not include `record_id`, age, gender, ICU type, measurement values, or predicted probability.

For drift monitoring, each successful `/predict` log may include `feature_bins`: integer indices into decile bins learned on the training set (plus a missing bin). Bins summarize where a value fell relative to training, without storing the value itself, so logs stay free of reconstructible vitals or age.

To verify a local log file after traffic:

```bash
# Should print 0: no JSON "parameter" keys from request bodies
grep -c '"parameter"' logs/requests.jsonl || true

# Spot-check: record_id must not appear (example uses a distinctive ID in a test request)
grep '424242' logs/requests.jsonl && echo "unexpected match" || echo "ok"
```

Cloud Run sends stdout to Cloud Logging; set `REQUEST_LOG_PATH` only when you need a file on disk (local Docker mount).

## Detecting changing data

1. Run `make monitor` daily on the latest request log (default `logs/requests.jsonl` from config).
2. Exit code `0` with `status: ok` or `not_enough_data` means no alert. Exit code `1` with `status: alert` means at least one rate exceeded training baselines or configured caps.
3. Watch missing rates per vital (`HR`, `RespRate`, `Temp`), `partial_rate`, `insufficient_rate`, `error_rate`, latency p95, and PSI per continuous feature when the window has at least `monitoring.psi_min_requests` successful predicts (default 200). Compare `risk_flag` rate with validation alert load when inputs are stable; a jump in alerts with stable missing rates may indicate population shift, while rising missing rates often point to sensors or ingestion.
4. PSI thresholds are conventions from practice (often 0.1 for investigation and 0.25 for a strong alert), not formal statistical tests. This project alerts when any feature PSI exceeds `monitoring.psi_alert` (default 0.25).
5. When labels arrive, compare PR-AUC, calibration, and Brier on recent labelled records against the model card.

## Monitoring check

```bash
make monitor
```

Reads the log path from `config/config.yaml` (`paths.request_log`) unless you pass `--log`. Baselines come from `training_reference` in the served model `metadata.json`. The window uses the most recent successful `POST /predict` responses (up to `monitoring.window_size`). Fewer than 30 successful requests in that window yields `not_enough_data` and exit code 0. PSI is computed only when the window has at least `monitoring.psi_min_requests` requests (default 200); below that, rate checks still run but PSI is omitted (`psi_status: not_enough_data`).

Simulate traffic against a running API:

```bash
make docker-run   # in another terminal
make simulate
make monitor
```

Simulate a missing sensor:

```bash
python scripts/send_requests.py --n 50 --drop RespRate
make monitor
```

Simulate a biased temperature sensor (needs at least 200 logged predicts for PSI):

```bash
python scripts/send_requests.py --n 200 --shift Temp=+1.5
make monitor
```

## Retraining (manual)

1. Freeze a new data snapshot and record its manifest digest in `data/manifest.json`.
2. Run `make reproduce` with the new snapshot and bump the model version in config before `make package`.
3. On the same held-out test split, compare PR-AUC, sensitivity at the operating threshold, Brier, calibration, alert load, and missing-vitals ablation against the current model.
4. Write an ADR with the numbers and the promote-or-reject decision.

## Releasing a model

1. Shadow: deploy the new version as a second revision that receives copies of requests; log predictions but do not show them clinically. Compare for a defined period.
2. Guardrails before promotion: validation sensitivity at the operating threshold not lower than the current model, alert rate per 100 patients not higher than an agreed margin, Brier not worse, p95 latency under budget, no rise in API error rate.
3. Canary: send a small share of traffic (Cloud Run revision split) and run `make monitor` (or the cloud equivalent) on the canary log stream.
4. Promote to 100 % traffic when guardrails hold.

## Rolling back

- Cloud Run: route 100 % traffic to the previous revision (see `docs/infrastructure.md` when available).
- Local or Docker: restart with the previous `MODEL_VERSION` or image tag. Predictions in logs stay tied to the model version that served them; logs are not rewritten.

## Incidents

If `make monitor` exits 1, notify on-call. The API continues to serve unless operators judge inputs or the model unreliable. The project does not implement a global abstention mode; that would be an operational runbook change. Bedside alarms in NOA do not depend on this cloud service.
