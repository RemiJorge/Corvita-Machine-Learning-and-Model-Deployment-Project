# 01. Architecture and conventions

## 1. Technical stack

| Item | Choice | Reason |
|---|---|---|
| Language | Python 3.12 | Current stable, supported by every library below |
| Environment and lockfile | `uv` with `pyproject.toml` and `uv.lock` | One tool, exact versions, fast installs, used in CI and Docker |
| Data | pandas + pyarrow (Parquet) | Standard, columnar storage for intermediate tables |
| Models | scikit-learn | Both required models, pipelines and metrics in one library |
| Serialization | joblib | Standard for scikit-learn pipelines |
| API | FastAPI + Pydantic v2 + uvicorn | Required by the brief, validation built in |
| Config | PyYAML | One readable `config/config.yaml` |
| Figures | matplotlib | ROC, precision-recall and calibration plots |
| Tests | pytest + httpx (FastAPI TestClient) | Standard |
| Lint and format | ruff | One tool for both |
| Containers | Docker | Required by the brief |
| Infra as code | Terraform with the `hashicorp/google` provider | See `specs/07_INFRA_SPEC.md` |
| CI | GitHub Actions | One workflow |
| Task runner | GNU Make | Short, readable entry points for every command |

### Dependency whitelist

Runtime group (installed in the Docker image): `numpy`, `pandas`, `pyarrow`, `scikit-learn`, `joblib`, `fastapi`, `uvicorn`, `pydantic`, `pyyaml`.

Dev group (never in the image): `pytest`, `httpx`, `ruff`, `matplotlib`.

Standard library only for: download (`urllib.request`), archives (`tarfile`, `zipfile`), hashing (`hashlib`), CLI (`argparse`), logging (`logging`, `json`), paths (`pathlib`), timing (`time.perf_counter`), IDs (`uuid`).

Not allowed without an ADR and human approval: XGBoost, LightGBM, CatBoost, MLflow, DVC, Hydra, Typer, Click, Poetry, pre-commit, mypy, SQLAlchemy, any database, any cloud SDK in the Python code.

`HistGradientBoostingClassifier` from scikit-learn is the tree-based model. It handles missing values natively and adds no dependency.

## 2. Repository layout

```
corvita-icu-mortality/
├── AGENTS.md
├── CLAUDE.md
├── README.md
├── CHANGELOG.md
├── TIME_LOG.md
├── AI_USAGE.md
├── LICENSE                      # MIT for the code; data license documented separately
├── Makefile
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── .dockerignore
├── .gitignore
├── config/
│   └── config.yaml
├── specs/                       # these specification files
├── docs/
│   ├── data.md
│   ├── modeling.md
│   ├── model_card.md
│   ├── api.md
│   ├── operations.md            # monitoring, drift, retraining, release, rollback
│   ├── infrastructure.md
│   ├── demo.md                  # review script
│   └── decisions/
│       ├── 000-template.md
│       └── 001-....md
├── data/                        # git-ignored except the manifest
│   ├── raw/
│   ├── interim/
│   ├── processed/
│   └── manifest.json            # committed
├── splits/                      # committed
│   ├── train_ids.csv
│   ├── val_ids.csv
│   └── test_ids.csv
├── models/                      # committed, small
│   └── 1.0.0/
│       ├── pipeline.joblib
│       └── metadata.json
├── reports/                     # committed
│   ├── data_quality.json
│   ├── tuning.csv
│   ├── metrics.json
│   ├── missing_vitals.json
│   └── figures/
├── examples/                    # API request bodies
│   ├── valid.json
│   ├── invalid.json
│   └── missing_vitals.json
├── logs/                        # git-ignored, request logs for the monitoring check
├── scripts/
│   └── send_requests.py         # replays test records against the API for the demo
├── src/icu/
│   ├── __init__.py
│   ├── config.py                # load and validate config.yaml
│   ├── ingest.py                # download, checksums, manifest
│   ├── parse.py                 # raw text files -> long table
│   ├── quality.py               # bounds, -1 handling, quality report
│   ├── tables.py                # 24 h cutoff, admission and vitals tables
│   ├── features.py              # feature computation, shared by training and API
│   ├── split.py                 # stratified RecordID split
│   ├── train.py                 # pipelines, tuning on validation, threshold
│   ├── evaluate.py              # test metrics, bootstrap, calibration, missing-vitals analysis
│   ├── artifacts.py             # save and load model folders and metadata
│   ├── monitor.py               # monitoring check on the request log
│   └── api/
│       ├── __init__.py
│       ├── app.py               # FastAPI app, routes, middleware
│       ├── schemas.py           # Pydantic request and response models
│       └── service.py           # request -> features -> prediction -> response
├── tests/
│   ├── conftest.py
│   ├── fixtures/                # small synthetic PhysioNet-format files
│   └── test_*.py
├── infra/                       # Terraform, see specs/07
└── .github/workflows/ci.yml
```

Every module under `src/icu/` that runs a pipeline step exposes `main()` and runs with `python -m icu.<module>`. Arguments use `argparse` and default to paths from the config.

## 3. Data flow

```
PhysioNet files (set-a, Outcomes-a.txt)
  -> ingest.py    data/raw/ + data/manifest.json (SHA-256, version, URLs, date)
  -> parse.py     data/interim/measurements.parquet (RecordID, minute, parameter, value)
  -> quality.py   bounds and -1 handling, reports/data_quality.json
  -> tables.py    data/processed/admission.parquet, data/processed/vitals.parquet (minute <= 1440)
  -> features.py  data/processed/features.parquet (one row per RecordID)
  -> split.py     splits/*.csv
  -> train.py     reports/tuning.csv, chosen settings, threshold
  -> evaluate.py  reports/metrics.json, reports/missing_vitals.json, reports/figures/*
  -> artifacts.py models/<version>/pipeline.joblib + metadata.json
  -> api/         POST /predict (reuses quality.py bounds and features.py)
  -> monitor.py   reads logs/requests.jsonl, exit code 1 on alert
```

The API imports the same bound-checking and feature functions as the training pipeline. This is the main guarantee against training-serving skew and it must stay that way.

## 4. Configuration

A single `config/config.yaml`, loaded once by `icu.config.load_config()` into a frozen dataclass or a plain dict validated at load time. Missing keys raise an error with the key name. Expected top-level keys:

```yaml
seed: 42

paths:
  raw_dir: data/raw
  interim_dir: data/interim
  processed_dir: data/processed
  manifest: data/manifest.json
  splits_dir: splits
  models_dir: models
  reports_dir: reports
  request_log: logs/requests.jsonl

source:
  dataset_version: "1.0.0"
  base_url: "https://physionet.org/files/challenge-2012/1.0.0/"
  files: ["set-a.tar.gz", "Outcomes-a.txt"]   # verify names on the dataset page before F1

cutoff_minutes: 1440          # inclusive

vitals: ["HR", "RespRate", "Temp"]

physiological_bounds:          # inclusive; values outside become missing and are counted
  HR: [20, 300]
  RespRate: [1, 80]
  Temp: [25.0, 45.0]

admission_bounds:
  Age: [15, 120]               # adjust to the observed range in F2, record in an ADR
  ICUType: [1, 4]

split:
  train: 0.70
  val: 0.15
  test: 0.15

models:
  logreg:
    C: [0.01, 0.1, 1.0, 10.0]
  hgb:
    learning_rate: [0.05, 0.1]
    max_depth: [2, 3]
    min_samples_leaf: [20, 50]
    max_iter: [100, 300]

threshold:
  target_sensitivity: 0.80

evaluation:
  bootstrap_resamples: 1000
  calibration_bins: 10

serving:
  model_version: "1.0.0"

monitoring:
  window_size: 200             # most recent requests considered
  max_partial_rate_increase: 0.15   # absolute increase over the training baseline
  max_insufficient_rate: 0.05
```

Bounds are starting values. F2 checks them against the real distribution and the final values are recorded in `docs/decisions/`.

## 5. Coding standards

- Type hints on every function signature. Use built-in generics (`list[str]`, `dict[str, float]`).
- Google-style docstrings on every public function: one summary line, `Args`, `Returns`, `Raises` when relevant.
- Functions do one thing. As a guide, a function longer than 40 lines should be split unless splitting hurts readability.
- Names describe content: `vitals_df`, `record_ids`, `threshold`, never `df2`, `tmp`, `data`.
- Pure functions for transformations (DataFrame in, DataFrame out). File input and output happen only in `main()` functions and in `artifacts.py`.
- No global mutable state. The API loads the model once at startup into the FastAPI app state.
- Errors: raise specific built-in exceptions (`ValueError`, `FileNotFoundError`) with messages that name the offending value. Never catch an exception just to silence it.
- Logging through the standard `logging` module. Pipeline scripts log at INFO with counts at each step ("parsed 4000 files, 1 234 567 rows"). No `print` in library code.
- No commented-out code, no TODO without an owner and a roadmap reference.
- ruff config in `pyproject.toml`: line length 100, rules `E`, `F`, `I`, `B`, `UP`, `SIM`, `N`. `ruff format` for formatting.

## 6. Versioning

- **Code:** Semantic Versioning in `pyproject.toml`. Start at `0.1.0` after F0, bump the minor version after each feature (see roadmap), release `1.0.0` when all required tasks are done. The package exposes `icu.__version__` read from package metadata.
- **Model:** a separate semantic version, used as the folder name under `models/`. Bump the major version when the feature schema changes, the minor version when the model is retrained with the same schema, the patch version for metadata-only fixes. The API reads the version to serve from the `MODEL_VERSION` environment variable, defaulting to `serving.model_version` in the config.
- **Data:** identified by the dataset version and the SHA-256 checksums in `data/manifest.json`. The model metadata stores a single digest of the manifest (`training_data_sha256`).
- **Git tags:** `vX.Y.Z` on `main` after each approved feature.

## 7. Changelog

`CHANGELOG.md` follows the Keep a Changelog format with sections `Added`, `Changed`, `Fixed`, `Removed`. One entry per feature, written for a reviewer, with the feature ID.

```markdown
## [0.5.0] - 2026-10-01
### Added
- F4: feature computation shared by training and API (count, mean, last value and missing flag per vital).
```

## 8. Git conventions

- Branches: `feature/Fx-short-name`, merged by the human owner.
- Commits: Conventional Commits, imperative mood, scope when useful: `feat(features): compute last value per vital`, `test(split): check RecordID overlap`, `docs(api): document abstention rule`, `chore: bump version to 0.5.0`.
- Small commits that each leave the repo in a working state.

## 9. Architecture Decision Records

Short files in `docs/decisions/NNN-kebab-title.md`. Write one for every choice a reviewer could question. Template (`000-template.md`):

```markdown
# NNN. Title

Date: YYYY-MM-DD
Status: accepted

## Context
What forced a decision, with facts and numbers.

## Decision
What was chosen, in one or two sentences.

## Alternatives considered
- Option: why not.

## Consequences
What this makes easier, what it makes harder, what to watch.
```

Expected ADRs (the roadmap says when each is written): physiological bounds, handling of `-1`, tie-breaking for the last value, no class weights, threshold rule, served model choice, abstention rule in the API, model baked into the image, GCP as target cloud, public invoker for the demo only.

## 10. Makefile targets

| Target | Does |
|---|---|
| `setup` | `uv sync --frozen` |
| `data` | `ingest` then `parse` then `quality` then `tables` |
| `features` | `python -m icu.features` |
| `split` | `python -m icu.split` |
| `train` | `python -m icu.train` |
| `evaluate` | `python -m icu.evaluate` |
| `package` | `python -m icu.artifacts` (writes `models/<version>/`) |
| `reproduce` | `data features split train evaluate package`, then compares split files and metrics to the committed ones and prints differences |
| `lint` | `ruff check .` and `ruff format --check .` |
| `test` | `pytest -m "not data"` (fast, fixtures only) |
| `test-data` | `pytest -m data` (needs the real dataset) |
| `check` | `lint` then `test` |
| `api` | `uvicorn icu.api.app:app --reload` |
| `docker-build` | `docker build -t corvita-icu-api:$(VERSION) .` |
| `docker-run` | build then run on port 8080 with `logs/` mounted |
| `simulate` | `python scripts/send_requests.py` against the running API |
| `monitor` | `python -m icu.monitor` |
| `tf-validate` | `terraform -chdir=infra fmt -check -recursive`, `init -backend=false`, `validate` |
| `clean` | remove `data/interim`, `data/processed`, caches |

Each target has a one-line comment and `make help` lists them.
