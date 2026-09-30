"""Tests for model packaging and reproduction comparison."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import pytest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from icu.artifacts import (
    compare_metric_dicts,
    compute_training_reference,
    load_model,
)
from icu.features import FEATURE_COLUMNS
from icu.train import CONTINUOUS_COLUMNS


def test_load_model_unknown_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
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
vitals: [HR]
physiological_bounds:
  HR: [20, 300]
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
  model_version: "9.9.9"
monitoring:
  window_size: 10
  max_partial_rate_increase: 0.15
  max_insufficient_rate: 0.05
""",
        encoding="utf-8",
    )
    models_root = tmp_path / "models"
    models_root.mkdir()
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError, match="Unknown model version"):
        load_model("9.9.9", config_path=config_path)


def test_load_model_sklearn_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
seed: 42
paths:
  models_dir: models
  raw_dir: data/raw
  interim_dir: data/interim
  processed_dir: data/processed
  manifest: data/manifest.json
  splits_dir: splits
  reports_dir: reports
  request_log: logs/requests.jsonl
source:
  dataset_version: "1.0.0"
  base_url: "https://example.com/"
  files: []
cutoff_minutes: 1440
vitals: [HR]
physiological_bounds:
  HR: [20, 300]
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
  model_version: "1.0.0"
monitoring:
  window_size: 10
  max_partial_rate_increase: 0.15
  max_insufficient_rate: 0.05
""",
        encoding="utf-8",
    )
    version_dir = tmp_path / "models" / "1.0.0"
    version_dir.mkdir(parents=True)
    pipeline = Pipeline([("scale", StandardScaler())])
    joblib.dump(pipeline, version_dir / "pipeline.joblib")
    metadata = {
        "library_versions": {"scikit-learn": "0.0.0-not-installed"},
    }
    (version_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="scikit-learn version mismatch"):
        load_model("1.0.0", config_path=config_path)


def test_training_reference_rates() -> None:
    import pandas as pd

    rows = [
        {col: 0.0 for col in FEATURE_COLUMNS},
        {col: 0.0 for col in FEATURE_COLUMNS},
        {col: 0.0 for col in FEATURE_COLUMNS},
    ]
    rows[0]["hr_missing"] = 1
    rows[0]["resp_rate_missing"] = 0
    rows[0]["temp_missing"] = 0
    rows[1]["hr_missing"] = 1
    rows[1]["resp_rate_missing"] = 1
    rows[1]["temp_missing"] = 0
    rows[2]["hr_missing"] = 1
    rows[2]["resp_rate_missing"] = 1
    rows[2]["temp_missing"] = 1
    for column in CONTINUOUS_COLUMNS:
        rows[0][column] = 1.0
        rows[1][column] = 2.0
        rows[2][column] = 3.0

    frame = pd.DataFrame(rows)
    ref = compute_training_reference(frame)

    assert ref["missing_rate"]["HR"] == pytest.approx(1.0)
    assert ref["partial_rate"] == pytest.approx(2 / 3)
    assert ref["insufficient_rate"] == pytest.approx(1 / 3)
    assert "age" in ref["feature_quantiles"]


def test_compare_metrics_identical() -> None:
    baseline = {"a": {"value": 1.0}, "b": 2}
    same = {"a": {"value": 1.0}, "b": 2}
    assert compare_metric_dicts(baseline, same) == []

    different = {"a": {"value": 1.0000011}}
    diffs = compare_metric_dicts(baseline, different, tolerance=1e-6)
    assert len(diffs) >= 1
    assert diffs[0][3] > 1e-6
