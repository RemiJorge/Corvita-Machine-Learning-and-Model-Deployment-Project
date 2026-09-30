# F14 handoff: Fresh-clone rehearsal and release (1.0.0)

Date closed: 2026-09-30  
Status: accepted by human owner  
Package version: 1.0.0

## What was validated

- README walkthrough and demo script (`docs/demo.md` / `specs/09_REVIEW_PREP.md`).
- `make reproduce` leaves committed `splits/` and `reports/` unchanged after demo-style rerun (F14 fixes in `[Unreleased]` changelog).
- `make check`, `make tf-validate`, Docker/API paths per README.

## Verification (2026-09-30)

```
make check
```

- 60 passed, 3 deselected (fast suite).

## Human follow-up (not agent)

- Push to remote and confirm CI green if not already.
- Create and push git tag `v1.0.0` on `main` when satisfied.
- Optional: O1 cloud deploy, O2 PSI, O3 ICUType metrics (roadmap optional table).

## Project status

All required features F0 to F14 closed. Specs are committed for traceability with `AGENTS.md`.
