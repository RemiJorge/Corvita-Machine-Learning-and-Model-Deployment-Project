"""Download PhysioNet set A, verify checksums, and write the data manifest."""

from __future__ import annotations

import hashlib
import json
import logging
import tarfile
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from icu.config import load_config

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1_048_576
DATASET_NAME = "PhysioNet Challenge 2012"
DATASET_LICENSE = "Open Data Commons Attribution License v1.0"
CHECKSUMS_FILENAME = "SHA256SUMS.txt"
ARCHIVE_NAME = "set-a.tar.gz"
EXTRACT_DIR_NAME = "set-a"


def sha256_file(path: Path) -> str:
    """Return the lowercase hex SHA-256 digest of a file read in chunks.

    Args:
        path: Path to the file to hash.

    Returns:
        Hex-encoded SHA-256 digest.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def parse_sha256sums(text: str) -> dict[str, str]:
    """Parse a PhysioNet-style SHA256SUMS file into ``filename -> hex digest``."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        digest, name = parts[0], parts[-1]
        if name.startswith("*"):
            name = name[1:]
        result[Path(name).name] = digest.lower()
    return result


def fetch_published_checksums(base_url: str) -> dict[str, str] | None:
    """Download ``SHA256SUMS.txt`` from the dataset version root, if present.

    Args:
        base_url: Directory URL ending with ``/`` (from config ``source.base_url``).

    Returns:
        Parsed checksum map, or ``None`` when the file is not published (HTTP 404).
    """
    url = f"{base_url.rstrip('/')}/{CHECKSUMS_FILENAME}"
    request = urllib.request.Request(url, headers={"User-Agent": "icu-mortality/0.2.0"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            logger.info(
                "No %s at %s; skipping published checksum comparison",
                CHECKSUMS_FILENAME,
                url,
            )
            return None
        raise
    return parse_sha256sums(text)


def verify_against_published(
    raw_dir: Path,
    filenames: list[str],
    published: dict[str, str] | None,
) -> dict[str, bool | None]:
    """Compare on-disk file hashes with published sums.

    Args:
        raw_dir: Directory containing the downloaded archives.
        filenames: Basenames to verify (must exist under ``raw_dir``).
        published: Map from ``parse_sha256sums`` or ``None`` if unavailable.

    Returns:
        Per-file ``published_sha256_match`` flags (``None`` when no published sum exists).

    Raises:
        FileNotFoundError: If a listed file is missing.
        ValueError: If a hash does not match the published value.
    """
    matches: dict[str, bool | None] = {}
    for name in filenames:
        path = raw_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"Missing raw file for verification: {path}")
        digest = sha256_file(path)
        if published is None or name not in published:
            matches[name] = None
            continue
        expected = published[name].lower()
        if digest != expected:
            raise ValueError(f"SHA-256 mismatch for {name}: local {digest}, published {expected}")
        matches[name] = True
    return matches


def download(
    url: str,
    dest: Path,
    *,
    expected_sha256: str | None = None,
) -> tuple[bool, str]:
    """Stream a URL to ``dest``, or reuse an existing file when its hash matches.

    Args:
        url: File URL to fetch when needed.
        dest: Output path under ``data/raw/``.
        expected_sha256: When set, an existing file must match this digest to skip download.

    Returns:
        ``(downloaded, sha256_hex)`` where ``downloaded`` is False when the file was reused.

    Raises:
        ValueError: If an existing file's digest does not match ``expected_sha256``.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        digest = sha256_file(dest)
        if expected_sha256 is not None and digest != expected_sha256.lower():
            raise ValueError(
                f"Existing file {dest} has SHA-256 {digest}, expected {expected_sha256.lower()}"
            )
        logger.info("Found on disk (verified): %s", dest.name)
        return False, digest

    logger.info("Downloading %s", url)
    request = urllib.request.Request(url, headers={"User-Agent": "icu-mortality/0.2.0"})
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=600) as response, dest.open("wb") as out:
        while True:
            chunk = response.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            out.write(chunk)
    hex_digest = digest.hexdigest()
    if expected_sha256 is not None and hex_digest != expected_sha256.lower():
        dest.unlink(missing_ok=True)
        raise ValueError(
            f"Downloaded {dest.name} SHA-256 {hex_digest}, expected {expected_sha256.lower()}"
        )
    return True, hex_digest


def extract_archive(archive_path: Path, raw_dir: Path) -> None:
    """Extract ``set-a.tar.gz`` into ``raw_dir/set-a/`` when that folder is missing."""
    extract_dir = raw_dir / EXTRACT_DIR_NAME
    if extract_dir.is_dir() and any(extract_dir.glob("*.txt")):
        logger.info("Extracted records already present at %s; skipping extraction", extract_dir)
        return
    logger.info("Extracting %s to %s", archive_path.name, extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(path=raw_dir, filter="data")


def compute_record_files_digest(set_a_dir: Path) -> dict[str, Any]:
    """Hash each record file and aggregate a single digest over sorted per-file hashes."""
    paths = sorted(set_a_dir.glob("*.txt"), key=lambda p: p.name)
    if not paths:
        raise ValueError(f"No record files found in {set_a_dir}")
    per_file = [sha256_file(path) for path in paths]
    aggregate_input = "\n".join(per_file).encode("ascii")
    aggregate = hashlib.sha256(aggregate_input).hexdigest()
    return {"count": len(paths), "sha256_of_sorted_file_hashes": aggregate}


def write_manifest(
    manifest_path: Path,
    *,
    dataset_version: str,
    base_url: str,
    file_entries: list[dict[str, Any]],
    record_files: dict[str, Any],
    published_checksums: dict[str, str] | None,
) -> None:
    """Write ``data/manifest.json`` with provenance fields from the data spec."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "dataset": DATASET_NAME,
        "dataset_version": dataset_version,
        "license": DATASET_LICENSE,
        "downloaded_at": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "published_checksums": published_checksums,
        "files": file_entries,
        "record_files": record_files,
    }
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote manifest %s", manifest_path)


def main(config_path: Path | str | None = None) -> None:
    """Run download-or-verify, optional extraction, and manifest generation."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = load_config(config_path)
    raw_dir = Path(config["paths"]["raw_dir"])
    manifest_path = Path(config["paths"]["manifest"])
    source = config["source"]
    base_url: str = source["base_url"]
    dataset_version: str = source["dataset_version"]
    filenames: list[str] = list(source["files"])

    published = fetch_published_checksums(base_url)

    file_entries: list[dict[str, Any]] = []
    for name in filenames:
        expected = published.get(name) if published else None
        url = f"{base_url.rstrip('/')}/{name}"
        dest = raw_dir / name
        _, digest = download(url, dest, expected_sha256=expected)
        file_entries.append(
            {
                "name": name,
                "url": url,
                "bytes": dest.stat().st_size,
                "sha256": digest,
                "published_sha256_match": None,
            }
        )

    matches = verify_against_published(raw_dir, filenames, published)
    for entry in file_entries:
        entry["published_sha256_match"] = matches[entry["name"]]

    archive_path = raw_dir / ARCHIVE_NAME
    if archive_path.is_file():
        extract_archive(archive_path, raw_dir)

    record_files = compute_record_files_digest(raw_dir / EXTRACT_DIR_NAME)
    write_manifest(
        manifest_path,
        dataset_version=dataset_version,
        base_url=base_url,
        file_entries=file_entries,
        record_files=record_files,
        published_checksums=published,
    )


if __name__ == "__main__":
    main()
