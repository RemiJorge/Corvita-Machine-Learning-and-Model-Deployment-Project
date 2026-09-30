# 005. No class weights in mortality models

Date: 2026-09-30
Status: accepted

## Context

About 14 % of ICU stays in set A die in hospital. Classifiers can use `class_weight` to up-weight the minority class. The brief asks for probabilistic scores (Brier score, calibration) and a decision threshold chosen on validation for sensitivity. Reweighting shifts predicted probabilities away from the true event rate and can worsen Brier and calibration even when ranking metrics improve.

## Decision

Neither logistic regression nor `HistGradientBoostingClassifier` uses `class_weight`. Imbalance is handled by picking the probability threshold on validation, not by changing the fitted likelihood.

## Alternatives considered

- `class_weight="balanced"`: rejected; distorts probability scale and complicates comparison to prevalence baselines.
- Resampling the training set: rejected; same probability distortion and extra pipeline complexity.

## Consequences

Sensitivity at a fixed alert rate may be lower without reweighting, but thresholds are explicit and tied to `threshold.target_sensitivity` in config. Test evaluation (F7) reports metrics at the validation threshold without refitting on train plus validation.
