"""Tests for configuration loading."""

from pathlib import Path

import pytest
import yaml

from icu.config import load_config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "config.yaml"


def test_load_config_default_path() -> None:
    """Default config loads with all required keys."""
    config = load_config(DEFAULT_CONFIG)
    assert config["seed"] == 42
    assert config["cutoff_minutes"] == 1440
    assert config["paths"]["raw_dir"] == "data/raw"


def test_load_config_missing_top_level_key(tmp_path: Path) -> None:
    """A missing top-level key raises ValueError naming the key."""
    partial = {"seed": 1}
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(partial), encoding="utf-8")

    with pytest.raises(ValueError, match="Missing required config key: paths"):
        load_config(config_path)


def test_load_config_missing_nested_path_key(tmp_path: Path) -> None:
    """A missing key under paths raises ValueError with the dotted name."""
    data = {
        "seed": 42,
        "paths": {"raw_dir": "data/raw"},
        "source": {"dataset_version": "1.0.0", "base_url": "http://example.com", "files": []},
        "cutoff_minutes": 1440,
        "vitals": ["HR"],
        "physiological_bounds": {"HR": [1, 2]},
        "admission_bounds": {"Age": [1, 2]},
        "split": {"train": 0.7, "val": 0.15, "test": 0.15},
        "models": {"logreg": {"C": [1.0]}},
        "threshold": {"target_sensitivity": 0.8},
        "evaluation": {"bootstrap_resamples": 100, "calibration_bins": 10},
        "serving": {"model_version": "1.0.0"},
        "monitoring": {
            "window_size": 200,
            "max_partial_rate_increase": 0.15,
            "max_insufficient_rate": 0.05,
            "psi_alert": 0.25,
            "psi_min_requests": 200,
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(data), encoding="utf-8")

    with pytest.raises(ValueError, match=r"Missing required config key: paths\."):
        load_config(config_path)
