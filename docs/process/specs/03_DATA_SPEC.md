# 03. Data specification

Facts below come from the dataset documentation as understood when writing this spec. The agent verifies each one against the real files during F1 and F2, and stops to ask if something differs.

## 1. Source

- Dataset page: https://physionet.org/content/challenge-2012/1.0.0/
- Files used: the set A archive (expected `set-a.tar.gz`, a zip may also exist) and `Outcomes-a.txt`.
- Check the file listing on the dataset page before writing the config. If names differ, update `config.yaml` and record the actual names in `docs/data.md`.
- Record the license displayed on the page in the manifest and in `docs/data.md`. Raw and processed data are never committed.

## 2. Download and provenance (F1)

### Manual placement of raw files

The human owner may copy `set-a.tar.gz` and `Outcomes-a.txt` into `data/raw/` instead of using the downloader. In that case `main()` must still compute SHA-256, compare against PhysioNet published sums when available, extract the archive if `data/raw/set-a/` is missing, and write or refresh `data/manifest.json`. Log that files were found on disk rather than downloaded. Do not skip verification.

1. Download each file with `urllib.request` into `data/raw/`, streaming to disk (skip download when a file already exists and its SHA-256 matches the expected value).
2. Compute SHA-256 with `hashlib`, reading in chunks.
3. If the dataset publishes a checksum file (PhysioNet usually provides `SHA256SUMS.txt` at the version root), download it and compare. A mismatch is a hard error. If no such file exists, say so in the manifest (`"published_checksums": null`) and in `docs/data.md`.
4. Extract the archive into `data/raw/set-a/`.
5. Write `data/manifest.json`:

```json
{
  "dataset": "PhysioNet Challenge 2012",
  "dataset_version": "1.0.0",
  "license": "<as displayed on the dataset page>",
  "downloaded_at": "2026-10-01T09:12:44Z",
  "files": [
    {"name": "set-a.tar.gz", "url": "...", "bytes": 0, "sha256": "...", "published_sha256_match": true},
    {"name": "Outcomes-a.txt", "url": "...", "bytes": 0, "sha256": "...", "published_sha256_match": true}
  ],
  "record_files": {"count": 0, "sha256_of_sorted_file_hashes": "..."}
}
```

`sha256_of_sorted_file_hashes` hashes the sorted list of per-record file hashes, so one value identifies the extracted content. The model metadata later stores the SHA-256 of `manifest.json` itself as `training_data_sha256`.

## 3. Raw format

### Record files

One text file per record, named `<RecordID>.txt`, CSV with header `Time,Parameter,Value`.

- `Time` is `HH:MM` elapsed since ICU admission. Hours can exceed 24 (data covers up to 48 hours).
- The first rows at `00:00` are general descriptors: `RecordID`, `Age`, `Gender`, `Height`, `ICUType`, `Weight`.
- Later rows are time series measurements. The same parameter can appear several times, sometimes at the same `Time`.
- Parameters used here: `HR` (beats per minute), `RespRate` (breaths per minute), `Temp` (degrees Celsius). Many other parameters exist (labs, `MechVent`, etc.) and are ignored by the model.

Descriptor codes:

| Field | Values |
|---|---|
| `Gender` | 0 = female, 1 = male, -1 = missing |
| `ICUType` | 1 = Coronary Care Unit, 2 = Cardiac Surgery Recovery Unit, 3 = Medical ICU, 4 = Surgical ICU |
| `Age` | years |

### Outcomes file

`Outcomes-a.txt`, CSV with columns `RecordID`, `SAPS-I`, `SOFA`, `Length_of_stay`, `Survival`, `In-hospital_death`.

Only `RecordID` and `In-hospital_death` are read into the modeling tables. The other four columns are outcomes or severity scores computed with information outside the first 24 hours of our inputs, and they are listed in `FORBIDDEN_COLUMNS`.

## 4. Parsing rules (F2)

Parsing and cleaning stop at `measurements.parquet`. Rows after minute 1440 remain in that file until F3 applies the cutoff in `icu.tables`. Fixtures under `tests/fixtures/` include a measurement after 24:00 for F3 boundary tests.

1. Read every `*.txt` in `data/raw/set-a/`. Sort files by name so the order is deterministic.
2. Skip the header line. Strip whitespace. Split on the first two commas only.
3. Convert `Time` to integer minutes: `int(hh) * 60 + int(mm)`. Reject a time whose minutes part is 60 or more, or that does not match `^\d{2}:\d{2}$`, with an error naming file and line number.
4. Convert `Value` to float. A non-numeric value is an error naming file and line.
5. Keep `RecordID` from the file name and check that it equals the `RecordID` descriptor row. A mismatch is an error.
6. Keep a `row_order` column (line index inside the file). It is used for deterministic tie-breaking.
7. Output `data/interim/measurements.parquet` with columns `record_id` (int), `minute` (int), `parameter` (str, categorical), `value` (float), `row_order` (int).

Checks asserted at the end of parsing:

- number of files equals number of distinct `record_id`;
- number of rows in the outcomes file equals number of files;
- every `record_id` has exactly one outcome row (one-to-one join);
- `In-hospital_death` only contains 0 and 1.

Log the record count and the death rate. Expected order of magnitude: 4000 records and a death rate near 14 %. These are sanity values, not hardcoded assertions.

## 5. Cleaning rules (F2)

All rules live in `icu/quality.py` and are reused by the API.

1. **Missing marker.** A value of `-1` means missing, in descriptors and in time series. It becomes `NaN`. Count per parameter.
2. **Physiological bounds.** For each vital, values outside `physiological_bounds` in the config (inclusive) become `NaN`. Count per parameter. Rationale to write in the ADR: values such as a heart rate of 0 or a temperature of 10 °C are recording errors, and keeping them would let the model learn from artifacts.
3. **Admission bounds.** `Age` outside `admission_bounds.Age`, `ICUType` outside 1 to 4, `Gender` not in {0, 1} become `NaN`. Count.
4. **Choosing bounds.** In F2, compute the 0.1, 1, 50, 99 and 99.9 percentiles of each vital and of `Age`, put them in the quality report, and check the config bounds against them. Adjust the config only with an ADR that cites these percentiles.
5. **Duplicates.** Exact duplicate rows (same record, minute, parameter, value) are kept once and counted. Several different values at the same minute are all kept; they count as separate measurements for `count` and `mean`, and the tie-break for `last` is the highest `row_order`.

Rows made `NaN` by rules 1 to 3 are removed from the vitals table (a missing measurement is not a measurement). They remain counted in the quality report.

## 6. Quality report (F2, completed in F3)

`reports/data_quality.json`:

```json
{
  "n_records": 0,
  "n_deaths": 0,
  "death_rate": 0.0,
  "descriptors": {
    "Age": {"missing": 0, "out_of_bounds": 0, "percentiles": {"p0.1": 0, "p1": 0, "p50": 0, "p99": 0, "p99.9": 0}},
    "Gender": {"missing": 0, "counts": {"0": 0, "1": 0}},
    "ICUType": {"missing": 0, "counts": {"1": 0, "2": 0, "3": 0, "4": 0}}
  },
  "vitals": {
    "HR": {
      "n_measurements_raw": 0,
      "n_minus_one": 0,
      "n_out_of_bounds": 0,
      "n_exact_duplicates": 0,
      "n_after_cutoff": 0,
      "n_measurements_used": 0,
      "records_without_any_value_in_24h": 0,
      "percentiles": {}
    }
  },
  "records_with_all_vitals_missing_in_24h": 0,
  "resp_rate_missing_vs_mechvent": {"note": "optional analysis, see section 9"}
}
```

`n_after_cutoff` and the `*_in_24h` fields are filled in F3.

## 7. The 24 hour cutoff (F3)

Implemented in `icu.tables` (`apply_cutoff`, `admission.parquet`, `vitals.parquet`). The API in F9 must import the same `apply_cutoff` before feature computation.

- A measurement is kept when `minute <= cutoff_minutes` (1440). The value 24:00 is included, 24:01 is excluded.
- Admission fields are taken from the `00:00` descriptor rows only. If a descriptor such as `Weight` reappears later as a time series, the later values are ignored (and `Weight` is not a feature anyway).
- The cutoff is applied in `tables.py` for training and inside the API service before feature computation. Both call the same function, `apply_cutoff(df, cutoff_minutes)`.

Output tables:

| File | Columns | Grain |
|---|---|---|
| `admission.parquet` | `record_id`, `age`, `gender`, `icu_type`, `in_hospital_death` | one row per record |
| `vitals.parquet` | `record_id`, `minute`, `parameter`, `value`, `row_order` | one row per kept measurement of HR, RespRate, Temp |

The label sits in `admission.parquet` for convenience, but `features.py` drops it before returning features, and a test checks this.

## 8. Selection bias (text for docs and model card)

Set A only includes patients who stayed in ICU at least 48 hours. In real use, a prediction made at 24 hours would also be made for patients who die or leave before 48 hours. Patients who die early, often the most severe cases, are therefore absent from both training and evaluation. The measured performance describes a population that is easier and more homogeneous than the real one, and the calibration may not transfer: the true death rate among all patients alive at 24 hours differs from the rate in this dataset. Other limits to state alongside it: data from a single hospital system in the United States, adults only, collected years ago, three vitals and three admission fields only. None of this transfers to newborns in an incubator.

## 9. Optional analysis: why RespRate is missing

Check whether records without any `RespRate` in the first 24 hours tend to have `MechVent = 1` in the same window, and report the cross-tabulation in the quality report and in `docs/data.md`. If the association holds, it supports the claim that missingness carries clinical information (ventilated patients are sicker and their breathing rate is recorded differently), which justifies the missing-data flags. This takes a few lines of pandas and is worth doing if F2 is on time. `MechVent` is used for this analysis only and never becomes a feature.

## 10. Tests for this spec

| Test | Checks |
|---|---|
| `test_time_to_minutes` | `"00:00"` -> 0, `"24:00"` -> 1440, `"47:59"` -> 2879, `"12:60"` raises |
| `test_parse_fixture_file` | Synthetic file parsed into the expected rows, including `row_order` |
| `test_record_id_mismatch_raises` | File name and descriptor disagree -> error |
| `test_minus_one_becomes_missing` | `-1` in `Gender` and in `HR` -> NaN and counted |
| `test_out_of_bounds_becomes_missing` | `HR = 0`, `Temp = 10` -> NaN and counted |
| `test_exact_duplicates_dropped` | Two identical rows -> one kept, counted once |
| `test_cutoff_keeps_1440` | Measurement at 1440 kept |
| `test_cutoff_drops_1441` | Measurement at 1441 dropped and counted |
| `test_admission_from_descriptors_only` | Admission values come from minute 0 rows |
| `test_outcomes_join_one_to_one` (data marker) | Real data: counts equal, no duplicates |
