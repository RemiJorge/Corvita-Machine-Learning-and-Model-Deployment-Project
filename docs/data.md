# Data pipeline

This page documents the PhysioNet Challenge 2012 set A inputs used in this project.

## Source

- Dataset page: https://physionet.org/content/challenge-2012/1.0.0/
- Version used: **1.0.0** (see `config/config.yaml` → `source.dataset_version`)
- Files used: `set-a.tar.gz` (record archives) and `Outcomes-a.txt` (labels and severity scores)
- Download base URL: `https://physionet.org/files/challenge-2012/1.0.0/` (also in config)

Raw and processed tables stay out of Git. Only `data/manifest.json` is committed once ingest has run.

## License

PhysioNet lists the data files under the **Open Data Commons Attribution License v1.0** (ODC-By). The same string is stored in `data/manifest.json` → `license`.

## Manual placement

You may copy `set-a.tar.gz`, `Outcomes-a.txt`, and/or an extracted `set-a/` folder into `data/raw/` instead of downloading. `python -m icu.ingest` still:

1. Computes SHA-256 for each configured archive or text file.
2. Compares against PhysioNet published sums when a checksum file exists.
3. Extracts `set-a.tar.gz` into `data/raw/set-a/` only when that folder is missing.
4. Writes or refreshes `data/manifest.json`.

When a file is already present and its digest matches the expected value, ingest logs that the file was found on disk and does not download it again.

## Checksums and manifest

Ingest tries to download `SHA256SUMS.txt` from the dataset version root. For Challenge 2012 v1.0.0, PhysioNet does **not** publish that file (HTTP 404). In that case the manifest sets `"published_checksums": null` and each file entry has `"published_sha256_match": null`. Local SHA-256 digests are still recorded.

When a checksum file exists, a mismatch stops the run with an error.

`data/manifest.json` fields:

| Field | Meaning |
|---|---|
| `dataset`, `dataset_version`, `license` | Provenance |
| `downloaded_at` | UTC timestamp of the first ingest that produced the current file checksums (unchanged on later `make data` if digests match) |
| `published_checksums` | Parsed PhysioNet sums, or `null` |
| `files[]` | Each configured raw file: URL, size, SHA-256, published match flag |
| `record_files.count` | Number of `*.txt` record files under `data/raw/set-a/` |
| `record_files.sha256_of_sorted_file_hashes` | SHA-256 of the newline-joined list of per-file digests (files sorted by name) |

Model metadata later stores the SHA-256 of `manifest.json` itself as `training_data_sha256`.

## Later stages (F2 onward)

Parsing, cleaning, the 24 h cutoff, and table builds are documented here as they land in F2 and F3. Authoritative rules: `docs/process/specs/03_DATA_SPEC.md`.

### Parsing (F2)

`python -m icu.parse` reads every `data/raw/set-a/<RecordID>.txt` in sorted file name order.

- CSV header `Time,Parameter,Value`; each body line is split on the first two commas only.
- `Time` must match `HH:MM` and converts to integer minutes (`24:00` → 1440). Minutes part 60 or more is rejected.
- `Value` must be numeric. The file name must match the `00:00,RecordID,<id>` descriptor row.
- Output: `data/interim/measurements.parquet` with columns `record_id`, `minute`, `parameter`, `value`, `row_order`.
- Integrity checks: number of files equals distinct `record_id` equals rows in `Outcomes-a.txt`; one-to-one join on `record_id`; `In-hospital_death` in `{0, 1}` only.
- The 24 h cutoff is **not** applied here; rows after minute 1440 remain until F3 (`icu.tables`).

Last run (`make data` on set A): **4000** records, **1 757 980** measurement rows, death rate **0.1385** (554 / 4000).

### Cleaning (F2)

`python -m icu.quality` reads the interim parquet, applies rules in `icu/quality.py` (reused later by the API), and overwrites the same parquet plus `reports/data_quality.json`.

1. `-1` → missing (NaN); counted per parameter (ADR: `docs/decisions/003-handling-minus-one.md`).
2. Vitals HR, RespRate, Temp outside inclusive `physiological_bounds` in config → NaN; counted per vital.
3. At minute 0: `Age` outside `admission_bounds.Age`, `Gender` not in `{0, 1}`, `ICUType` not in `{1, 2, 3, 4}` → NaN; counted.
4. Exact duplicate rows (same `record_id`, `minute`, `parameter`, `value`) dropped; lowest `row_order` kept.

Bounds rationale: `docs/decisions/002-physiological-bounds.md`.

### Quality report (F2)

Path: `reports/data_quality.json`. F2 fields cover parsing and cleaning; F3 (`icu.tables`) fills `n_after_cutoff`, `n_measurements_used`, `records_without_any_value_in_24h` per vital, and `records_with_all_vitals_missing_in_24h`.

Summary from the last full run:

| | Value |
|---|---|
| `n_records` | 4000 |
| `n_deaths` / `death_rate` | 554 / 0.1385 |
| Gender missing (`-1`) | 3 |
| HR `n_out_of_bounds` | 16 |
| RespRate `n_out_of_bounds` | 62 |
| Temp `n_out_of_bounds` | 130 |
| HR / RespRate / Temp `n_minus_one` | 0 / 0 / 0 |

Percentiles for vitals and Age are in the JSON file under `descriptors` and `vitals`.

### RespRate missingness and mechanical ventilation (O0)

In the first 1440 minutes, **2405** records have at least one `MechVent = 1` row; **none** of them also have a non-missing `RespRate` in that window (`resp_rate_present_mechvent_yes`: 0 records). Among the **2903** records with no RespRate in 24 h, **2405** (83 %) coincide with `MechVent = 1`; the remaining **498** have no ventilator flag. Death rate is higher when RespRate is missing without MechVent (95/498, 19.1 %) than when RespRate is present (85/1097, 7.7 %); ventilated records without RespRate are 374/2405 (15.6 %). The pattern supports treating RespRate absence as clinically informative (ventilated patients are monitored differently), which motivates the `resp_rate_missing` feature flag rather than imputing a rate. Full counts: `reports/data_quality.json` → `resp_rate_missing_vs_mechvent`.

### Spot-check raw file vs parquet

Pick a record id present in `data/raw/set-a/` (example **132539**):

```bash
uv run python -c "
import pandas as pd
rid = 132539
df = pd.read_parquet('data/interim/measurements.parquet')
print(df[df.record_id == rid].sort_values(['minute','row_order']).head(12))
"
```

Compare printed rows to the first lines of `data/raw/set-a/132539.txt` (same times, parameters, and values after cleaning: `-1` shows as NaN, out-of-range vitals as NaN).

### 24 h cutoff and tables (F3)

`python -m icu.tables` reads cleaned `data/interim/measurements.parquet` and `Outcomes-a.txt`, applies the same cutoff the API will use (`apply_cutoff`, `cutoff_minutes` in config, default 1440), and writes:

| File | Columns | Grain |
|---|---|---|
| `data/processed/admission.parquet` | `record_id`, `age`, `gender`, `icu_type`, `in_hospital_death` | one row per record |
| `data/processed/vitals.parquet` | `record_id`, `minute`, `parameter`, `value`, `row_order` | one row per kept HR, RespRate, or Temp measurement |

Rules:

- A measurement is kept when `minute <= cutoff_minutes` (`24:00` → 1440 included, `24:01` → 1441 excluded).
- Admission fields come from `00:00` descriptor rows only; later duplicate descriptors are ignored.
- Vital rows that are missing after F2 cleaning are dropped from `vitals.parquet`.
- Cutoff exclusion counts are logged and merged into `reports/data_quality.json`.

Check max minute in vitals after a full run:

```bash
uv run python -c "import pandas as pd; print(pd.read_parquet('data/processed/vitals.parquet').minute.max())"
```

Expect **1440 or less**.

### Selection bias

Set A only includes patients who stayed in the ICU at least 48 hours. A prediction at 24 hours in practice would also apply to patients who die or leave before 48 hours; those patients, often the most severe, are absent from training and evaluation. Reported performance describes a more homogeneous population than real early ICU mortality screening, and calibration may not transfer. Other limits: single US hospital system, adults only, historical data, three vitals and three admission fields. This does not transfer to neonates in an incubator.

### Pipeline command

`make data` runs ingest, then parse, then quality, then tables.

See `docs/process/specs/03_DATA_SPEC.md` for the authoritative rules.
