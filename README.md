# ICU mortality risk from first-day vitals

This repository predicts in-hospital death during an ICU stay from the first 24 hours of adult vital signs and admission fields (PhysioNet Challenge 2012, set A). It is a Corvita Biomedical take-home exercise in reproducible ML, API serving, monitoring, and infrastructure-as-code. Outputs are risk estimates for demonstration only: not a clinical tool and not applicable to newborns or neonatal incubators.

![CI](https://github.com/RemiJorge/Corvita-Machine-Learning-and-Model-Deployment-Project/actions/workflows/ci.yml/badge.svg)

## Results at a glance

Test set: 600 records, 83 deaths. Metrics from `reports/metrics.json` (1000 bootstrap resamples, 95 % percentile intervals). Baselines: PR-AUC and precision at test prevalence (0.138); AUROC 0.5; Brier of a constant prediction equal to the training death rate (0.139): 0.119.


| Model                        | PR-AUC [95 % CI]     | AUROC [95 % CI]      | Sensitivity [CI]     | Specificity [CI]     | Brier [CI]           |
| ---------------------------- | -------------------- | -------------------- | -------------------- | -------------------- | -------------------- |
| Logistic regression (served) | 0.303 [0.225, 0.399] | 0.741 [0.684, 0.792] | 0.783 [0.687, 0.859] | 0.578 [0.538, 0.620] | 0.110 [0.090, 0.129] |
| Hist. gradient boosting      | 0.350 [0.267, 0.457] | 0.776 [0.724, 0.827] | 0.855 [0.779, 0.927] | 0.578 [0.535, 0.621] | 0.105 [0.090, 0.123] |
| Baseline                     | 0.138                | 0.500                | n/a                  | n/a                  | 0.119                |


**Served model:** logistic regression (`C=0.01`). It is served because validation PR-AUC was higher (0.381 versus 0.371 for HGB). Secondary advantages are size, speed, and readable coefficients. On the test set HGB scores higher on every metric, but the paired bootstrap interval for the PR-AUC difference contains zero. See `docs/decisions/007-served-model-choice.md`.

## Quick start

**Prerequisites:** Python 3.12, [uv](https://docs.astral.sh/uv/), Docker, Terraform 1.9+, GNU make.

1. `make setup`: installs locked dependencies from `uv.lock`.
2. Place PhysioNet set A files in `data/raw/` or let ingest download them; then `make data`: writes `data/manifest.json` and processed tables; expect 4000 records in the manifest.
3. `make reproduce`: rebuilds features, splits, training, metrics, and packaged model; expect split bytes unchanged and metrics within tolerance of committed `reports/metrics.json`.
4. `make check`: ruff and fast pytest; expect exit code 0.
5. `make docker-run`: builds and runs the API on port 8080 (blocks the terminal; use a second shell for steps 6 to 8).
6. `curl -s -X POST localhost:8080/predict -H "Content-Type: application/json" -d @examples/valid.json`: JSON with `data_quality.status` `ok` and a numeric `probability`.
7. `curl -s -X POST localhost:8080/predict -H "Content-Type: application/json" -d @examples/invalid.json`: HTTP 422 with field errors.
8. `curl -s -X POST localhost:8080/predict -H "Content-Type: application/json" -d @examples/missing_vitals.json`: status `partial` and a warning for missing vitals.
9. `make simulate && make monitor`: replays test requests; monitor exits 0 when rates are normal.
10. `make tf-validate`: Terraform format check, init without backend, validate; expect success.

Full API examples: `docs/api.md`. Review demo script: `docs/demo.md`.

## Data and results walkthrough

[notebooks/analysis.ipynb](notebooks/analysis.ipynb) is a read-only tour of cohort statistics, missing-data patterns, test metrics, and committed figures under `reports/`. It does not retrain models or recompute features. Most cells need only `reports/`; histogram cells need processed tables from `make data`. Re-execute locally with `make notebook` (requires dev dependencies from `make setup`).

## How it works

```text
PhysioNet raw files (set A)
  -> ingest (checksums, manifest)
  -> parse + quality (bounds, -1 handling)
  -> tables (24 h cutoff, admission + vitals parquet)
  -> features (19 columns, shared with API)
  -> stratified split (train / val / test IDs in Git)
  -> train (grid search on validation only)
  -> evaluate (single test score, bootstrap CIs)
  -> package (models/1.0.1/ served in Docker; 1.0.0 kept for rollback)
  -> FastAPI /predict (same cleaning + features)
  -> JSON request logs (no patient values) + monitor check
```

- **Data:** source, license, cutoff, and selection bias ([docs/data.md](docs/data.md)).
- **Modeling:** features, split, tuning, threshold, reproduction ([docs/modeling.md](docs/modeling.md)).
- **API:** schemas, abstention, logging ([docs/api.md](docs/api.md)).
- **Operations:** monitoring, release, rollback ([docs/operations.md](docs/operations.md)).
- **Cloud:** Terraform on GCP ([docs/infrastructure.md](docs/infrastructure.md)).



## Input fields

Measurements after minute 1440 are dropped. Outcome fields (`SAPS-I`, `SOFA`, `Length_of_stay`, `Survival`, `In-hospital_death`) are never model inputs.


| Field    | Source             | Unit / values    | Cleaning                                    | Features produced                                      |
| -------- | ------------------ | ---------------- | ------------------------------------------- | ------------------------------------------------------ |
| Age      | `00:00` descriptor | years            | Outside [15, 120] → missing                 | `age`                                                  |
| Gender   | `00:00` descriptor | 0 female, 1 male | `-1` or invalid → missing                   | `gender_male`, `gender_missing`                        |
| ICUType  | `00:00` descriptor | 1 to 4           | Outside [1, 4] → missing                    | `icu_type_1`, `icu_type_2`, `icu_type_3`, `icu_type_4` |
| HR       | time series        | bpm              | `-1` → missing; outside [20, 300] → missing | `hr_count`, `hr_mean`, `hr_last`, `hr_missing`         |
| RespRate | time series        | breaths/min      | `-1` → missing; outside [1, 80] → missing   | `resp_rate_*`                                          |
| Temp     | time series        | °C               | `-1` → missing; outside [25, 45] → missing  | `temp_*`                                               |


Last value at the latest minute uses the highest `row_order` on ties (ADR 004).

## Reproducibility

Pinned: `uv.lock`, `config/config.yaml` (`seed: 42`, `cutoff_minutes: 1440`, `serving.model_version: 1.0.1`), committed split CSVs under `splits/`, `reports/metrics.json`, and `models/1.0.1/metadata.json` for the served artifact (manifest digest `3d13119ba577e31b155e066f68ada7dfafd09bfd0a8aaf147c9ca56970a17062`, split file hashes, hyperparameters). `make reproduce` compares split files byte-for-byte and metrics with tolerance `1e-6`.

Expected differences across machines: floating-point noise below tolerance, Docker build layer timestamps, and `git_dirty` in metadata if the tree changed after packaging. Archives or copies without `.git` still run `make reproduce`; repackaged `metadata.json` then has `git_commit: "unknown"` (committed `models/` in the zip may still list the build commit until you repackage).

## API

`POST /predict` accepts admission fields and a list of `{time, parameter, value}` measurements. Unknown `parameter` values return 422 instead of being dropped. Three data-quality statuses: `ok` (all vitals present), `partial` (one or two missing, still scored), `insufficient` (no valid vitals, abstain: `probability` null). Threshold 0.131 on validation for sensitivity ≥ 0.80; `risk_flag` when probability ≥ threshold.

Example (truncated); see [docs/api.md](docs/api.md) for full responses:

```bash
curl -s -X POST localhost:8080/predict \
  -H "Content-Type: application/json" \
  -d @examples/valid.json
```

Errors: 422 validation, 500 on unexpected server failure. Health: `GET /health` → `{"status":"ok","model_version":"1.0.1"}` (default; override with `MODEL_VERSION` when multiple folders are in the image).

## Monitoring and operations

Each request logs one JSON line to stdout (and to `REQUEST_LOG_PATH` when set): latency, status, missing vitals, flags, not `record_id`, ages, or measurement values. See [docs/operations.md](docs/operations.md) for grep checks.

`make monitor` reads `logs/requests.jsonl`, compares rates to training reference baselines in model metadata, and runs PSI on logged feature bins (no raw values in logs). Exits 0 for `ok` or `not_enough_data`, exits 1 on alert. Simulate bias with `scripts/send_requests.py --shift Temp=+1.5`. Retraining is manual: new training run, shadow period, guardrails, canary, promote revision; rollback by Cloud Run revision or `MODEL_VERSION` in Docker ([docs/operations.md](docs/operations.md)).

## Cloud setup


| Component                   | Role                                           |
| --------------------------- | ---------------------------------------------- |
| Cloud Run `icu-api-<env>`   | HTTPS API, scale to zero, model in image       |
| Artifact Registry `icu-api` | Immutable Docker tags                          |
| GCS artifacts bucket        | Dataset snapshots, models, reports (versioned) |
| Runtime service account     | No GCP roles (least privilege)                 |
| Deployer SA                 | Push images, deploy Run                        |
| Optional budget             | Alert only, does not stop spend                |


Access: callers need `roles/run.invoker`; demo may use `allUsers` (ADR 011). Secrets: none in app; `terraform.tfvars` and `backend.hcl` stay local. State: remote GCS, not in Git. Retention: artifact lifecycle keeps five noncurrent versions; logs 30 days in Cloud Logging. Cost: about $0 for review traffic ([infra/README.md](infra/README.md)). Removal: `terraform destroy`. Recovery: revision rollback, GCS object versions, redeploy in another region ([docs/infrastructure.md](docs/infrastructure.md)).

**Live GCP demo (O1):** `terraform apply` was run once for review; `/health` and smoke traffic were checked. Deployment date, image tag, and redacted plan summary: [infra/README.md](infra/README.md#deployment-log). Org-policy edge cases and cold-start timing under real idle load were not benchmarked.

## Optional extras (beyond F0 to F14)

- **O0:** RespRate missingness vs mechanical ventilation (`reports/data_quality.json`, [docs/data.md](docs/data.md)).
- **O3:** Test-set metrics by ICU type ([reports/subgroups.json](reports/subgroups.json), model card table).
- **O1:** Cloud Run deployed with Terraform; `pull_cloud_logs.sh` runbook in [infra/README.md](infra/README.md).
- **O2:** PSI drift on binned features (`make monitor`, `--shift` on `send_requests.py`).



## Data and citation

PhysioNet Challenge 2012 set A is used under the [Open Data Commons Attribution License v1.0](https://opendatacommons.org/licenses/by/1-0/). When referencing the challenge, cite:

> Predicting In-Hospital Mortality of Patients in ICU: The PhysioNet/Computing in Cardiology Challenge 2012. Ikaro Silva, George Moody, Daniel J Scott, Leo A Celi, Roger G Mark.

Dataset page: [PhysioNet Challenge 2012](https://physionet.org/content/challenge-2012/1.0.0/).

## Limitations

- Set A excludes stays shorter than 48 hours, so early deaths are underrepresented; metrics do not reflect all patients seen at 24 hours.
- Single hospital system, adult ICU, 2012 sensors; three vitals only.
- Test set has 83 events; confidence intervals are wide.
- No external validation; calibration may not transfer.
- Served threshold is a configurable operating point, not a clinical standard.
- PSI on `resp_rate_count` is mostly uninformative (many zero counts in one bin). `icu.psi` imports constants from `icu.train` (acceptable for the exercise; would decouple in production).



## Path to real-world use

External and prospective validation on contemporary cohorts; evaluation without the 48 h inclusion filter; clinician review of sensitivity and alert load; shadow deployment before alerts; software as a medical device lifecycle (IEC 62304, Health Canada) if used for decisions; hospital integration via HL7 FHIR; monitoring with delayed labels and recalibration.

## Project management

Human time: **14 h** of 24 h ([docs/process/TIME_LOG.md](docs/process/TIME_LOG.md)). Required features F0 to F14 closed at `v1.0.0`; post-review fixes, live O1 deploy, and optionals through package **1.4.2** ([CHANGELOG.md](CHANGELOG.md)). Specs and agent rules: [docs/process/](docs/process/). Design choices: [docs/decisions/](docs/decisions/).

## Use of AI tools

Summary by area in [docs/process/AI_USAGE.md](docs/process/AI_USAGE.md). Coding agents implemented features from the specs; the author reviewed code, ran commands, and verified reports. Every part was reviewed, run, and understood by the author before submission.

## Repository layout

```text
config/          config.yaml
data/            manifest.json (raw/processed not in Git)
docs/            data, modeling, model card, API, ops, infra, demo, ADRs, process/
examples/        JSON bodies for curl
infra/           Terraform for GCP
models/1.0.1/    served pipeline and metadata (1.0.0 in image for rollback)
reports/         metrics, tuning, figures, data quality, subgroups
scripts/         send_requests.py, pull_cloud_logs.sh
notebooks/       analysis.ipynb (data and results walkthrough)
splits/          train, val, test record IDs
src/icu/         ingest through API, monitor, and PSI helpers
tests/           pytest suite
```

