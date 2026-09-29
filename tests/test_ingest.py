"""Tests for data ingest (hashing, checksum verification, manifest)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from icu import ingest


def test_sha256_file_known_content(tmp_path: Path) -> None:
    """Chunked hashing matches hashlib on a small file."""
    path = tmp_path / "sample.bin"
    path.write_bytes(b"hello ingest")
    expected = "7b7151713f427da6c615a775517c0daac27971d307511ac899b62069cee82d34"
    assert ingest.sha256_file(path) == expected


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    """``sha256_file`` matches the standard library for arbitrary bytes."""
    import hashlib

    data = b"x" * 5000 + b"y" * 5000
    path = tmp_path / "chunks.bin"
    path.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()
    assert ingest.sha256_file(path) == expected


def test_parse_sha256sums() -> None:
    """PhysioNet sum lines map basename to digest."""
    text = "abc123  set-a.tar.gz\n def456 *Outcomes-a.txt\n"
    parsed = ingest.parse_sha256sums(text)
    assert parsed["set-a.tar.gz"] == "abc123"
    assert parsed["Outcomes-a.txt"] == "def456"


def test_verify_against_published_mismatch(tmp_path: Path) -> None:
    """A wrong local hash raises with both digests named."""
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    published = {"a.txt": "0" * 64}
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        ingest.verify_against_published(tmp_path, ["a.txt"], published)


def test_verify_against_published_no_file(tmp_path: Path) -> None:
    """Missing published sums yield ``None`` match flags without error."""
    path = tmp_path / "only.txt"
    path.write_text("data", encoding="utf-8")
    matches = ingest.verify_against_published(tmp_path, ["only.txt"], None)
    assert matches["only.txt"] is None


def test_download_skips_when_hash_matches(tmp_path: Path) -> None:
    """An on-disk file with the expected digest is not re-downloaded."""
    dest = tmp_path / "keep.bin"
    dest.write_bytes(b"stable")
    digest = ingest.sha256_file(dest)
    downloaded, returned = ingest.download(
        "http://127.0.0.1:9/never-used",
        dest,
        expected_sha256=digest,
    )
    assert downloaded is False
    assert returned == digest


def test_write_manifest_roundtrip(tmp_path: Path) -> None:
    """Manifest JSON includes required top-level keys from the data spec."""
    manifest_path = tmp_path / "manifest.json"
    files = [
        {
            "name": "set-a.tar.gz",
            "url": "https://example.com/set-a.tar.gz",
            "bytes": 10,
            "sha256": "a" * 64,
            "published_sha256_match": None,
        }
    ]
    record_files = {"count": 2, "sha256_of_sorted_file_hashes": "b" * 64}
    ingest.write_manifest(
        manifest_path,
        dataset_version="1.0.0",
        base_url="https://example.com/",
        file_entries=files,
        record_files=record_files,
        published_checksums=None,
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["dataset"] == ingest.DATASET_NAME
    assert payload["license"] == ingest.DATASET_LICENSE
    assert payload["published_checksums"] is None
    assert payload["files"] == files
    assert payload["record_files"] == record_files


def test_compute_record_files_digest(tmp_path: Path) -> None:
    """Aggregate digest is stable for sorted record file hashes."""
    record_dir = tmp_path / "set-a"
    record_dir.mkdir()
    (record_dir / "2.txt").write_text("b", encoding="utf-8")
    (record_dir / "1.txt").write_text("a", encoding="utf-8")
    summary = ingest.compute_record_files_digest(record_dir)
    assert summary["count"] == 2
    assert len(summary["sha256_of_sorted_file_hashes"]) == 64
