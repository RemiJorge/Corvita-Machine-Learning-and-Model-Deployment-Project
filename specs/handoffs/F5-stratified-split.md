# F5 handoff: Stratified split (0.6.0)

Date closed: 2026-09-30  
Status: accepted by human owner  
Package version: 0.6.0

### What changed

- `src/icu/split.py`: `stratified_split`, `write_split_csv`, `main` from admission labels
- `tests/test_split.py`: overlap, determinism, death-rate balance (`@pytest.mark.data`)
- `splits/train_ids.csv`, `splits/val_ids.csv`, `splits/test_ids.csv`: committed ID lists
- `Makefile`: `make split` runs `python -m icu.split`
- `docs/modeling.md`: split procedure, rounding, grouping key
- `pyproject.toml`: version 0.6.0; `CHANGELOG.md`: F5 entry

### Commands run

```
make check
```

```
make lint
uv run ruff check .
All checks passed!
uv run ruff format --check .
34 files already formatted
uv run pytest -m "not data"
29 passed, 2 deselected in 3.89s
```

```
make split
make split
git diff splits/
```

```
uv run python -m icu.split
INFO train: n=2800 death_rate=0.1386
INFO val: n=600 death_rate=0.1383
INFO test: n=600 death_rate=0.1383
uv run python -m icu.split
INFO train: n=2800 death_rate=0.1386
INFO val: n=600 death_rate=0.1383
INFO test: n=600 death_rate=0.1383
```

(`git diff splits/` after the second run: no output.)

```
uv run pytest tests/test_split.py -v
tests/test_split.py::test_split_no_overlap_and_complete PASSED
tests/test_split.py::test_split_deterministic PASSED
tests/test_split.py::test_split_death_rates_close PASSED
3 passed in 0.50s
```

### Human verification steps

1. `make split` twice, `git diff splits/`: empty (expected: no diff after second run).
2. Log shows size and death rate of each group (expected: train n=2800, val/test n=600 each; death rates about 13.8 %).

### Decisions taken

- Holdout fractions derived from `config.yaml` `split.train/val/test` so the two sklearn calls match 70/15/15 without hard-coded 0.30 and 0.50 in code.

### Limitations and open questions

- None for F5.

## Next feature

F6. Read `specs/04_MODELING_SPEC.md` sections 3 to 5.
