# F4 handoff: Feature computation (0.5.0)

Date closed: 2026-09-30  
Status: accepted by human owner  
Package version: 0.5.0

## What was delivered

- `icu/features.py`: `compute_features`, `FEATURE_COLUMNS` (19 columns), `FORBIDDEN_COLUMNS`, `main()` writing `data/processed/features.parquet`.
- `tests/test_features.py`: fixture expectations, missing RespRate, tie-break, column order, no forbidden columns.
- `docs/decisions/004-tie-breaking-last-vital.md`, `docs/modeling.md` (section 1 design notes).
- `make features` runs `python -m icu.features`.

## Verification (2026-09-30)

```
make check
```

- ruff: all checks passed.
- pytest `-m "not data"`: 27 passed (5 feature tests).

Human gate: hand-check one RecordID against `features.parquet`; read `features.py` in one pass.

## Notes for F5

- Stratify on `in_hospital_death` from `admission.parquet` (4000 rows).
- Split IDs are committed under `splits/`; `make reproduce` in F8 will compare them.

## Next feature

F5. Read `specs/04_MODELING_SPEC.md` section 2.
