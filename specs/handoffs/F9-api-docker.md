# F9 handoff: Prediction API and Docker image (0.10.0)

Date closed: 2026-09-30  
Status: accepted by human owner  
Package version: 0.10.0

## What was delivered

- `icu/api/`: `app.py`, `schemas.py`, `service.py` (`/predict`, `/health`).
- Shared pipeline: `apply_cutoff`, quality bounds, `compute_features`, `load_model` with `MODEL_VERSION` / `MODELS_DIR`.
- `Dockerfile` (multi-stage, non-root, healthcheck), four `examples/*.json`, `docs/api.md`.
- `tests/test_api.py` (validation, partial, abstention, cutoff, offline parity with `data` marker).
- ADRs `008-api-abstention.md`, `009-model-baked-in-image.md`.
- `make api`, `make docker-build`, `make docker-run`.

## Verification (2026-09-30)

```
make check
```

- 53 fast tests passed (API tests included).

Request logging middleware, `make simulate`, and `make monitor` deferred to F10 per roadmap.

## Notes for F10

- Implement API spec section 7 (JSONL, no PHI).
- `docker-run` already mounts `logs/`; set `REQUEST_LOG_PATH` in container for local monitor demos.
- `test_logs_contain_no_patient_values` may need updating once logging lands.

## Next feature

F10. Read `specs/05_API_SPEC.md` section 7 and `specs/06_QUALITY_CI_MONITORING_SPEC.md` sections 4 to 6.
