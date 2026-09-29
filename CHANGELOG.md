# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
