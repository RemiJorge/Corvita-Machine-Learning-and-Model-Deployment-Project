"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
import sklearn
from fastapi.testclient import TestClient

from icu.api.app import create_app
from icu.features import FEATURE_COLUMNS
from icu.train import build_logreg_pipeline

_TEST_CONFIG = """
seed: 42
paths:
  raw_dir: data/raw
  interim_dir: data/interim
  processed_dir: data/processed
  manifest: data/manifest.json
  splits_dir: splits
  models_dir: models
  reports_dir: reports
  request_log: logs/requests.jsonl
source:
  dataset_version: "1.0.0"
  base_url: "https://example.com/"
  files: []
cutoff_minutes: 1440
vitals:
  - HR
  - RespRate
  - Temp
physiological_bounds:
  HR: [20, 300]
  RespRate: [1, 80]
  Temp: [25.0, 45.0]
admission_bounds:
  Age: [15, 120]
  ICUType: [1, 4]
split:
  train: 0.7
  val: 0.15
  test: 0.15
models:
  logreg:
    C: [0.01]
  hgb:
    learning_rate: [0.05]
    max_depth: [2]
    min_samples_leaf: [20]
    max_iter: [100]
threshold:
  target_sensitivity: 0.8
evaluation:
  bootstrap_resamples: 10
  calibration_bins: 5
serving:
  model_version: "test"
monitoring:
  window_size: 10
  max_partial_rate_increase: 0.15
  max_insufficient_rate: 0.05
"""


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """FastAPI test client with a tiny fitted model in a temporary models folder."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text(_TEST_CONFIG, encoding="utf-8")

    models_root = tmp_path / "models" / "test"
    models_root.mkdir(parents=True)

    rng = np.random.default_rng(42)
    n = 40
    x = rng.normal(size=(n, len(FEATURE_COLUMNS)))
    x_df = pd.DataFrame(x, columns=FEATURE_COLUMNS)
    x_df["age"] = rng.uniform(20, 90, size=n)
    y = np.zeros(n, dtype=int)
    y[:8] = 1

    pipeline = build_logreg_pipeline(c_strength=0.1, seed=42)
    pipeline.fit(x_df, y)

    metadata = {
        "model_version": "test",
        "served_model": "logistic_regression",
        "created_at": "2026-09-30T12:00:00Z",
        "git_commit": "abcdef0",
        "training_data_sha256": "0" * 64,
        "threshold": 0.5,
        "library_versions": {"scikit-learn": sklearn.__version__},
    }
    joblib.dump(pipeline, models_root / "pipeline.joblib")
    (models_root / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    request_log = tmp_path / "requests.jsonl"
    monkeypatch.setenv("REQUEST_LOG_PATH", str(request_log))
    app = create_app(config_path, pipeline=pipeline, metadata=metadata)
    with TestClient(app) as client:
        yield client
