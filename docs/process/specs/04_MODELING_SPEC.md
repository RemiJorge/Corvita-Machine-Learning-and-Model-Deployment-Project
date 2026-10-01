# 04. Modeling specification

## 1. Features (F4)

Implemented in `icu.features` (`compute_features`, `FEATURE_COLUMNS`). Training and the API must import this module in F6 and F9.

`icu/features.py` exposes one entry point used by both training and the API:

```python
def compute_features(admission_df: pd.DataFrame, vitals_df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per record_id with the columns of FEATURE_COLUMNS, in order."""
```

Inputs are already cleaned and cut at 1440 minutes (see data spec). The function never reads files and never sees the label.

### Feature list

Order is fixed by `FEATURE_COLUMNS`. 19 columns.

| Column | Type | Definition |
|---|---|---|
| `age` | float | Age in years, NaN if missing |
| `gender_male` | float | 1.0 male, 0.0 female, NaN if missing |
| `gender_missing` | int | 1 if gender is missing, else 0 |
| `icu_type_1` to `icu_type_4` | int | One-hot of ICUType; all four are 0 if ICUType is missing |
| `hr_count` | int | Number of HR measurements kept in the window |
| `hr_mean` | float | Mean of those measurements, NaN if count is 0 |
| `hr_last` | float | Value of the latest measurement (highest minute, then highest `row_order`), NaN if count is 0 |
| `hr_missing` | int | 1 if count is 0, else 0 |
| `resp_rate_count`, `resp_rate_mean`, `resp_rate_last`, `resp_rate_missing` | | Same rules for RespRate |
| `temp_count`, `temp_mean`, `temp_last`, `temp_missing` | | Same rules for Temp |

Design notes to keep in `docs/modeling.md`:

- One-hot encoding of `ICUType` is done here, not in the scikit-learn pipeline, because the four categories are fixed by the dataset definition. Nothing is learned from data, so it cannot leak, and training and serving share it by construction.
- The missing flags look redundant with `count == 0`, but they are required by the brief and make the logistic regression coefficients easy to read.
- Records with no vital at all still get a row (counts 0, flags 1).

Constants in the same module:

```python
FEATURE_COLUMNS: list[str] = [...]
FORBIDDEN_COLUMNS: frozenset[str] = frozenset(
    {"SAPS-I", "SOFA", "Length_of_stay", "Survival", "In-hospital_death", "in_hospital_death"}
)
```

`compute_features` ends with an assertion that no forbidden column is present and that columns equal `FEATURE_COLUMNS`.

## 2. Split (F5)

Implemented in `icu.split`; committed `splits/train_ids.csv`, `val_ids.csv`, `test_ids.csv`.

1. Load `admission.parquet` (record IDs and labels only).
2. `train_test_split(ids, test_size=0.30, stratify=labels, random_state=seed)` gives train (70 %) and a holdout.
3. Split the holdout with `test_size=0.50, stratify=holdout_labels, random_state=seed` into validation and test (15 % each).
4. Sort each ID list ascending and write one column `record_id` to `splits/{train,val,test}_ids.csv`.
5. Log size and death rate of each group.

The grouping key is `RecordID`. In this dataset each record is a separate ICU stay and no patient identifier links stays, so patient-level grouping is not possible. State this in `docs/modeling.md` and note that in NOA the grouping key would be the infant, as discussed in the first technical exercise.

## 3. Pipelines (F6)

Implemented in `icu.train` (`reports/tuning.csv`, `reports/selection.json`). Test metrics stay in F7.

Both models are scikit-learn `Pipeline` objects fitted on the training rows only.

### Logistic regression

```
ColumnTransformer(
  continuous  [age, gender_male, *_mean, *_last]: SimpleImputer(strategy="median") -> StandardScaler()
  counts      [*_count]:                          StandardScaler()
  binary      [gender_missing, icu_type_*, *_missing]: "passthrough"
)
-> LogisticRegression(C=<grid>, max_iter=2000)
```

### Tree-based model

```
HistGradientBoostingClassifier(
  learning_rate=<grid>, max_depth=<grid>, min_samples_leaf=<grid>, max_iter=<grid>,
  early_stopping=False, random_state=seed
)
```

No imputation: the model routes missing values natively. `early_stopping=False` is set explicitly so that the model never carves its own internal validation split from the training data, which keeps tuning on our validation set only and keeps runs deterministic.

### No class weights

Neither model uses `class_weight`. Reweighting classes shifts predicted probabilities away from real frequencies and worsens the Brier score. The class imbalance (about 14 % deaths) is handled by choosing the decision threshold. Write this in an ADR.

## 4. Tuning on validation (F6)

- Grids come from `config.yaml` (`models.logreg`, `models.hgb`). Iterate with `sklearn.model_selection.ParameterGrid`.
- For each candidate: fit on train, predict probabilities on validation, compute validation PR-AUC (`average_precision_score`), AUROC, Brier.
- Append one row per candidate to `reports/tuning.csv`: `model`, the parameters, `val_pr_auc`, `val_auroc`, `val_brier`, `fit_seconds`.
- Selection rule per model: highest validation PR-AUC; if two candidates are within 0.005, take the lower validation Brier; if still tied, the simpler one (smaller `C` for logistic regression, fewer iterations and smaller depth for HGB).
- Models are not refitted on train plus validation. The brief asks for preparation learned on train only, and refitting would make the threshold chosen on validation inconsistent with the final model. Write this in `docs/modeling.md`.

## 5. Threshold (F6)

- Computed on validation for each selected model.
- Rule: the highest threshold whose validation sensitivity is at least `threshold.target_sensitivity` (0.80). The highest such threshold gives the best specificity at that sensitivity. Use `roc_curve` on validation probabilities.
- Save for each model: threshold, validation sensitivity, validation specificity, validation precision, alerts per 100 patients (share predicted positive times 100).
- Justification for the ADR and model card: in an early-warning setting, missing a patient who will die costs more than a false alert, so sensitivity is fixed first; but every alert consumes clinician attention, so the alert load is reported next to it and the target is a config value that clinicians would set, not the engineer. The Youden-optimal threshold is also reported for comparison only.

`reports/selection.json` holds, per model, the selected parameters, validation metrics, threshold data, and the list of rows considered.

## 6. Test evaluation (F7)

Implemented in `icu.evaluate` (`reports/metrics.json`, `reports/missing_vitals.json`, figures). Served model ADR 007.

`evaluate.py` loads the frozen selection, predicts on the test set once per model, and computes:

| Metric | Function | Baseline reported next to it |
|---|---|---|
| PR-AUC | `average_precision_score` | Test prevalence (score of a random ranking) |
| AUROC | `roc_auc_score` | 0.5 |
| Sensitivity | recall of class 1 at the validation threshold | none |
| Specificity | recall of class 0 at the validation threshold | none |
| Precision (PPV) | at the validation threshold | test prevalence |
| Brier score | `brier_score_loss` | Brier of a constant prediction equal to the training death rate |
| Alerts per 100 patients | share predicted positive x 100 | none |

Also report the confusion matrix counts.

### Confidence intervals

- 1000 bootstrap resamples of the test rows with replacement, seed from config. Skip resamples that contain a single class and report how many were skipped.
- 95 % percentile intervals for every metric above.
- Paired bootstrap: the same resamples for both models give an interval for the difference in PR-AUC and AUROC (HGB minus logistic regression). If the interval contains 0, write that the test set cannot separate the two models.
- Explain in the model card that the test set holds about 600 records and about 80 deaths, which makes intervals wide.

### Calibration

- `calibration_curve(y, p, n_bins=10, strategy="quantile")` for both models, one figure with the diagonal.
- Comment in the model card: which model is better calibrated, and what that means for a clinician reading a probability. Recalibration (isotonic or Platt) is future work, because doing it properly needs data that is used neither for tuning nor for testing.

### Figures

`reports/figures/roc.png`, `pr.png`, `calibration.png`, each with both models, axis labels, the baseline line, and the test-set size in the title. Plain matplotlib, readable in black and white.

## 7. Missing-vitals analysis (F7)

Two complementary views, for both models, in `reports/missing_vitals.json` and summarized in the model card.

1. **Natural subgroups on the test set:** all records; records missing at least one vital; missing HR; missing RespRate; missing Temp; missing all three. For each: `n`, `n_deaths`, and the metrics when the subgroup has at least 10 deaths and 10 survivors, otherwise the string `"too few events"`.
2. **Ablation:** for each vital, and then for all three together, delete that vital's measurements for every test record, recompute features with `compute_features`, predict, and report the metrics and the change versus the full test set. This shows how much the model depends on each signal and what a sensor outage would do.

Interpretation to write: a large drop when RespRate is removed means the model relies on it and a monitoring alert on its absence matters; a small drop means the model degrades gracefully.

## 8. Choice of the served model (F7)

Chosen on validation results only, by this rule: higher validation PR-AUC; if the difference is below 0.01, prefer logistic regression for its better expected calibration, smaller size, faster inference and readable coefficients. The ADR cites validation numbers. Test numbers appear in the ADR only as a reported consequence, never as the reason.

## 9. Artifacts (F8)

Implemented in `icu.artifacts` (`make package`, `make reproduce`). Committed `models/1.0.0/`.

```
models/1.0.0/
├── pipeline.joblib          # served model (full scikit-learn pipeline)
├── comparison/
│   └── <other_model>.joblib # the non-served model, kept for reproducibility
└── metadata.json
```

`metadata.json`:

```json
{
  "model_version": "1.0.0",
  "served_model": "logistic_regression",
  "created_at": "2026-10-02T15:40:00Z",
  "code_version": "0.9.0",
  "git_commit": "abc1234",
  "git_dirty": false,
  "dataset_version": "1.0.0",
  "training_data_sha256": "<sha256 of data/manifest.json>",
  "split_files_sha256": {"train": "...", "val": "...", "test": "..."},
  "seed": 42,
  "cutoff_minutes": 1440,
  "physiological_bounds": {"HR": [20, 300], "RespRate": [1, 80], "Temp": [25.0, 45.0]},
  "feature_columns": ["age", "..."],
  "hyperparameters": {"C": 0.1},
  "threshold": 0.12,
  "target_sensitivity": 0.8,
  "validation_metrics": {},
  "test_metrics": {},
  "training_reference": {
    "missing_rate": {"HR": 0.0, "RespRate": 0.0, "Temp": 0.0},
    "partial_rate": 0.0,
    "insufficient_rate": 0.0,
    "feature_quantiles": {"hr_mean": {"p5": 0, "p25": 0, "p50": 0, "p75": 0, "p95": 0}}
  },
  "library_versions": {"python": "3.12.x", "scikit-learn": "x.y.z", "pandas": "x.y.z", "numpy": "x.y.z"}
}
```

Numbers above are placeholders for the shape only. `training_reference` is computed on the training rows and is the baseline for the monitoring check.

`artifacts.py` exposes `save_model(...)` and `load_model(version) -> (pipeline, metadata)`. `load_model` checks that the installed scikit-learn version equals the one in metadata and raises a clear error otherwise. `docs/modeling.md` notes that joblib files must only be loaded from trusted sources.

## 10. Reproducibility expectations

- Same machine, same lockfile: identical split files and identical metrics.
- Different OS or CPU: split files identical; metrics can differ in the last decimals because of floating-point differences in numerical libraries. `make reproduce` reports the maximum absolute difference per metric and treats anything under 1e-6 as equal.
- The README states these expectations, as the brief asks to "state any expected difference".

## 11. Tests for this spec

| Test | Checks |
|---|---|
| `test_features_fixture_values` | Exact expected values on synthetic records |
| `test_features_missing_vital` | count 0, mean and last NaN, flag 1 |
| `test_features_last_value_tiebreak` | Same minute, higher `row_order` wins |
| `test_features_columns_and_order` | Columns equal `FEATURE_COLUMNS` |
| `test_no_forbidden_columns` | Adding a forbidden column to the input never reaches the output |
| `test_split_no_overlap_and_complete` | Disjoint, union complete |
| `test_split_deterministic` | Two runs, identical output |
| `test_split_death_rates_close` (data marker) | Within 1 point |
| `test_preprocessing_fitted_on_train_only` | Imputer medians equal training medians |
| `test_threshold_meets_target` | On a synthetic example, chosen threshold reaches target sensitivity and is the highest that does |
| `test_bootstrap_deterministic` | Same seed, same intervals |
| `test_load_model_unknown_version` | Clear error |
