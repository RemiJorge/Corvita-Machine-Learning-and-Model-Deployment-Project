## Feature F9: Prediction API and Docker image (version 0.10.0)

Status: ready for human verification

### What changed

- `src/icu/api/schemas.py`: Pydantic request and response models.
- `src/icu/api/service.py`: Cutoff, bounds, features, abstention, warnings.
- `src/icu/api/app.py`: FastAPI app, lifespan model load, `/health`, `/predict`.
- `src/icu/artifacts.py`: Optional `models_dir` on `load_model` for `MODELS_DIR`.
- `Dockerfile`, `.dockerignore`, `Makefile` (`api`, `docker-build`, `docker-run`).
- `examples/*.json`, `docs/api.md`, `tests/conftest.py`, `tests/test_api.py`.
- `docs/decisions/008-api-abstention.md`, `docs/decisions/009-model-baked-in-image.md`.
- `pyproject.toml` 0.10.0, `CHANGELOG.md`.

### Commands run

```
make check
```

```
make lint
...
================= 53 passed, 3 deselected, 1 warning in 3.60s ==================
```

```
make docker-build
```

```
Successfully tagged corvita-icu-api:0.10.0
IMAGE                    DISK USAGE   CONTENT SIZE
corvita-icu-api:0.10.0   735MB        171MB
```

```
docker run -d --rm -p 8081:8080 --name f9-api-test corvita-icu-api:0.10.0
sleep 4 && curl -s localhost:8081/health
```

```
{"status":"ok","model_version":"1.0.0"}
```

(Port 8080 was in use locally; container verified on 8081 after lazy `matplotlib` import fix in `evaluate.write_figures`.)

### Human verification steps

1. `make docker-run`, then the three `curl` commands from `docs/api.md`; compare with the documented responses.
2. `curl localhost:8080/health`: model version shown.
3. `docker image ls`: note the image size for the README.

### Decisions taken

- Request JSON logging deferred to F10 per roadmap (ADR 008/009 for abstention and baked model).
- `insufficient` only when no vital rows exist in the 24 h window; all-invalid vitals yield `partial` (API spec section 5 note).

### Limitations and open questions

- `test_logs_contain_no_patient_values` and middleware logging: F10.
- `make simulate` still stubbed until F10.
- Docker image content size about 171 MB; document in README during F13.
