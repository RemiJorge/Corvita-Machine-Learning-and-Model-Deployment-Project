# 007. Served model from validation performance

Date: 2026-09-30
Status: accepted

## Context

Two models were tuned on the training split and compared on validation (F6): logistic regression with `C=0.01` and hist gradient boosting with `learning_rate=0.05`, `max_depth=2`, `min_samples_leaf=50`, `max_iter=100`. The deployment candidate must be chosen before the one-time test evaluation, using validation metrics only, so the holdout does not influence the decision.

Validation ranking metrics from `reports/selection.json`:

| Model | val PR-AUC | val AUROC | val Brier |
|---|---|---|---|
| logistic_regression | 0.381 | 0.772 | 0.107 |
| hist_gradient_boosting | 0.371 | 0.769 | 0.105 |

The PR-AUC gap is 0.010 (above the 0.01 tie band in the modeling spec).

## Decision

Serve **logistic regression** (`C=0.01`) because it has the higher validation PR-AUC. The decision threshold remains the validation value 0.131 (sensitivity at least 0.80 on validation). HGB is kept as a comparison model in reports and future packaging (F8), not as the served pipeline.

## Alternatives considered

- Serve HGB because test PR-AUC and Brier are slightly better after scoring: rejected; test metrics must not drive the choice.
- Serve HGB when validation PR-AUC differs by less than 0.01: not applicable here (gap equals 0.010, logreg still wins on the primary rule).
- Refit on train plus validation before serving: rejected in F6; would break consistency with the frozen validation threshold.

## Consequences

Test-set scores (reported once in F7, not used for the decision): logistic regression PR-AUC 0.303 (95 % bootstrap CI 0.225 to 0.399) versus HGB 0.350 (CI 0.267 to 0.457). Paired bootstrap on the test set cannot separate the models on PR-AUC (HGB minus logreg interval contains 0). The served model is smaller, faster, and has readable coefficients for review. Recalibration remains future work; see the model card calibration section.
