# Modeling

## Features (F4)

`icu.features.compute_features(admission_df, vitals_df)` builds the model input matrix. It does not read files and does not use the outcome label. Training (`python -m icu.features`) and the prediction API (F9) call the same function on tables that already passed the 24 h cutoff and cleaning rules in `icu.tables` and `icu.quality`.

Column names and order are fixed by `FEATURE_COLUMNS` (19 columns). See `specs/04_MODELING_SPEC.md` section 1 for definitions.

### ICU type one-hot

`ICUType` is encoded as `icu_type_1` through `icu_type_4` inside `compute_features`, not in the scikit-learn pipeline. The four categories are fixed by the dataset. Nothing is learned from data at this step, so it cannot leak, and training and serving share the encoding by construction.

### Missing vital flags

For each vital, `*_missing` is 1 when `*_count` is 0. The flags overlap with count in information but are required by the brief and make logistic regression coefficients easier to read.

### Records without vitals

Every `record_id` in the admission table gets one feature row. If a patient has no measurement for a vital in the window, that vital has count 0, mean and last are missing, and the missing flag is 1.

### Last value tie-breaking

When several measurements share the latest minute for a vital, the value from the row with the highest `row_order` is used. See `docs/decisions/004-tie-breaking-last-vital.md`.

### Output artifact

`make features` writes `data/processed/features.parquet` with `record_id` plus the feature columns. The label stays in `admission.parquet` for splits and training.

## Split (F5)

`icu.split.stratified_split` assigns every `record_id` to train, validation, or test using labels from `admission.parquet` only.

### Procedure

1. Sort all record IDs ascending (with matching labels).
2. `train_test_split` with `test_size = val + test` (0.30 from config), `stratify=labels`, `random_state=seed`.
3. Split the holdout with `test_size = test / (val + test)` (0.50), same seed and stratification on holdout labels.
4. Write sorted IDs to `splits/train_ids.csv`, `splits/val_ids.csv`, `splits/test_ids.csv` (one column `record_id`).

Target fractions are 70 % / 15 % / 15 % from `config/config.yaml`. Actual group sizes follow scikit-learn stratified rounding. For 4000 records this is typically about 2800 train, 600 validation, and 600 test (exact counts appear in the split log).

### Grouping key

Each row is one ICU stay identified by `RecordID`. This dataset does not link multiple stays to the same patient, so patient-level grouping is not possible here. In NOA the grouping key would be the infant, as in the first technical exercise.

`make split` runs `python -m icu.split` and logs size and death rate per group.

## Training and validation selection (F6)

`icu.train` loads `features.parquet` and labels from `admission.parquet`, then keeps only rows whose `record_id` appears in `splits/train_ids.csv` or `splits/val_ids.csv`. The test ID file is not read during training (`python -m icu.train`).

### Pipelines

Logistic regression uses a `ColumnTransformer`: median imputation and scaling on continuous vitals and age, scaling on count features, passthrough on binary and ICU-type columns, then `LogisticRegression` with `C` from the config grid. `HistGradientBoostingClassifier` trains on the raw feature matrix (native missing support), with `early_stopping=False` so tuning uses only the project validation split.

Neither model uses `class_weight` (see `docs/decisions/005-no-class-weights.md`).

### Tuning

Hyperparameter grids live in `config/config.yaml`. Every combination is fit on **training rows only**, scored on validation, and appended to `reports/tuning.csv` (PR-AUC, AUROC, Brier, fit time).

Selection per model:

1. Highest validation PR-AUC.
2. If two candidates are within 0.005 PR-AUC, lower validation Brier wins.
3. If still tied: smaller `C` for logistic regression; for HGB, fewer `max_iter`, then smaller `max_depth`.

The winning hyperparameters are not refit on train plus validation. Preparation stays on the training set only so the validation threshold remains consistent with the fitted model. Test evaluation in F7 uses the same train-fitted model.

### Threshold

On validation probabilities for each selected model, the decision threshold is the highest value whose sensitivity is at least `threshold.target_sensitivity` (default 0.80). Validation specificity, precision, and alerts per 100 patients are stored in `reports/selection.json`. The Youden threshold is recorded for comparison only (`docs/decisions/006-threshold-rule.md`).

`make train` runs `python -m icu.train` and writes `reports/tuning.csv` and `reports/selection.json`.

## Test evaluation (F7)

`icu.evaluate` scores the **test split once**. It reads frozen hyperparameters and validation thresholds from `reports/selection.json`, refits both models on **training rows only**, and writes:

- `reports/metrics.json` (point metrics, naive baselines, 1000 bootstrap intervals, paired bootstrap for HGB minus logistic regression)
- `reports/missing_vitals.json` (natural missing-vital subgroups and vital ablation on test records)
- `reports/figures/roc.png`, `pr.png`, `calibration.png`

The served model is chosen from **validation** metrics only (`docs/decisions/007-served-model-choice.md`). Test numbers are reported but do not drive that choice.

`make evaluate` runs `python -m icu.evaluate`. Model serialization under `models/` is F8.

## Artifacts (F8)

`icu.artifacts.save_model` refits both models on training rows with hyperparameters frozen from `reports/selection.json`, then writes the served pipeline to `models/<model_version>/pipeline.joblib` and the comparison HGB model to `models/<model_version>/comparison/hist_gradient_boosting.joblib`. `metadata.json` records git commit, manifest digest, split file hashes, validation and test metrics for the served model, and a `training_reference` block from training rows for monitoring.

`load_model(version)` returns the served pipeline and metadata. It checks that the installed scikit-learn version matches the one stored in metadata. Only load joblib files from trusted sources.

`make package` runs `python -m icu.artifacts`. `make reproduce` saves a baseline of `splits/*.csv` and `reports/metrics.json`, reruns the full pipeline, then prints a short summary block (split status, metric count, max absolute diff, pass or fail). Numeric metrics must match within `1e-6` absolute difference.
