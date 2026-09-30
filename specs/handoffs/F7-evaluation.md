# F7 handoff: Test evaluation and missing-vitals analysis (0.8.0)

Date closed: 2026-09-30  
Status: accepted by human owner  
Package version: 0.8.0

## What was delivered

- `icu/evaluate.py`: one-time test scoring, bootstrap CIs, paired bootstrap, calibration plots.
- `reports/metrics.json`, `reports/missing_vitals.json`, `reports/figures/{roc,pr,calibration}.png`.
- `tests/test_evaluate.py`; ADR `007-served-model-choice.md`; `docs/model_card.md` started.
- `make evaluate` runs `python -m icu.evaluate`.

## Verification (2026-09-30)

```
make check
```

- 43 fast tests passed (includes 5 evaluate tests).

Served model: `logistic_regression` (validation rule). Test n=600, 83 deaths. Paired bootstrap PR-AUC difference CI includes zero.

## Notes for F8

- Package the fitted pipelines from training artifacts, not a re-tune on test.

## Next feature

F8 (completed). F9 API uses the same feature and cutoff path as training.
