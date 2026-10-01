# 02. Roadmap

Features are delivered one at a time, in order. Each ends with a human verification gate. The human owner updates the `Status` column; agents only work on the row marked `CURRENT`.

## Project state

Last updated: 2026-09-30.

| | |
|---|---|
| **Status** | **Submission complete** at package version **1.0.0** (F0 to F14 done) |
| **Current feature** | None. Optional items O1 to O3 only if the human owner requests them |
| **Last completed** | F14: Fresh-clone rehearsal and release (see `specs/handoffs/F14-release.md`) |
| **Read next** | `docs/demo.md` for the live review; optional table at the end of this file |
| **Git** | Branches, merges, commits and tags are owned by the human; tag `v1.0.0` when ready |

Required roadmap features are finished. The cut list is not in use unless the human owner reopens scope.

## Overview and time budget

Human time includes supervision, running commands and reading code. Total budget: 24 h.

| ID | Feature | Version | Human time | Status |
|---|---|---|---|---|
| F0 | Repository bootstrap | 0.1.0 | 0.75 h | done |
| F1 | Download, checksums, manifest | 0.2.0 | 0.75 h | done |
| F2 | Parsing and data quality report | 0.3.0 | 1.5 h | done |
| F3 | 24 h cutoff, admission and vitals tables | 0.4.0 | 1 h | done |
| F4 | Feature computation | 0.5.0 | 1.5 h | done |
| F5 | Stratified split | 0.6.0 | 0.75 h | done |
| F6 | Training, validation selection, threshold | 0.7.0 | 2.5 h | done |
| F7 | Test evaluation and missing-vitals analysis | 0.8.0 | 2 h | done |
| F8 | Model packaging and one-command reproduction | 0.9.0 | 1.25 h | done |
| F9 | Prediction API and Docker image | 0.10.0 | 2.5 h | done |
| F10 | Request logging and monitoring check | 0.11.0 | 1.5 h | done |
| F11 | CI workflow | 0.12.0 | 0.75 h | done |
| F12 | Terraform for GCP | 0.13.0 | 1.75 h | done |
| F13 | Documentation, model card, README | 1.0.0 | 2.5 h | done |
| F14 | Fresh-clone rehearsal and release | 1.0.0 | 1 h | done |
| Buffer | Fixes, review preparation | | 2 h | |

Suggested days: day 1 = F0 to F5, day 2 = F6 to F8, day 3 = F9 to F14.

## Cut list if time runs short

Remove in this order: optional items O1 to O3, the PSI part of monitoring, the paired bootstrap, the HGB grid (keep scikit-learn defaults, say so in an ADR). Never cut: cutoff and split tests, the three API cases, the monitoring check, `terraform validate`, the README, the time log, the list of unfinished work.

---

## F0. Repository bootstrap (0.1.0)

**Status:** done

**Goal.** An empty but runnable project skeleton.

**Deliverables.** `pyproject.toml` with the whitelisted dependencies in runtime and dev groups, `uv.lock`, the folder layout from the conventions spec with empty modules containing only a module docstring, `config/config.yaml`, `icu/config.py` with `load_config()`, `Makefile` with every target (unimplemented ones print "not implemented yet: Fx" and exit 1), `.gitignore`, `.dockerignore`, `CHANGELOG.md`, `TIME_LOG.md`, `AI_USAGE.md`, `docs/decisions/000-template.md`, a minimal `README.md` with the project title and setup command, `tests/test_config.py`.

**Acceptance criteria.**
- `make setup` installs from the lockfile.
- `make check` passes.
- `load_config()` raises a clear error when a key is missing (tested).

**Human verification.**
1. `make setup && make check`: green.
2. `make help`: every target listed with a one-line description.
3. `git status` after `make check`: nothing untracked except expected ignored folders.

**Completion.** Closed 2026-09-29 at version 0.1.0.

---

## F1. Download, checksums, manifest (0.2.0)

**Status:** done

**Spec.** `specs/03_DATA_SPEC.md` sections 1 and 2.

**Goal.** Fetch set A and the outcomes file, verify integrity, record provenance.

**Agent notes.** Work on the human-prepared feature branch only. Raw archives may already sit under `data/raw/`; ingest must still hash, verify, extract if needed, and write `data/manifest.json`. At the end of F1, change the `data` Makefile target so it runs ingest only (parse, quality, and tables stay stubbed until F2 and F3). Bump `pyproject.toml` to 0.2.0 and update `CHANGELOG.md` under `[Unreleased]`.

**Deliverables.** `icu/ingest.py` with `download()`, `sha256_file()`, `verify_against_published()`, `write_manifest()`, `main()`. `data/manifest.json` committed. Tests with a temporary file for hashing and manifest writing (no network in tests).

**Acceptance criteria.**
- Downloading twice does not re-download files already present with the right checksum.
- If PhysioNet publishes `SHA256SUMS.txt`, each downloaded file is compared and a mismatch stops the run with an error.
- The manifest lists dataset version, source URLs, download date, file sizes, SHA-256 of each archive and of each extracted outcome file, and the license shown on the dataset page.

**Human verification.**
1. `make data` (only ingest runs at this stage): files appear in `data/raw/`.
2. Open `data/manifest.json`: checksums present, compare one by hand with `sha256sum data/raw/Outcomes-a.txt`.
3. Run again: log says files are already present and verified.

**Completion.** Closed 2026-09-29 at version 0.2.0. Manifest records 4000 record files; `published_checksums` is null (no PhysioNet sums file used at ingest time).

---

## F2. Parsing and data quality report (0.3.0)

**Status:** done

**Spec.** `specs/03_DATA_SPEC.md` sections 3 to 6.

**Goal.** One long table of all measurements, cleaned according to written rules, and a quality report.

**Agent notes.** Work on the human-prepared feature branch only. If parsed record counts or file layout differ from the data spec, stop and ask the human. At the end of F2, extend `make data` to run ingest, then `python -m icu.parse`, then `python -m icu.quality` (leave `icu.tables` stubbed until F3). Add `docs/decisions/002-physiological-bounds.md` and `003-handling-minus-one.md` after checking real distributions in `reports/data_quality.json`. Bump `pyproject.toml` to 0.3.0 and update `CHANGELOG.md`. Wire `make test-data` to `pytest -m data` once at least one test uses that marker (optional in F2 if all tests use fixtures).

**Deliverables.** `icu/parse.py`, `icu/quality.py`, `data/interim/measurements.parquet`, `reports/data_quality.json`, synthetic fixtures in `tests/fixtures/` (three or four small patient files in the exact PhysioNet format, including a `-1` value, an out-of-range value, a duplicate timestamp and a measurement after 24:00). ADRs: physiological bounds, handling of `-1`.

**Acceptance criteria.**
- Number of parsed records equals number of files and number of rows in `Outcomes-a.txt`; the join on `RecordID` is one to one (asserted).
- Time strings are converted to integer minutes; malformed rows raise an error naming the file and line.
- `-1` becomes missing everywhere, and the count per parameter is reported.
- Values outside physiological bounds become missing and are counted per parameter.
- The quality report contains the numbers listed in the data spec.

**Human verification.**
1. `make data`, then open `reports/data_quality.json`: record count, death rate, missing rate and out-of-range count per vital.
2. Pick one raw file, compare three of its lines with the Parquet table (`python -c` one-liner documented in `docs/data.md`).
3. Read the bounds ADR and check the chosen bounds against the percentiles in the report.

**Completion.** Closed 2026-09-29 at version 0.3.0. Quality report: 4000 records, death rate 13.85 %, ADRs `002-physiological-bounds` and `003-handling-minus-one`.

---

## F3. 24 h cutoff, admission and vitals tables (0.4.0)

**Status:** done

**Spec.** `specs/03_DATA_SPEC.md` sections 5 and 7.

**Agent notes.** Work on the human-prepared feature branch only. Implement `apply_cutoff` in a place reusable by the API later (`tables.py` or a small shared helper imported by `icu.api.service` in F9). At the end of F3, extend `make data` to run ingest, parse, quality, then `python -m icu.tables`. Merge cutoff exclusion counts into `reports/data_quality.json` per the data spec schema. Add `tests/test_tables.py` with named boundary tests (`test_cutoff_keeps_1440`, `test_cutoff_drops_1441`). Bump `pyproject.toml` to 0.4.0 and update `CHANGELOG.md`. Document selection bias (data spec section 8) in `docs/data.md` when tables exist.

**Deliverables.** `icu/tables.py` producing `admission.parquet` and `vitals.parquet`. Tests: a measurement at minute 1440 is kept, at 1441 is excluded; admission fields are taken from the 00:00 descriptor rows only.

**Acceptance criteria.**
- `vitals.parquet` contains only `HR`, `RespRate`, `Temp` with `minute <= cutoff_minutes`.
- The number of rows excluded by the cutoff is logged and added to the quality report.
- `admission.parquet` has exactly one row per RecordID.

**Human verification.**
1. `pytest tests/test_tables.py -v`: boundary tests visible by name.
2. `python -c "import pandas as pd; print(pd.read_parquet('data/processed/vitals.parquet').minute.max())"` prints 1440 or less.

**Completion.** Closed 2026-09-29 at version 0.4.0. `apply_cutoff` in `icu.tables`; 4000 admission rows; vitals capped at minute 1440; quality report includes `n_after_cutoff` per vital.

---

## F4. Feature computation (0.5.0)

**Status:** done

**Spec.** `specs/04_MODELING_SPEC.md` section 1.

**Agent notes.** Work on the human-prepared feature branch only. `compute_features` must be shared by training and the API (no duplicate logic in F9). Drop `in_hospital_death` from the feature output; test forbidden columns. Add ADR `004-tie-breaking-last-vital.md` for last-value rule. Wire `make features` to `python -m icu.features`. Bump `pyproject.toml` to 0.5.0 and update `CHANGELOG.md`. Start `docs/modeling.md` with the design notes from the modeling spec section 1.

**Deliverables.** `icu/features.py` with `compute_features(admission_df, vitals_df) -> DataFrame` usable on one patient or many, `FEATURE_COLUMNS` constant, `FORBIDDEN_COLUMNS` constant, `data/processed/features.parquet`. ADR: tie-breaking for the last value.

**Acceptance criteria.**
- Hand-computed expected features for the synthetic fixtures match exactly (tested).
- A patient with no `RespRate` gets count 0, mean and last missing, flag 1.
- Output columns equal `FEATURE_COLUMNS`, in that order. No forbidden column can appear (tested).
- Runs in under a few seconds on the full dataset.

**Human verification.**
1. Pick one RecordID, compute its HR mean and last value by hand from the raw file, compare with `features.parquet`.
2. Read `features.py` top to bottom and check that it is understandable in one read.

**Completion.** Closed 2026-09-30 at version 0.5.0. Nineteen `FEATURE_COLUMNS`, ADR `004-tie-breaking-last-vital`, `docs/modeling.md`, five feature tests on fixtures.

---

## F5. Stratified split (0.6.0)

**Status:** done

**Spec.** `specs/04_MODELING_SPEC.md` section 2.

**Agent notes.** Work on the human-prepared feature branch only. Load labels from `admission.parquet` only (not from outcomes file directly). Commit `splits/*.csv` with sorted `record_id` column. Wire `make split` to `python -m icu.split`. Add `tests/test_split.py` including overlap, coverage, determinism, and at least one `@pytest.mark.data` test for death-rate balance within 1 pp. Document rounding in `docs/modeling.md`. Bump `pyproject.toml` to 0.6.0 and update `CHANGELOG.md`.

**Deliverables.** `icu/split.py`, `splits/train_ids.csv`, `splits/val_ids.csv`, `splits/test_ids.csv`, tests.

**Acceptance criteria.**
- 70 / 15 / 15 of RecordIDs (rounding documented), stratified on the outcome, seed from config.
- No RecordID in two files; union equals all RecordIDs (tested).
- Death rates of the three groups within 1 percentage point of each other (tested on real data under the `data` marker).
- Running twice produces byte-identical files (tested).

**Human verification.**
1. `make split` twice, `git diff splits/`: empty.
2. Log shows size and death rate of each group.

**Completion.** Closed 2026-09-30 at version 0.6.0. Split sizes 2800 / 600 / 600; death rates within 0.03 pp; committed `splits/*.csv` deterministic on rerun.

---

## F6. Training, validation selection, threshold (0.7.0)

**Status:** done

**Spec.** `specs/04_MODELING_SPEC.md` sections 3 to 5.

**Agent notes.** Work on the human-prepared feature branch only. Fit on train rows only; never load test IDs in `train.py`. Write every grid row to `reports/tuning.csv`; selection and thresholds to `reports/selection.json`. ADRs `005-no-class-weights.md` and `006-threshold-rule.md`. Wire `make train` to `python -m icu.train`. Add tests that imputer medians match train and that `test_ids` does not appear in `train.py`. Do not refit on train+val. Bump `pyproject.toml` to 0.7.0 and extend `docs/modeling.md` (tuning tie-break, no refit on val). Update `CHANGELOG.md`.

**Deliverables.** `icu/train.py`, `reports/tuning.csv`, chosen settings and thresholds saved to `reports/selection.json`. ADRs: no class weights, threshold rule.

**Acceptance criteria.**
- Both pipelines fit on train only. Validation is used only to score grid candidates and to pick the threshold (tested by checking that fitted imputer medians equal train medians).
- Every grid candidate is written to `tuning.csv` with validation PR-AUC, AUROC and Brier.
- The chosen threshold reaches the target sensitivity on validation; the resulting validation specificity and alerts per 100 patients are saved.
- The test set is not loaded by `train.py` at all.

**Human verification.**
1. `make train`, open `reports/tuning.csv`, check the selected row is the best by the written rule.
2. `grep -n test_ids src/icu/train.py`: no match.

**Completion.** Closed 2026-09-30 at version 0.7.0. Twenty grid candidates in `tuning.csv`; `selection.json` with logreg `C=0.01` (val PR-AUC 0.381) and HGB grid winner; validation sensitivity at or above 0.80 for both thresholds; ADRs 005 and 006.

---

## F7. Test evaluation and missing-vitals analysis (0.8.0)

**Status:** done

**Spec.** `specs/04_MODELING_SPEC.md` sections 6 to 8.

**Agent notes.** Work on the human-prepared feature branch only. This is the **first** scoring of the test set: load frozen `selection.json`, refit is not allowed on test. Write `reports/metrics.json` (bootstrap CIs, baselines, paired bootstrap for PR-AUC and AUROC), `reports/missing_vitals.json` (subgroups + ablation), figures under `reports/figures/`. ADR `007-served-model-choice.md` must cite **validation** metrics only as the decision reason. Wire `make evaluate` to `python -m icu.evaluate`. Bump `pyproject.toml` to 0.8.0; start or extend `docs/model_card.md` with real numbers. Do not package models yet (F8).

**Deliverables.** `icu/evaluate.py`, `reports/metrics.json`, `reports/missing_vitals.json`, figures (ROC, precision-recall, calibration for both models), ADR: served model choice.

**Acceptance criteria.**
- Test metrics for both models with 95 % bootstrap intervals and naive baselines.
- Calibration curve and Brier for both models.
- Missing-vitals subgroup results and the ablation described in the modeling spec.
- The served model is chosen from validation results and the ADR says so explicitly.

**Human verification.**
1. `make evaluate`, open the three figures.
2. Read `metrics.json`: every metric has a value, an interval and a baseline.
3. Check that the served-model ADR cites validation numbers, not test numbers.

**Completion.** Closed 2026-09-30 at version 0.8.0. Served model `logistic_regression` (ADR 007); `metrics.json`, `missing_vitals.json`, three figures; paired bootstrap PR-AUC interval contains zero.

---

## F8. Model packaging and one-command reproduction (0.9.0)

**Status:** done

**Spec.** `specs/04_MODELING_SPEC.md` section 9.

**Deliverables.** `icu/artifacts.py`, `models/1.0.0/pipeline.joblib`, `models/1.0.0/metadata.json`, working `make reproduce`.

**Acceptance criteria.**
- `metadata.json` follows the schema in the modeling spec, including the git commit and the manifest digest.
- `make reproduce` from a clean `data/processed` rebuilds everything and reports "splits identical, metrics identical" or lists differences with their size.
- `load_model(version)` returns the pipeline and metadata and fails clearly on an unknown version.

**Human verification.**
1. `make clean && make reproduce`: summary shows no difference.
2. Open `metadata.json` and check the commit hash against `git log -1`.

**Completion.** Closed 2026-09-30 at version 0.9.0. `models/1.0.0/` with served logreg pipeline, comparison HGB, `metadata.json`; `make reproduce` with baseline compare.

---

## F9. Prediction API and Docker image (0.10.0)

**Status:** done

**Spec.** `specs/05_API_SPEC.md`.

**Agent notes.** Work on the human-prepared feature branch only. Reuse `apply_cutoff` from `icu.tables`, bounds from `icu.quality`, and `compute_features` from `icu.features` (no duplicated logic). Load model via `icu.artifacts.load_model` and `MODEL_VERSION` env (default from config). Implement `examples/valid.json`, `invalid.json`, `missing_vitals.json`, and `no_vitals.json` per API spec. ADRs `008-api-abstention.md` and `009-model-baked-in-image.md`. Wire `make api`, `docker-build`, `docker-run`; leave structured request logging for F10. Bump `pyproject.toml` to **0.10.0** and add `docs/api.md`. Update `CHANGELOG.md`.

**Deliverables.** `icu/api/`, `Dockerfile`, `examples/*.json`, `tests/test_api.py`. ADRs: abstention rule, model baked into the image.

**Acceptance criteria.**
- The API reuses `quality.py` bounds and `features.py`; no duplicated feature logic (checked in review).
- Valid, invalid and missing-vitals examples behave as specified (tested).
- The prediction for a test-set patient sent through the API equals the offline prediction for the same RecordID to 1e-9 (tested under the `data` marker).
- Image runs as a non-root user, exposes port 8080, has a health check, and contains no dev dependency.

**Human verification.**
1. `make docker-run`, then the three `curl` commands from `docs/api.md`; compare with the documented responses.
2. `curl localhost:8080/health`: model version shown.
3. `docker image ls`: note the image size for the README.

**Completion.** Closed 2026-09-30 at version 0.10.0. `icu/api/`, Dockerfile, four examples, `docs/api.md`, ADRs 008 to 009; `make api` and `docker-build`/`docker-run`; 53 fast tests including API suite.

---

## F10. Request logging and monitoring check (0.11.0)

**Status:** done

**Spec.** `specs/05_API_SPEC.md` section 7 and `specs/06_QUALITY_CI_MONITORING_SPEC.md` section 4.

**Agent notes.** Work on the human-prepared feature branch only. Implement request logging middleware per API spec §7 (no patient values in JSONL). Wire `REQUEST_LOG_PATH` / `logs/requests.jsonl` for local `make docker-run`. Add `icu/monitor.py`, `scripts/send_requests.py`, wire `make simulate` and `make monitor`. Tests with synthetic log files per monitoring spec §4. Start `docs/operations.md` (retrain, release, rollback procedures from spec §6). Bump `pyproject.toml` to **0.11.0**. PSI drift (O2) is out of scope unless time after F14.

**Deliverables.** JSON request logging in the API, `icu/monitor.py`, `scripts/send_requests.py`, `docs/operations.md` first version.

**Acceptance criteria.**
- One JSON line per request with the fields listed in the API spec and no patient values.
- `make monitor` prints a JSON summary and exits 0 when rates are normal, 1 when the missing-vital rate exceeds the threshold (both cases tested with synthetic log files).
- `scripts/send_requests.py --drop RespRate` can simulate a sensor outage for the demo.

**Human verification.**
1. `make docker-run`, `make simulate`, `make monitor`: exit code 0.
2. `python scripts/send_requests.py --drop HR,RespRate,Temp --n 50`, then `make monitor`: alert and exit code 1.
3. `grep -c '"HR"' logs/requests.jsonl` style check documented in `docs/operations.md`: no vital values in logs.

**Completion.** Closed 2026-09-30 at version 0.11.0. `request_log` middleware, `icu.monitor`, `send_requests.py`, `docs/operations.md`; `make simulate` / `make monitor`; monitor tests in fast suite (59 tests total).

---

## F11. CI workflow (0.12.0)

**Status:** done

**Spec.** `specs/06_QUALITY_CI_MONITORING_SPEC.md` section 3.

**Agent notes.** Work on the human-prepared feature branch only. Add `.github/workflows/ci.yml` with `python`, `docker`, and `terraform` jobs as in the monitoring spec (Python 3.12, `uv sync --frozen`, ruff, pytest `-m "not data"`, docker build + health + `valid.json` smoke POST, `terraform fmt -check` and `validate` with `-backend=false`). The terraform job requires `infra/` (F12); if needed, ask the human to do F12 first or on the same branch so CI is green. Pin action majors that exist at implementation time. Bump `pyproject.toml` to **0.12.0**. Add CI status badge to `README.md` after the human confirms green Actions. No secrets, no deploy. Update `CHANGELOG.md`.

**Deliverables.** `.github/workflows/ci.yml`.

**Acceptance criteria.** On push and pull request: lockfile install, lint, format check, fast tests, Docker build, Terraform format check and validate. Green on GitHub.

**Human verification.** Push the branch, open the Actions tab, check every job is green, add the badge to the README.

**Completion.** Closed 2026-09-30 at version 0.12.0. `.github/workflows/ci.yml` with `python`, `docker`, and `terraform` jobs. CI badge on README when the human confirms green Actions (optional until push).

---

## F12. Terraform for GCP (0.13.0)

**Status:** done

**Spec.** `specs/07_INFRA_SPEC.md`.

**Agent notes.** Work on the human-prepared feature branch only. Create full `infra/` tree per infra spec; wire `make tf-validate` (replace F12 stub). Commit `.terraform.lock.hcl`. ADRs `010-gcp-target-cloud.md` and `011-public-invoker-demo.md` (or next free numbers). Add `docs/infrastructure.md` mapping each resource to `main.tf`. `infra/README.md` with pasted `terraform init -backend=false` and `validate` output, cost estimate, untested steps. No `terraform apply`, no real project IDs in Git. Bump `pyproject.toml` to **0.13.0**. After F12, the CI `terraform` job should pass on push.

**Deliverables.** `/infra` files, `infra/README.md` with outputs of `terraform init -backend=false` and `terraform validate`, cost estimate, list of untested steps. ADRs: GCP as target cloud, public invoker for the demo only.

**Acceptance criteria.** `make tf-validate` passes. Provider versions pinned and `.terraform.lock.hcl` committed. No project ID, billing account or email hardcoded.

**Human verification.** `make tf-validate`; read `main.tf` and check that each resource maps to a line in `docs/infrastructure.md`.

**Completion.** Closed 2026-09-30 at version 0.13.0. `infra/` stack, lockfile, `make tf-validate` green, `docs/infrastructure.md`, ADRs 010 to 011.

---

## F13. Documentation, model card, README (1.0.0)

**Status:** done

**Spec.** `specs/08_DOCUMENTATION_SPEC.md`.

**Acceptance criteria.** Every section listed in the documentation spec exists and contains real numbers from `reports/`. `TIME_LOG.md` and `AI_USAGE.md` are filled by the human owner with the agent's help.

**Human verification.** Read the README as a reviewer in 10 minutes. Every command in it is run once, in order.

**Completion.** Closed 2026-09-30 at version **1.0.0**. Final `README.md`, `docs/demo.md`, model card pass, `make reproduce` typo fixed. Human owner validated README/docs and signed off `TIME_LOG.md` / `AI_USAGE.md` (total 6 h 30 logged of 24 h budget).

---

## F14. Fresh-clone rehearsal and release (1.0.0)

**Status:** done

**Goal.** Prove the submission works for someone else.

**Agent notes.** Human-led rehearsal; agent only fixes blockers found during clone/README walkthrough. Follow `docs/demo.md`. Finalize `TIME_LOG.md` and `AI_USAGE.md` with the human owner. Tag `v1.0.0` is human-owned after approval. Optional O1 to O3 only after F14 is accepted.

**Steps.**
1. Clone the repository into an empty folder.
2. Follow the README from top to bottom without prior knowledge: setup, data, reproduce, tests, docker, three requests, monitor, tf-validate.
3. Fix anything that fails, update the changelog, tag `v1.0.0`.
4. Rehearse the demo in `docs/demo.md` once, aloud, in English.

**Completion.** Closed 2026-09-30 at version **1.0.0**. Fresh-clone / README path validated; reproduce demo check stable (`fit_seconds` out of committed reports, `manifest.downloaded_at` preserved on re-ingest). `make check` green (60 fast tests). Git tag `v1.0.0` remains human-owned.

---

## Optional items (only after F14)

| ID | Item | Value |
|---|---|---|
| O1 | Real deployment on Cloud Run free tier with `terraform apply`, URL in the README, `terraform destroy` after the review | Shows the infra works end to end |
| O2 | PSI drift check per feature in `monitor.py` against training reference distributions | Stronger monitoring story |
| O3 | Test metrics by `ICUType` with intervals | Subgroup comparison, listed as optional by the brief |
