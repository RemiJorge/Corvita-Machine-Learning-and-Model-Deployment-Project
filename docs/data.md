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
| `downloaded_at` | UTC timestamp of the ingest run |
| `published_checksums` | Parsed PhysioNet sums, or `null` |
| `files[]` | Each configured raw file: URL, size, SHA-256, published match flag |
| `record_files.count` | Number of `*.txt` record files under `data/raw/set-a/` |
| `record_files.sha256_of_sorted_file_hashes` | SHA-256 of the newline-joined list of per-file digests (files sorted by name) |

Model metadata later stores the SHA-256 of `manifest.json` itself as `training_data_sha256`.

## Later stages (F2 onward)

Parsing, cleaning, the 24 h cutoff, and table builds are documented here as they land in F2 and F3. See `specs/03_DATA_SPEC.md` for the authoritative rules.
