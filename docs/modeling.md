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
