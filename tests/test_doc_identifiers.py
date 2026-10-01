"""Committed docs must quote the same identifiers as models/1.0.1/metadata.json (served)."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_readme_and_model_card_match_metadata_digest() -> None:
    metadata = json.loads(
        (REPO_ROOT / "models" / "1.0.1" / "metadata.json").read_text(encoding="utf-8")
    )
    digest = str(metadata["training_data_sha256"])
    commit = str(metadata["git_commit"])

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    model_card = (REPO_ROOT / "docs" / "model_card.md").read_text(encoding="utf-8")

    assert digest in readme
    assert digest in model_card
    assert commit in model_card
