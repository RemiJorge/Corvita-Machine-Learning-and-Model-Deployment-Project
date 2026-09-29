# 006. Validation threshold from target sensitivity

Date: 2026-09-30
Status: accepted

## Context

The model outputs a probability of in-hospital death from the first 24 hours. Clinicians need early warning: missing a patient who will die is costlier than a false alert, but each alert uses attention. The config sets `threshold.target_sensitivity` (default 0.80). The test set must not influence this choice (F7 scores test once at the frozen threshold).

## Decision

On validation probabilities, use `sklearn.metrics.roc_curve` and take the **highest** threshold whose sensitivity (true positive rate) is at least the target. That threshold maximizes specificity among rules that meet the sensitivity floor. Report validation specificity, precision, and alerts per 100 patients at that threshold. Compute the Youden index threshold on validation for comparison only; it does not drive deployment.

## Alternatives considered

- Youden-optimal threshold (maximize sensitivity + specificity - 1): rejected as the primary rule; it does not fix a clinical sensitivity floor.
- Tuning threshold on the test set: rejected; leaks the holdout and breaks one-shot test evaluation.
- Refitting on train plus validation before thresholding: rejected; would mismatch the model fit with the validation scores used to pick hyperparameters (see `docs/modeling.md`).

## Consequences

Test sensitivity may fall below 0.80 even when validation met the target; bootstrap intervals in F7 quantify that. Alert load is visible via alerts per 100 patients next to sensitivity. Changing the clinical target is a config change, not a code change.
