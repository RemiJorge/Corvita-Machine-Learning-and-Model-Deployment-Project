# F11 handoff: CI workflow (0.12.0)

Date closed: 2026-09-30  
Status: accepted by human owner  
Package version: 0.12.0

## What was delivered

- `.github/workflows/ci.yml`: jobs `python` (uv, ruff, pytest `-m "not data"`), `docker` (build, health, POST `examples/valid.json`), `terraform` (fmt, init `-backend=false`, validate).

## Verification (2026-09-30)

```
make check
```

- 59 fast tests passed locally.

Human gate: green GitHub Actions on push; README CI badge when repo URL is known.

## Notes for F12

- `make tf-validate` still stubbed until F12; CI `terraform` job fails until `infra/` is committed.
- Region `northamerica-northeast1`, least privilege, remote state described in infra spec (not applied in take-home).

## Next feature

F12. Read `specs/07_INFRA_SPEC.md`.
