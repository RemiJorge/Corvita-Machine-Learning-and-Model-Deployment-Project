# Model card: ICU in-hospital mortality, first 24 hours

- Model version: 1.0.0 (packaged in F8)
- Served model: logistic regression, `C=0.01`
- Trained on: PhysioNet Challenge 2012 set A, manifest digest `a2ce977bd52333720499d08063d076a83bab822acad39272dd1d733371ec6046`, training split 2800 records
- Code: git `1f32e78`, package 0.8.0

## Intended use

Demonstration of an end-to-end ML workflow for a hiring exercise. Not validated for clinical use.
Not applicable to newborns.

## Inputs

Admission fields (age, gender, ICU type) and vitals HR, RespRate, and Temp aggregated over the first 1440 minutes after ICU admission. Features are listed in `icu.features.FEATURE_COLUMNS` (19 columns). Outcome scores and post-24 h measurements are never inputs.

## Outcome

In-hospital death during the stay.

## Performance on the test set (600 records, 83 deaths)

Bootstrap: 1000 resamples, 95 % percentile intervals. Baselines: PR-AUC and precision use test prevalence (0.138); AUROC baseline 0.5; Brier baseline uses a constant prediction at the training death rate (0.139).

| Model | PR-AUC [CI] | AUROC [CI] | Brier [CI] |
|---|---|---|---|
| logistic_regression (served) | 0.303 [0.225, 0.399] | 0.741 [0.684, 0.792] | 0.110 [0.090, 0.129] |
| hist_gradient_boosting | 0.350 [0.267, 0.457] | 0.776 [0.724, 0.827] | 0.105 [0.090, 0.123] |

Operating threshold **0.131** for the served model (chosen on validation for sensitivity at least 0.80): test sensitivity 0.78 (CI 0.687 to 0.859), specificity 0.58 (CI 0.538 to 0.620), precision 0.23 (CI 0.181 to 0.276), **47** alerts per 100 patients (CI 43 to 51).

With only about 600 test records and 83 deaths, intervals are wide. Paired bootstrap on the test set: PR-AUC difference (HGB minus logreg) interval contains 0, so the holdout does not clearly rank the two models on PR-AUC despite the validation gap.

## Calibration

See `reports/figures/calibration.png`. On the test set, HGB has a slightly lower Brier score (0.105 versus 0.110 for logistic regression), so its probability scale is marginally closer to observed frequencies in this split. Logistic regression is still served because validation PR-AUC favored it (see `docs/decisions/007-served-model-choice.md`). A clinician should treat outputs as risk estimates, not diagnoses. Isotonic or Platt recalibration would need data outside tuning and test; that is out of scope here.

## Behaviour with missing vitals

Natural subgroups on the test set are in `reports/missing_vitals.json`. About 421 of 600 test records miss at least one vital in the window; metrics remain computable there but specificity drops versus the full test set.

Ablation (drop vital measurements for all test records, recompute features): removing **RespRate** lowers served-model PR-AUC by about 0.016 and AUROC by about 0.053 versus the full test set, so the model relies on respiratory rate and monitoring gaps matter. Removing HR or Temp alone changes PR-AUC by less than about 0.02 on this split. Dropping all three vitals cuts PR-AUC sharply (see ablation `all_three` in the report).

Abstention when inputs are insufficient is defined in the API spec (F9); not implemented until then.

## Limitations

- Adult ICU cohort (2012 challenge); not transferable to neonates or to NOA without retraining.
- Single geographic era and sensor mix; drift is expected in production.
- No external validation set beyond this project holdout.
- Class imbalance handled by thresholding, not class weights.
- Split is by record ID, not patient (dataset has no patient linkage).

## Ethical and safety notes

Probabilities are estimates for a population unlike the one where they would be used. A clinician decides; the model can abstain once the API exists; request logs must not store raw patient values.
