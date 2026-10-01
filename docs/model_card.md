# Model card: ICU in-hospital mortality, first 24 hours

- Model version: 1.0.1 (served; same `pipeline.joblib` as 1.0.0 with PSI reference metadata)
- Served model: logistic regression, `C=0.01`
- Trained on: PhysioNet Challenge 2012 set A, manifest SHA-256 `3d13119ba577e31b155e066f68ada7dfafd09bfd0a8aaf147c9ca56970a17062` (hash of `data/manifest.json` at package time), training split 2800 records
- Code: git `f729e02f85f6e0114ce809f4aeb94cca5d09e73f` (from `models/1.0.1/metadata.json`), package 1.4.0

## Intended use

Demonstration of an end-to-end ML workflow for a hiring exercise. Not validated for clinical use.
Not applicable to newborns.

## Inputs

Admission fields (age, gender, ICU type) and vitals HR, RespRate, and Temp aggregated over the first 1440 minutes after ICU admission. Features are listed in `icu.features.FEATURE_COLUMNS` (19 columns). Outcome scores and post-24 h measurements are never inputs.

## Outcome

In-hospital death during the stay.

## Performance on the test set (600 records, 83 deaths)

Bootstrap: 1000 resamples, 95 % percentile intervals. Baselines: PR-AUC and precision use test prevalence (0.138); AUROC baseline 0.5; Brier of a constant prediction equal to the training death rate (0.139): 0.119.

| Model | PR-AUC [CI] | AUROC [CI] | Brier [CI] |
|---|---|---|---|
| logistic_regression (served) | 0.303 [0.225, 0.399] | 0.741 [0.684, 0.792] | 0.110 [0.090, 0.129] |
| hist_gradient_boosting | 0.350 [0.267, 0.457] | 0.776 [0.724, 0.827] | 0.105 [0.090, 0.123] |

Operating threshold **0.131** for the served model (chosen on validation for sensitivity at least 0.80): test sensitivity 0.78 (CI 0.687 to 0.859), specificity 0.58 (CI 0.538 to 0.620), precision 0.23 (CI 0.181 to 0.276), **47** alerts per 100 patients (CI 43 to 51). That alert load is heavy for clinical use; `threshold.target_sensitivity` in `config/config.yaml` is the lever to discuss with clinicians when trading sensitivity against flags.

With only about 600 test records and 83 deaths, intervals are wide. Paired bootstrap on the test set: PR-AUC difference (HGB minus logreg) interval contains 0, so the holdout does not clearly rank the two models on PR-AUC despite the validation gap.

## Calibration

See `reports/figures/calibration.png`. On the test set, HGB has a slightly lower Brier score (0.105 versus 0.110 for logistic regression). Logistic regression is still served because validation PR-AUC favored it (0.381 versus 0.371); size, speed, and readable coefficients are secondary reasons. The paired bootstrap PR-AUC difference on the test set has an interval that contains zero. A clinician should treat outputs as risk estimates, not diagnoses. Isotonic or Platt recalibration would need data outside tuning and test; that is out of scope here.

## Behaviour with missing vitals

On the test set, records missing at least one vital have an observed death rate of 70/421 (16.6 %) versus 13/179 (7.3 %) for records with all three vitals present. RespRate is the main gap: about 73 % of training records have no RespRate measurement in the first 24 hours (`reports/data_quality.json`, `records_without_any_value_in_24h` for RespRate). On the full set A cohort, every record with `MechVent = 1` in the first 24 h lacks a RespRate value in the same window (2405/2405); RespRate is never recorded alongside active ventilation in this extract, which supports the missing-data flags as clinical signal rather than random dropout.

Natural subgroups on the test set are in `reports/missing_vitals.json`. About 421 of 600 test records miss at least one vital in the window; metrics remain computable there but specificity drops versus the full test set.

### Performance by ICUType (test set)

Full numbers and bootstrap intervals: `reports/subgroups.json`. Group sizes sum to 600.

| ICUType | n | deaths | observed death rate | mean predicted (logreg) | mean predicted (HGB) |
|---|---:|---:|---:|---:|---:|
| 1 | 92 | 15 | 16.3 % | 13.1 % | 14.6 % |
| 2 | 114 | 7 | 6.1 % | 10.0 % | 6.2 % |
| 3 | 238 | 38 | 16.0 % | 17.5 % | 19.0 % |
| 4 | 156 | 23 | 14.7 % | 12.6 % | 13.2 % |

ICUType 2 has only 7 deaths on the test split, so subgroup metrics are reported as `too few events` (fewer than 10 deaths or 10 survivors); the table still compares observed rate to mean predicted probability. ICUTypes 1, 3, and 4 show mixed calibration: type 3 mean predictions run slightly above the observed rate, while types 1 and 4 run slightly below, with wide bootstrap intervals at this sample size. On NOA, the same observed-versus-predicted breakdown would be run per deploying hospital, incubator firmware version, and gestational age band before trusting scores outside the training mix.

Ablation (drop vital measurements for all test records, recompute features): removing **RespRate** lowers served-model PR-AUC by about 0.016 and AUROC by about 0.053 versus the full test set, so the model relies on respiratory rate and monitoring gaps matter. Removing HR or Temp alone changes PR-AUC by less than about 0.02 on this split. Dropping all three vitals cuts PR-AUC sharply (see ablation `all_three` in the report).

The API abstains when no vital has a valid value in the window (`data_quality.status` `insufficient`). See `docs/decisions/008-api-abstention.md`.

## Limitations

- 48 h inclusion rule in set A: early deaths and short stays are missing; see [data.md](data.md#selection-bias).
- Single hospital system, adult data, 2012 era; three vitals only.
- Test set 600 records, 83 deaths: wide bootstrap intervals.
- No external validation; calibration may not transfer.
- Class imbalance handled by thresholding, not class weights (ADR 005).
- Split is by record ID, not patient (dataset has no patient linkage).
- PSI drift monitoring is weak on `resp_rate_count` because most values sit in one bin (many zero counts). `icu.psi` imports training constants from `icu.train`; a production codebase would move shared feature lists to `icu.features` or config.

## Ethical and safety notes

Probabilities are estimates for a population unlike the one where they would be used. A clinician decides; the model abstains when vitals are insufficient; request logs omit patient identifiers and measurement values (`docs/operations.md`).
