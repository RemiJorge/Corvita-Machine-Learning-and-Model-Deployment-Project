# F10 handoff: Request logging and monitoring check (0.11.0)

Date closed: 2026-09-30  
Status: accepted by human owner  
Package version: 0.11.0

## What was delivered

- `icu/api/request_log.py`: JSONL middleware (stdout + `REQUEST_LOG_PATH`), no patient values.
- `icu/monitor.py`: windowed rates, alerts, exit codes 0/1.
- `scripts/send_requests.py`; `make simulate`, `make monitor`.
- `docs/operations.md`; logging notes in `docs/api.md`.
- `tests/test_monitor.py`; `docker-run` sets `REQUEST_LOG_PATH`.

## Verification (2026-09-30)

```
make check
```

- 59 fast tests passed (includes monitor tests).

Human gate: simulate + monitor OK; outage simulation triggers alert; privacy check in operations doc.

## Notes for F11

- Docker CI job: build with committed `models/1.0.0/`, smoke `POST` with `examples/valid.json`.
- The `terraform` job needs a valid `infra/` tree (roadmap F12). If CI must be green on first push, do F12 on the same branch or immediately before merging F11.

## Next feature

F11. Read `specs/06_QUALITY_CI_MONITORING_SPEC.md` section 3.
