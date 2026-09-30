# F8 handoff: Model packaging and one-command reproduction (0.9.0)

Date closed: 2026-09-30  
Status: accepted by human owner  
Package version: 0.9.0

## What was delivered

- `icu/artifacts.py`: `save_model`, `load_model`, metadata schema, reproduction baseline compare.
- Committed `models/1.0.0/pipeline.joblib`, `comparison/` HGB joblib, `metadata.json`.
- `make package`, `make reproduce` (full pipeline + split/metrics diff).
- `tests/test_artifacts.py`; artifacts section in `docs/modeling.md`.

## Verification (2026-09-30)

```
make check
```

- 43 fast tests passed (includes 4 artifact tests).

`metadata.json`: model version 1.0.0, served `logistic_regression`, manifest digest and split hashes recorded.

## Notes for F9

- API loads `models/1.0.0` via `load_model` and `MODEL_VERSION`.
- Threshold and feature columns are in metadata; responses must include traceability fields per API spec.

## Next feature

F9. Read `specs/05_API_SPEC.md`.
