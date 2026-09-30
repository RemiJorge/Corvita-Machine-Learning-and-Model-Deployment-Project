## Feature F15: Consistency fixes (version 1.0.1)

Status: ready for human verification

### What changed
- `src/icu/api/service.py`: non-numeric `record_id`; abstention warning; plural out-of-range warnings
- `tests/test_api.py`, `tests/test_doc_identifiers.py`: new coverage
- `docs/decisions/001-reject-unknown-parameters.md`, `008-api-abstention.md`, `docs/api.md`
- `models/1.0.0/`, README, `docs/model_card.md`: identifiers under Python 3.12 package
- `.python-version`, `pyproject.toml`, `uv.lock`: Python 3.12 pin
- `Makefile`: `docker-run` host user
- `reports/data_quality.json`, `src/icu/quality.py`: removed spec placeholder key
- `.gitignore`, `specs/`, `AGENTS.md`: committed (CLAUDE.md stays ignored)
- `LICENSE`, README citation, typography across docs and `evaluate.py`
- `CHANGELOG.md`, version 1.0.1

### Commands run
See handoff report in the agent session (make check, reproduce, human verification).

### Human verification steps
Per `specs/10_FIXES_AND_OPTIONALS.md` section F15 human verification.

### Decisions taken
- Point 11: commit `specs/` and `AGENTS.md`; keep `CLAUDE.md` in `.gitignore` (not committed).
- `make reproduce` on Python 3.12: max metric absolute difference 0 (identical to baseline).

### Limitations and open questions
- Port 8080 was occupied by an existing `corvita-icu-api-demo` container during HV2; verification used uvicorn on 18080 and docker on 18081.
