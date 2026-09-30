# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- F14: Stop writing `fit_seconds` to `reports/tuning.csv` and `reports/selection.json` so `make reproduce` leaves `git diff splits/ reports/` empty after the demo check (timing is logged at INFO only).
- F14: Preserve `downloaded_at` in `data/manifest.json` when ingest content is unchanged so `models/1.0.0/metadata.json` stays stable across `make reproduce`.

## [1.0.0] - 2026-09-30

### Added

- F13: Final `README.md` (results, quick start, limitations, layout).
- F13: `docs/demo.md` review script per `specs/09_REVIEW_PREP.md`.

### Changed

- F13: Final pass on `docs/model_card.md` (package 1.0.0, abstention, limitations aligned with README).
- F13: Draft `TIME_LOG.md` and `AI_USAGE.md` for human owner confirmation.

### Fixed

- F13: `make reproduce` Makefile typo (`--save-baseline*` → `--save-baseline`).

## [0.13.0] - 2026-09-30

### Added

- F12: Terraform stack under `infra/` for GCP (Cloud Run, Artifact Registry, GCS artifacts, IAM, optional budget and public invoker).
- F12: `docs/infrastructure.md`, `infra/README.md`, ADRs 010 (GCP) and 011 (public invoker demo).
- F12: `make tf-validate` and committed `infra/.terraform.lock.hcl` (google provider ~> 6.0).

### Changed

- F12: `.gitignore` allows `infra/.terraform.lock.hcl`; ignores `infra/terraform.tfvars` and `infra/backend.hcl`.

## [0.12.0] - 2026-09-30

### Added

- F11: GitHub Actions CI workflow (`.github/workflows/ci.yml`) with `python`, `docker`, and `terraform` jobs.

## [0.11.0] - 2026-09-30

### Added

- F10: Structured JSON request logging middleware (`icu/api/request_log.py`) with `REQUEST_LOG_PATH` support.
- F10: `icu.monitor` monitoring check, `make monitor`, and `tests/test_monitor.py`.
- F10: `scripts/send_requests.py` and `make simulate` for demo traffic.
- F10: `docs/operations.md` (monitoring, retrain, release, rollback, log privacy).

### Changed

- F10: `make docker-run` sets `REQUEST_LOG_PATH=/app/logs/requests.jsonl`.
- F10: `docs/api.md` documents logging fields and privacy rules.

## [0.10.0] - 2026-09-30

### Added

- F9: Prediction API (`icu/api/`) with `/predict` and `/health`, reusing `tables`, `quality`, and `features`.
- F9: `Dockerfile`, `examples/*.json`, `tests/test_api.py`, and `docs/api.md`.
- F9: ADRs `008-api-abstention.md` and `009-model-baked-in-image.md`.
- F9: `make api`, `make docker-build`, and `make docker-run`.

### Changed

- F9: `load_model` accepts optional `models_dir` override for `MODELS_DIR`.
- F9: Lazy `matplotlib` import in `evaluate.write_figures` so the API image stays dev-free.

## [0.9.0] - 2026-09-30

### Added

- F8: `icu.artifacts` with `save_model`, `load_model`, `metadata.json`, and `models/1.0.0/` (served pipeline plus comparison HGB).
- F8: `make package` and `make reproduce` with split byte comparison and metrics diff summary (`1e-6` tolerance).
- F8: `tests/test_artifacts.py` (unknown version, sklearn mismatch, training reference, metric compare).

### Changed

- F8: Artifacts section in `docs/modeling.md`; model card code version updated.

## [0.8.0] - 2026-09-30

### Added

- F7: `icu.evaluate` with one-time test scoring, bootstrap CIs, paired bootstrap, calibration figures, and missing-vitals subgroup plus ablation analysis.
- F7: `reports/metrics.json`, `reports/missing_vitals.json`, and `reports/figures/{roc,pr,calibration}.png`; `make evaluate` runs `python -m icu.evaluate`.
- F7: `tests/test_evaluate.py` (bootstrap determinism, served-model rule, test split usage).
- F7: ADR `docs/decisions/007-served-model-choice.md` and initial `docs/model_card.md`; test evaluation section in `docs/modeling.md`.

## [0.7.0] - 2026-09-30

### Added

- F6: `icu.train` with logistic regression and HGB pipelines, validation grid search, and sensitivity-based thresholds.
- F6: `reports/tuning.csv` and `reports/selection.json`; `make train` runs `python -m icu.train`.
- F6: `tests/test_train.py` (train-only imputer, threshold rule, no test split in training code, selection tie-breaks).
- F6: ADRs `docs/decisions/005-no-class-weights.md` and `006-threshold-rule.md`; training section in `docs/modeling.md`.

## [0.6.0] - 2026-09-30

### Added

- F5: `icu.split` with stratified 70/15/15 split from `admission.parquet`, committed `splits/*.csv`.
- F5: `tests/test_split.py` (overlap, determinism, death-rate balance on real data).
- F5: Split procedure and grouping key documented in `docs/modeling.md`.
- F5: `make split` runs `python -m icu.split`.

## [0.5.0] - 2026-09-29

### Added

- F4: `icu.features` with `compute_features`, `FEATURE_COLUMNS`, and `data/processed/features.parquet`.
- F4: `tests/test_features.py` (fixtures, missing vital, tie-break, column order, forbidden columns).
- F4: ADR `docs/decisions/004-tie-breaking-last-vital.md` and `docs/modeling.md` (feature design notes).
- F4: `make features` runs `python -m icu.features`.

## [0.4.0] - 2026-09-29

### Added

- F3: `icu.tables` with `apply_cutoff`, `data/processed/admission.parquet` and `vitals.parquet`.
- F3: Cutoff exclusion and 24 h vital counts merged into `reports/data_quality.json`.
- F3: `tests/test_tables.py` (boundary tests at minutes 1440 and 1441, admission descriptors).
- F3: `make data` runs ingest, parse, quality, and tables; `docs/data.md` documents tables and selection bias.

## [0.3.0] - 2026-09-29

### Added

- F2: `icu.parse` reads set A record files into `data/interim/measurements.parquet` with integrity checks against `Outcomes-a.txt`.
- F2: `icu.quality` applies `-1` and bounds cleaning, deduplicates exact rows, writes `reports/data_quality.json`.
- F2: Synthetic PhysioNet fixtures under `tests/fixtures/` and tests in `tests/test_parse.py`, `tests/test_quality.py`.
- F2: ADRs `docs/decisions/002-physiological-bounds.md` and `003-handling-minus-one.md`.
- F2: `make data` runs ingest, parse, and quality; `make test-data` runs `pytest -m data`.
- F2: Extended `docs/data.md` (parsing, cleaning, quality report, spot-check command).

## [0.2.0] - 2026-09-29

### Added

- F1: `icu.ingest` downloads or verifies PhysioNet set A, optional extraction, and `data/manifest.json`.
- F1: `tests/test_ingest.py` (hashing, checksum verification, manifest writing; no network).
- F1: `docs/data.md` (source, license, manual raw files, manifest fields).
- F1: `make data` runs ingest only.

## [0.1.0] - 2026-09-29

### Added

- F0: Project skeleton with `pyproject.toml`, `uv.lock`, `config/config.yaml`, and `icu.config.load_config()`.
- F0: Empty pipeline and API modules under `src/icu/`, Makefile targets, and `tests/test_config.py`.
