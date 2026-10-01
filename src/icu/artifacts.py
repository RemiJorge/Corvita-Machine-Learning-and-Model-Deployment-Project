"""Save and load trained model folders and metadata."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn

from icu.config import load_config
from icu.evaluate import (
    METRICS_FILENAME,
    choose_served_model,
    fit_frozen_models,
)
from icu.features import FEATURE_COLUMNS
from icu.ingest import sha256_file
from icu.psi import compute_psi_bins
from icu.split import TEST_IDS_CSV, TRAIN_IDS_CSV, VAL_IDS_CSV
from icu.train import (
    CONTINUOUS_COLUMNS,
    LOGISTIC_REGRESSION,
    load_labeled_features,
    read_record_ids,
)

logger = logging.getLogger(__name__)

SELECTION_FILENAME = "selection.json"
PIPELINE_FILENAME = "pipeline.joblib"
METADATA_FILENAME = "metadata.json"
HGB_COMPARISON_FILENAME = "hist_gradient_boosting.joblib"
REPRO_BASELINE_DIRNAME = ".repro_baseline"
METRIC_COMPARE_TOLERANCE = 1e-6

VITAL_MISSING_COLUMNS: tuple[str, ...] = ("hr_missing", "resp_rate_missing", "temp_missing")


def compute_training_reference(x_train: pd.DataFrame) -> dict[str, Any]:
    """Summarize training features for monitoring baselines.

    ``missing_rate`` is the fraction of rows with each vital's missing flag set.
    ``partial_rate`` is the fraction with exactly one or two vitals missing (some
    signal present). ``insufficient_rate`` is the fraction with all three vitals
    missing. These definitions align with future request-quality monitoring until
    the API abstention rules are implemented in F9.

    Args:
        x_train: Training feature matrix with ``FEATURE_COLUMNS``.

    Returns:
        Dictionary with ``missing_rate``, ``partial_rate``, ``insufficient_rate``,
        ``feature_quantiles``, and ``psi_bins``.
    """
    missing_flags = x_train[list(VITAL_MISSING_COLUMNS)].astype(int)
    n_rows = len(x_train)
    if n_rows == 0:
        msg = "Training reference requires at least one row"
        raise ValueError(msg)

    missing_sum = missing_flags.sum(axis=1)
    missing_rate = {
        "HR": float(missing_flags["hr_missing"].mean()),
        "RespRate": float(missing_flags["resp_rate_missing"].mean()),
        "Temp": float(missing_flags["temp_missing"].mean()),
    }
    partial_rate = float(np.mean((missing_sum >= 1) & (missing_sum <= 2)))
    insufficient_rate = float(np.mean(missing_sum >= 3))

    quantiles: dict[str, dict[str, float]] = {}
    for column in CONTINUOUS_COLUMNS:
        series = x_train[column].dropna()
        if len(series) == 0:
            quantiles[column] = {"p5": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p95": 0.0}
            continue
        percentiles = np.percentile(series.to_numpy(), [5, 25, 50, 75, 95])
        quantiles[column] = {
            "p5": float(percentiles[0]),
            "p25": float(percentiles[1]),
            "p50": float(percentiles[2]),
            "p75": float(percentiles[3]),
            "p95": float(percentiles[4]),
        }

    return {
        "missing_rate": missing_rate,
        "partial_rate": partial_rate,
        "insufficient_rate": insufficient_rate,
        "feature_quantiles": quantiles,
        "psi_bins": compute_psi_bins(x_train),
    }


def git_commit_and_dirty(repo_root: Path) -> tuple[str, bool]:
    """Return current git commit hash and whether the working tree is dirty.

    Args:
        repo_root: Repository root for git commands.

    Returns:
        Tuple of (short or full commit hash, dirty flag).

    Raises:
        RuntimeError: If git is unavailable or not a repository.
    """
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.PIPE,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.PIPE,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        msg = f"Could not read git state from {repo_root}: {exc}"
        raise RuntimeError(msg) from exc
    return commit, bool(status.strip())


def library_versions() -> dict[str, str]:
    """Return versions of Python and key runtime libraries."""
    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "scikit-learn": sklearn.__version__,
        "pandas": pd.__version__,
        "numpy": np.__version__,
    }


def build_metadata(
    config: dict[str, Any],
    selection: dict[str, Any],
    metrics: dict[str, Any],
    served_model: str,
    training_reference: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    """Assemble model metadata JSON (modeling spec section 9).

    Args:
        config: Loaded project config.
        selection: Contents of ``selection.json``.
        metrics: Contents of ``metrics.json``.
        served_model: ``logistic_regression`` or ``hist_gradient_boosting``.
        training_reference: Output of ``compute_training_reference``.
        repo_root: Repository root for git and relative paths.

    Returns:
        Metadata dictionary ready to serialize.
    """
    paths = config["paths"]
    splits_dir = Path(paths["splits_dir"])
    manifest_path = Path(paths["manifest"])
    git_commit, git_dirty = git_commit_and_dirty(repo_root)

    served_block = selection[served_model]
    served_metrics_block = metrics[served_model]

    created_at = datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "model_version": config["serving"]["model_version"],
        "served_model": served_model,
        "created_at": created_at,
        "code_version": package_version("icu-mortality"),
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "dataset_version": config["source"]["dataset_version"],
        "training_data_sha256": sha256_file(manifest_path),
        "split_files_sha256": {
            "train": sha256_file(splits_dir / TRAIN_IDS_CSV),
            "val": sha256_file(splits_dir / VAL_IDS_CSV),
            "test": sha256_file(splits_dir / TEST_IDS_CSV),
        },
        "seed": int(config["seed"]),
        "cutoff_minutes": int(config["cutoff_minutes"]),
        "physiological_bounds": config["physiological_bounds"],
        "feature_columns": list(FEATURE_COLUMNS),
        "hyperparameters": served_block["selected_params"],
        "threshold": float(served_block["threshold"]["threshold"]),
        "target_sensitivity": float(selection["target_sensitivity"]),
        "validation_metrics": served_block["validation_metrics"],
        "test_metrics": {
            "point_metrics": served_metrics_block["point_metrics"],
            "bootstrap": served_metrics_block["bootstrap"],
        },
        "training_reference": training_reference,
        "library_versions": library_versions(),
    }


def model_dir(config: dict[str, Any], model_version: str | None = None) -> Path:
    """Return the directory for a packaged model version."""
    version = model_version or config["serving"]["model_version"]
    return Path(config["paths"]["models_dir"]) / version


def save_model(config_path: Path | str | None = None, repo_root: Path | None = None) -> Path:
    """Fit frozen models on training data and write the model folder.

    Args:
        config_path: Optional path to ``config.yaml``.
        repo_root: Repository root for git metadata; defaults to cwd.

    Returns:
        Path to the model version directory.

    Raises:
        FileNotFoundError: If selection or metrics reports are missing.
        ValueError: If train rows do not match split IDs.
    """
    config = load_config(config_path)
    root = repo_root or Path.cwd()
    seed = int(config["seed"])
    reports_dir = Path(config["paths"]["reports_dir"])
    splits_dir = Path(config["paths"]["splits_dir"])

    selection_path = reports_dir / SELECTION_FILENAME
    metrics_path = reports_dir / METRICS_FILENAME
    if not selection_path.is_file():
        msg = f"Missing {selection_path}; run training and evaluation first"
        raise FileNotFoundError(msg)
    if not metrics_path.is_file():
        msg = f"Missing {metrics_path}; run evaluation first"
        raise FileNotFoundError(msg)

    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    served_model = choose_served_model(selection)

    train_ids = read_record_ids(splits_dir / TRAIN_IDS_CSV)
    labeled = load_labeled_features(config)
    train_mask = labeled["record_id"].isin(train_ids)
    x_train = labeled.loc[train_mask, FEATURE_COLUMNS]
    y_train = labeled.loc[train_mask, "in_hospital_death"].astype(int).to_numpy()

    if len(x_train) != len(train_ids):
        msg = "Split IDs do not match labeled feature rows"
        raise ValueError(msg)

    logreg, hgb = fit_frozen_models(selection, x_train, y_train, seed)
    training_reference = compute_training_reference(x_train)
    metadata = build_metadata(config, selection, metrics, served_model, training_reference, root)

    out_dir = model_dir(config)
    out_dir.mkdir(parents=True, exist_ok=True)
    comparison_dir = out_dir / "comparison"
    comparison_dir.mkdir(parents=True, exist_ok=True)

    served_pipeline = logreg if served_model == LOGISTIC_REGRESSION else hgb
    joblib.dump(served_pipeline, out_dir / PIPELINE_FILENAME)
    joblib.dump(hgb, comparison_dir / HGB_COMPARISON_FILENAME)

    metadata_path = out_dir / METADATA_FILENAME
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    logger.info("Wrote model package to %s (served=%s)", out_dir, served_model)
    return out_dir


def load_model(
    version: str,
    config_path: Path | str | None = None,
    models_dir: Path | str | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Load the served pipeline and metadata for a model version.

    Args:
        version: Folder name under ``models/`` (for example ``1.0.0``).
        config_path: Optional path to ``config.yaml`` for ``models_dir``.
        models_dir: Optional override for ``paths.models_dir`` (for example from env).

    Returns:
        Tuple of (fitted pipeline or classifier, metadata dict).

    Raises:
        FileNotFoundError: If the version directory or files are missing.
        ValueError: If the installed scikit-learn version does not match metadata.
    """
    config = load_config(config_path)
    if models_dir is not None:
        config = dict(config)
        paths = dict(config["paths"])
        paths["models_dir"] = str(models_dir)
        config["paths"] = paths
    directory = model_dir(config, version)
    if not directory.is_dir():
        msg = f"Unknown model version {version!r}: {directory} does not exist"
        raise FileNotFoundError(msg)

    pipeline_path = directory / PIPELINE_FILENAME
    metadata_path = directory / METADATA_FILENAME
    if not pipeline_path.is_file() or not metadata_path.is_file():
        msg = f"Model version {version!r} is incomplete under {directory}"
        raise FileNotFoundError(msg)

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    recorded_sklearn = metadata.get("library_versions", {}).get("scikit-learn")
    if recorded_sklearn is not None and recorded_sklearn != sklearn.__version__:
        msg = (
            f"scikit-learn version mismatch: metadata has {recorded_sklearn!r}, "
            f"installed {sklearn.__version__!r}"
        )
        raise ValueError(msg)

    pipeline = joblib.load(pipeline_path)
    return pipeline, metadata


def reproduction_baseline_dir(config: dict[str, Any]) -> Path:
    """Directory where reproduction baselines are stored."""
    return Path(config["paths"]["models_dir"]).parent / REPRO_BASELINE_DIRNAME


def save_reproduction_baseline(config_path: Path | str | None = None) -> Path:
    """Copy committed splits and metrics before a full reproduction run.

    Args:
        config_path: Optional path to ``config.yaml``.

    Returns:
        Path to the baseline directory.
    """
    config = load_config(config_path)
    baseline_dir = reproduction_baseline_dir(config)
    if baseline_dir.exists():
        shutil.rmtree(baseline_dir)
    baseline_dir.mkdir(parents=True)

    splits_dir = Path(config["paths"]["splits_dir"])
    reports_dir = Path(config["paths"]["reports_dir"])
    metrics_path = reports_dir / METRICS_FILENAME

    for name in (TRAIN_IDS_CSV, VAL_IDS_CSV, TEST_IDS_CSV):
        shutil.copy2(splits_dir / name, baseline_dir / name)
    shutil.copy2(metrics_path, baseline_dir / METRICS_FILENAME)

    logger.info("Saved reproduction baseline to %s", baseline_dir)
    return baseline_dir


def _files_identical(path_a: Path, path_b: Path) -> bool:
    return path_a.read_bytes() == path_b.read_bytes()


def _collect_numeric_leaves(
    value: Any,
    prefix: str,
    out: dict[str, float],
) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int | float):
        out[prefix or "root"] = float(value)
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            _collect_numeric_leaves(nested, child, out)
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            child = f"{prefix}[{index}]"
            _collect_numeric_leaves(nested, child, out)


def compare_metric_dicts(
    baseline: dict[str, Any],
    current: dict[str, Any],
    tolerance: float = METRIC_COMPARE_TOLERANCE,
) -> list[tuple[str, float, float, float]]:
    """Compare numeric leaves in two metrics JSON structures.

    Returns:
        List of (path, baseline_value, current_value, abs_diff) where abs_diff
        exceeds ``tolerance``. Missing keys in either tree are treated as diffs.
    """
    base_leaves: dict[str, float] = {}
    current_leaves: dict[str, float] = {}
    _collect_numeric_leaves(baseline, "", base_leaves)
    _collect_numeric_leaves(current, "", current_leaves)

    all_keys = sorted(set(base_leaves) | set(current_leaves))
    diffs: list[tuple[str, float, float, float]] = []
    for key in all_keys:
        if key not in base_leaves or key not in current_leaves:
            diffs.append(
                (
                    key,
                    base_leaves.get(key, float("nan")),
                    current_leaves.get(key, float("nan")),
                    float("inf"),
                )
            )
            continue
        diff = abs(base_leaves[key] - current_leaves[key])
        if diff > tolerance:
            diffs.append((key, base_leaves[key], current_leaves[key], diff))
    return diffs


def max_metric_diff(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> tuple[int, float]:
    """Return the number of numeric leaves and the maximum absolute difference."""
    base_leaves: dict[str, float] = {}
    current_leaves: dict[str, float] = {}
    _collect_numeric_leaves(baseline, "", base_leaves)
    _collect_numeric_leaves(current, "", current_leaves)

    all_keys = sorted(set(base_leaves) | set(current_leaves))
    max_diff = 0.0
    for key in all_keys:
        if key not in base_leaves or key not in current_leaves:
            return len(all_keys), float("inf")
        max_diff = max(max_diff, abs(base_leaves[key] - current_leaves[key]))
    return len(all_keys), max_diff


def print_reproduction_summary(
    *,
    splits_ok: bool,
    split_diffs: list[str],
    metrics_ok: bool,
    metric_diffs: list[tuple[str, float, float, float]],
    metric_leaf_count: int,
    max_metric_abs_diff: float,
    tolerance: float,
) -> None:
    """Print a short human-readable reproduction report to stdout."""
    print()
    print("=== Reproduction summary ===")
    print(f"Metric tolerance: {tolerance:g} (absolute difference per numeric value)")

    print("Splits (byte-identical to baseline saved at start of reproduce):")
    if splits_ok:
        for name in (TRAIN_IDS_CSV, VAL_IDS_CSV, TEST_IDS_CSV):
            print(f"  {name}: identical")
    else:
        for name in (TRAIN_IDS_CSV, VAL_IDS_CSV, TEST_IDS_CSV):
            status = "DIFF" if name in split_diffs else "identical"
            print(f"  {name}: {status}")

    print(f"Metrics ({METRICS_FILENAME}): {metric_leaf_count} numeric values compared")
    if max_metric_abs_diff == float("inf"):
        print("  max absolute difference: missing keys between baseline and current")
    else:
        print(f"  max absolute difference: {max_metric_abs_diff:.6g}")

    if splits_ok and metrics_ok:
        print("Result: splits identical, metrics identical")
    else:
        print("Result: REPRODUCTION FAILED")
        if not metrics_ok:
            print("Largest metric diffs (up to 10):")
            sorted_diffs = sorted(metric_diffs, key=lambda row: row[3], reverse=True)
            for path, base_val, cur_val, diff in sorted_diffs[:10]:
                print(f"  {path}: baseline={base_val} current={cur_val} abs_diff={diff}")
            if len(metric_diffs) > 10:
                print(f"  ... and {len(metric_diffs) - 10} more")
    print("============================")
    print()


def compare_reproduction(
    config_path: Path | str | None = None,
    tolerance: float = METRIC_COMPARE_TOLERANCE,
) -> bool:
    """Compare regenerated splits and metrics to the saved baseline.

    Args:
        config_path: Optional path to ``config.yaml``.
        tolerance: Maximum absolute difference treated as equal for metrics.

    Returns:
        True if splits and metrics match within tolerance.

    Raises:
        FileNotFoundError: If baseline files are missing.
    """
    config = load_config(config_path)
    baseline_dir = reproduction_baseline_dir(config)
    if not baseline_dir.is_dir():
        msg = f"Missing reproduction baseline at {baseline_dir}; run --save-baseline first"
        raise FileNotFoundError(msg)

    splits_dir = Path(config["paths"]["splits_dir"])
    reports_dir = Path(config["paths"]["reports_dir"])
    metrics_path = reports_dir / METRICS_FILENAME

    split_diffs: list[str] = []
    for name in (TRAIN_IDS_CSV, VAL_IDS_CSV, TEST_IDS_CSV):
        baseline_file = baseline_dir / name
        current_file = splits_dir / name
        if not baseline_file.is_file():
            msg = f"Baseline split file missing: {baseline_file}"
            raise FileNotFoundError(msg)
        if not _files_identical(baseline_file, current_file):
            split_diffs.append(name)

    baseline_metrics = json.loads((baseline_dir / METRICS_FILENAME).read_text(encoding="utf-8"))
    current_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metric_diffs = compare_metric_dicts(baseline_metrics, current_metrics, tolerance)
    metric_leaf_count, max_metric_abs_diff = max_metric_diff(baseline_metrics, current_metrics)

    splits_ok = len(split_diffs) == 0
    metrics_ok = len(metric_diffs) == 0

    print_reproduction_summary(
        splits_ok=splits_ok,
        split_diffs=split_diffs,
        metrics_ok=metrics_ok,
        metric_diffs=metric_diffs,
        metric_leaf_count=metric_leaf_count,
        max_metric_abs_diff=max_metric_abs_diff,
        tolerance=tolerance,
    )

    return splits_ok and metrics_ok


def main() -> None:
    """CLI entry point for packaging and reproduction checks."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Package models or check reproduction.")
    parser.add_argument(
        "--save-baseline",
        action="store_true",
        help="Copy splits and metrics.json before make reproduce.",
    )
    parser.add_argument(
        "--compare-reproduction",
        action="store_true",
        help="Compare splits and metrics to the saved baseline.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (default: project config).",
    )
    args = parser.parse_args()

    if args.save_baseline:
        save_reproduction_baseline(args.config)
        return
    if args.compare_reproduction:
        ok = compare_reproduction(args.config)
        if not ok:
            sys.exit(1)
        return

    save_model(args.config)


if __name__ == "__main__":
    main()
