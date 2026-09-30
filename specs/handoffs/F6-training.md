# F6 handoff: Training, validation selection, threshold (0.7.0)

Date closed: 2026-09-30  
Status: accepted by human owner  
Package version: 0.7.0

## What was delivered

- `icu/train.py`: logreg and HGB pipelines, full validation grids, sensitivity-based thresholds.
- `reports/tuning.csv` (20 candidates), `reports/selection.json`.
- `tests/test_train.py` (train-only fit, threshold rule, no test IDs in training module, tie-breaks).
- ADRs `005-no-class-weights.md`, `006-threshold-rule.md`; training notes in `docs/modeling.md`.
- `make train` runs `python -m icu.train`.

## Verification (2026-09-30)

```
make check
```

- 34 fast tests passed (5 train tests).
- `grep test_ids src/icu/train.py`: no matches.

Selected on validation (see `selection.json`): logistic regression `C=0.01` (val PR-AUC 0.381); HGB best `learning_rate=0.05`, `max_depth=2`, `min_samples_leaf=50`, `max_iter=100` (val PR-AUC 0.371). Both thresholds meet target sensitivity 0.80 on validation.

## Notes for F7

- Score test set once using frozen pipelines and validation thresholds.
- Served model rule: modeling spec section 8 (validation PR-AUC; prefer logreg if within 0.01).
- Do not write `models/` until F8.

## Next feature

F7. Read `specs/04_MODELING_SPEC.md` sections 6 to 8.
