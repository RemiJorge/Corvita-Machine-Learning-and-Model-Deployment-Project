## Feature F4: Feature computation (version 0.5.0)

Status: ready for human verification

### What changed

- `src/icu/features.py`: `FEATURE_COLUMNS`, `FORBIDDEN_COLUMNS`, `compute_features`, `main()`.
- `tests/test_features.py`: five tests from modeling spec section 11 (F4).
- `docs/decisions/004-tie-breaking-last-vital.md`: last vital tie-break rule.
- `docs/modeling.md`: feature design notes for F4.
- `Makefile`: `features` target runs `python -m icu.features`.
- `pyproject.toml`: version 0.5.0.
- `CHANGELOG.md`: 0.5.0 release entry.

### Commands run

```
make check
```

```
make lint
uv run ruff check .
All checks passed!
uv run ruff format --check .
33 files already formatted
make test
uv run pytest -m "not data"
============================= test session starts ==============================
platform linux -- Python 3.14.4, pytest-9.1.1, pluggy-1.6.0
collected 28 items / 1 deselected / 27 selected
tests/test_config.py ...
tests/test_features.py .....
tests/test_ingest.py ........
tests/test_parse.py ....
tests/test_quality.py ...
tests/test_tables.py ....
======================= 27 passed, 1 deselected in 2.84s =======================
```

```
make features
uv run python -m icu.features
INFO Wrote data/processed/features.parquet (4000 rows)
```

### Human verification steps

1. Pick one RecordID, compute its HR mean and last value by hand from the raw file, compare with `features.parquet`.
2. Read `features.py` top to bottom and check that it is understandable in one read.

Expected: hand values match parquet for the chosen record; module is a single straight-line read without hidden helpers beyond admission and vital aggregation.

### Decisions taken

- Last vital at equal minute: highest `row_order` (ADR: `docs/decisions/004-tie-breaking-last-vital.md`).

### Limitations and open questions

- `features.parquet` includes `record_id` for joins; `compute_features` returns only `FEATURE_COLUMNS` for API use.
- F5 split not started.
