# F3 handoff: 24 h cutoff, admission and vitals tables (0.4.0)

Date closed: 2026-09-29  
Status: accepted by human owner  
Package version: 0.4.0

## What was delivered

- `icu/tables.py`: `apply_cutoff`, admission and vitals parquet writers, quality report merge for 24 h fields.
- `tests/test_tables.py`: boundary tests at minutes 1440 and 1441, admission from 00:00 descriptors.
- `make data` runs ingest, parse, quality, tables.
- `docs/data.md`: processed tables, selection bias (spec section 8).

## Verification (2026-09-29)

```
make check
```

- ruff: all checks passed.
- pytest `-m "not data"`: 22 passed (including 4 table tests).

Human gate: `test_tables.py -v`, vitals `minute.max()` <= 1440.

## Notes for F4

- Inputs: `data/processed/admission.parquet` and `vitals.parquet` (already cut at 1440).
- `apply_cutoff` lives in `icu.tables`; F9 API should import it, not reimplement.
- Label column `in_hospital_death` is in admission only; features must not expose it.

## Next feature

F4. Read `specs/04_MODELING_SPEC.md` section 1.
