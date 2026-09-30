# F2 handoff: Parsing and data quality report (0.3.0)

Date closed: 2026-09-29  
Status: accepted by human owner  
Package version: 0.3.0

### What changed

- `src/icu/parse.py`: PhysioNet record parsing, outcomes read, integrity asserts, parquet output.
- `src/icu/quality.py`: `-1` and bounds cleaning, duplicate drop, quality report builder.
- `tests/fixtures/*.txt`: Synthetic records (sentinel, OOB, duplicate, post-24h).
- `tests/test_parse.py`, `tests/test_quality.py`: Spec section 10 tests for F2 (cutoff tests deferred to F3).
- `Makefile`: `data` runs ingest + parse + quality; `test-data` runs `pytest -m data`.
- `docs/decisions/002-physiological-bounds.md`, `003-handling-minus-one.md`: ADRs from real report.
- `docs/data.md`: Parsing, cleaning, report summary, spot-check command.
- `pyproject.toml`: version 0.3.0; `CHANGELOG.md`: F2 entry.

### Commands run

```
make check
```

```
make lint
...
All checks passed!
...
18 passed, 1 deselected in 2.59s

make test-data
...
1 passed, 18 deselected in 2.62s
```

```
make data
```

```
INFO Parsed 4000 record files, 1757980 measurement rows; death rate 0.1385 (554 / 4000)
INFO Wrote quality report reports/data_quality.json (4000 records, death rate 0.1385)
```

(ingest logs omitted; same as F1: files on disk, manifest refreshed.)

### Human verification steps

1. `make data`, then open `reports/data_quality.json`: record count 4000, death rate ~14 %, missing/OOB per vital (see `docs/data.md` table).
2. Pick one raw file, compare three lines with the Parquet table using the one-liner in `docs/data.md` (example record 132539).
3. Read `docs/decisions/002-physiological-bounds.md` and check bounds against percentiles in the report.

### Decisions taken

- Keep config physiological and Age bounds unchanged after F2 percentiles (ADR: `docs/decisions/002-physiological-bounds.md`).
- Treat all `-1` as missing (ADR: `docs/decisions/003-handling-minus-one.md`).
- Optional RespRate vs MechVent analysis (spec section 9) not implemented; report keeps placeholder note only.

### Limitations and open questions

- F3 placeholders in `data_quality.json` (`n_after_cutoff`, 24h fields) are zero until `icu.tables` lands.
- `measurements.parquet` is gitignored; reproduce with `make data` when raw files are present.
