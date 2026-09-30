# F1 handoff: Download, checksums, manifest (0.2.0)

Date closed: 2026-09-29  
Status: accepted by human owner  
Package version: 0.2.0

## What was delivered

- `icu/ingest.py`: download or verify on disk, optional tar extract, `data/manifest.json`.
- `tests/test_ingest.py` (8 tests, no network).
- `docs/data.md` (source, license, manual raw files, manifest).
- `make data` runs ingest only.
- Committed `data/manifest.json` (4000 record files, ODC-By 1.0 license).

## Verification (2026-09-29)

```
make check
```

- ruff: all checks passed.
- pytest `-m "not data"`: 11 passed (3 config + 8 ingest).

Human gate: manifest checksums, idempotent `make data`, raw files under `data/raw/`.

## Notes for F2

- `published_checksums` is null in the manifest; ingest documents that PhysioNet published sums were not available or not used.
- Real data is present locally; F2 parsing assertions should use the full set A (4000 files) when running `make data` on the human machine.

## Next feature

F2. Read `specs/03_DATA_SPEC.md` sections 3 to 6.
