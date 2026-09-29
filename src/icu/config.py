"""Load and validate ``config/config.yaml`` for pipeline and serving."""

from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG_PATH = Path("config/config.yaml")

_TOP_LEVEL_KEYS = (
    "seed",
    "paths",
    "source",
    "cutoff_minutes",
    "vitals",
    "physiological_bounds",
    "admission_bounds",
    "split",
    "models",
    "threshold",
    "evaluation",
    "serving",
    "monitoring",
)

_PATH_KEYS = (
    "raw_dir",
    "interim_dir",
    "processed_dir",
    "manifest",
    "splits_dir",
    "models_dir",
    "reports_dir",
    "request_log",
)

_SOURCE_KEYS = ("dataset_version", "base_url", "files")


def _require_key(mapping: dict[str, Any], key: str, prefix: str = "") -> Any:
    """Return ``mapping[key]`` or raise with a message that names the missing key."""
    if key not in mapping:
        label = f"{prefix}.{key}" if prefix else key
        raise ValueError(f"Missing required config key: {label}")
    return mapping[key]


def _validate_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Check that every required key is present."""
    for key in _TOP_LEVEL_KEYS:
        _require_key(raw, key)

    paths = raw["paths"]
    if not isinstance(paths, dict):
        raise ValueError("Missing required config key: paths")
    for key in _PATH_KEYS:
        _require_key(paths, key, "paths")

    source = raw["source"]
    if not isinstance(source, dict):
        raise ValueError("Missing required config key: source")
    for key in _SOURCE_KEYS:
        _require_key(source, key, "source")

    return raw


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    """Load project configuration from YAML and validate required keys.

    Args:
        path: Path to ``config.yaml``. Defaults to ``config/config.yaml`` relative
            to the current working directory.

    Returns:
        The parsed configuration as a plain dict.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If a required key is missing or the YAML is not a mapping.
    """
    config_path = Path(path) if path is not None else _DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict):
        raise ValueError("Config root must be a mapping")

    return _validate_config(raw)
