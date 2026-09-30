# F12 handoff: Terraform for GCP (0.13.0)

Date closed: 2026-09-30  
Status: accepted by human owner  
Package version: 0.13.0 (release train continues to 1.0.0 in F13)

## What was delivered

- `infra/`: versions, providers, backend template, variables, `main.tf`, outputs, `.terraform.lock.hcl`.
- `infra/README.md` (init/validate outputs, costs, untested steps).
- `docs/infrastructure.md`; ADRs `010-gcp-target-cloud.md`, `011-public-invoker-demo.md`.
- `make tf-validate` wired in Makefile.

## Verification (2026-09-30)

```
make tf-validate
```

- fmt check, init `-backend=false`, validate: Success.

```
make check
```

- 59 fast tests passed.

## Notes for F13/F14

- No live `terraform apply` in take-home unless optional O1.
- CI `terraform` job should pass with committed `infra/`.

## Next feature

F13 (completed). F14: fresh-clone rehearsal.
