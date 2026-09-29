# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
