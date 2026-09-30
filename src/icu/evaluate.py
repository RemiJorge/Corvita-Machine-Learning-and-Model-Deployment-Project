"""Test-set metrics, bootstrap intervals, calibration, and missing-vitals analysis."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)
from sklearn.pipeline import Pipeline

from icu.config import load_config
from icu.features import FEATURE_COLUMNS, compute_features
from icu.split import TEST_IDS_CSV, TRAIN_IDS_CSV
from icu.tables import ADMISSION_PARQUET, VITALS_PARQUET
from icu.train import (
    HIST_GRADIENT_BOOSTING,
    LOGISTIC_REGRESSION,
    build_hgb_pipeline,
    build_logreg_pipeline,
    load_labeled_features,
    read_record_ids,
    threshold_metrics,
)

logger = logging.getLogger(__name__)

SELECTION_FILENAME = "selection.json"
METRICS_FILENAME = "metrics.json"
MISSING_VITALS_FILENAME = "missing_vitals.json"
SUBGROUPS_FILENAME = "subgroups.json"

ICU_TYPE_CODES: tuple[str, ...] = ("1", "2", "3", "4")

SERVED_MODEL_PR_AUC_MARGIN = 0.01
SERVED_MODEL_RULE = (
    "Higher validation PR-AUC; if the difference is below 0.01, prefer logistic_regression "
    "for calibration, size, speed, and interpretability."
)

BOOTSTRAP_METRIC_NAMES: tuple[str, ...] = (
    "pr_auc",
    "auroc",
    "sensitivity",
    "specificity",
    "precision",
    "brier",
    "alerts_per_100",
)

SUBGROUP_DEFINITIONS: dict[str, str] = {
    "all": "All test records",
    "any_missing_vital": "At least one vital missing in the 24 h window",
    "missing_hr": "No HR measurements in the window",
    "missing_resp_rate": "No RespRate measurements in the window",
    "missing_temp": "No Temp measurements in the window",
    "missing_all_three": "No HR, RespRate, or Temp measurements",
}


def load_selection(path: Path) -> dict[str, Any]:
    """Load and validate the frozen model selection from F6.

    Args:
        path: Path to ``selection.json``.

    Returns:
        Parsed selection dict.

    Raises:
        FileNotFoundError: If ``path`` is missing.
        ValueError: If required model blocks or thresholds are absent.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Selection file not found: {path}")
    selection = json.loads(path.read_text(encoding="utf-8"))
    for model_name in (LOGISTIC_REGRESSION, HIST_GRADIENT_BOOSTING):
        if model_name not in selection:
            msg = f"Selection missing block: {model_name}"
            raise ValueError(msg)
        block = selection[model_name]
        if "selected_params" not in block or "threshold" not in block:
            msg = f"Selection block incomplete for {model_name}"
            raise ValueError(msg)
        if "threshold" not in block["threshold"]:
            msg = f"Selection missing decision threshold for {model_name}"
            raise ValueError(msg)
    return selection


def choose_served_model(selection: dict[str, Any]) -> str:
    """Pick the deployment model using validation metrics only (modeling spec section 8).

    Args:
        selection: Contents of ``selection.json``.

    Returns:
        ``logistic_regression`` or ``hist_gradient_boosting``.
    """
    logreg_pr = float(selection[LOGISTIC_REGRESSION]["validation_metrics"]["val_pr_auc"])
    hgb_pr = float(selection[HIST_GRADIENT_BOOSTING]["validation_metrics"]["val_pr_auc"])
    diff = logreg_pr - hgb_pr
    if diff > SERVED_MODEL_PR_AUC_MARGIN:
        return LOGISTIC_REGRESSION
    if diff < -SERVED_MODEL_PR_AUC_MARGIN:
        return HIST_GRADIENT_BOOSTING
    return LOGISTIC_REGRESSION


def predict_proba(model: Any, features: pd.DataFrame) -> np.ndarray:
    """Return predicted probability of death for each row.

    Args:
        model: Fitted pipeline or ``HistGradientBoostingClassifier``.
        features: Feature matrix with ``FEATURE_COLUMNS``.

    Returns:
        One-dimensional array of probabilities for class 1.
    """
    if isinstance(model, Pipeline):
        return model.predict_proba(features)[:, 1]
    return model.predict_proba(features)[:, 1]


def fit_frozen_models(
    selection: dict[str, Any],
    x_train: pd.DataFrame,
    y_train: np.ndarray,
    seed: int,
) -> tuple[Any, Any]:
    """Refit both models on training data with hyperparameters frozen from selection.

    Args:
        selection: Frozen selection from F6.
        x_train: Training features.
        y_train: Training labels.
        seed: Random seed from config.

    Returns:
        Tuple of (logistic regression pipeline, HGB classifier).
    """
    logreg_params = selection[LOGISTIC_REGRESSION]["selected_params"]
    logreg = build_logreg_pipeline(float(logreg_params["C"]), seed)
    logreg.fit(x_train, y_train)

    hgb_params = selection[HIST_GRADIENT_BOOSTING]["selected_params"]
    hgb = build_hgb_pipeline(
        learning_rate=float(hgb_params["learning_rate"]),
        max_depth=int(hgb_params["max_depth"]),
        min_samples_leaf=int(hgb_params["min_samples_leaf"]),
        max_iter=int(hgb_params["max_iter"]),
        seed=seed,
    )
    hgb.fit(x_train, y_train)
    return logreg, hgb


def _confusion_counts(y_true: np.ndarray, y_proba: np.ndarray, threshold: float) -> dict[str, int]:
    y_pred = (y_proba >= threshold).astype(int)
    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))
    tn = int(np.sum((y_true == 0) & (y_pred == 0)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def compute_metric_bundle(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    threshold: float,
    train_death_rate: float,
) -> dict[str, Any]:
    """Compute test metrics and baselines at a fixed threshold.

    Args:
        y_true: Binary labels.
        y_proba: Predicted probability of class 1.
        threshold: Decision threshold from validation.
        train_death_rate: Mean death rate on the training split (Brier baseline).

    Returns:
        Point metrics, baselines, and confusion matrix counts.
    """
    prevalence = float(np.mean(y_true)) if len(y_true) else 0.0
    at_threshold = threshold_metrics(y_true, y_proba, threshold)
    constant_pred = np.full_like(y_proba, train_death_rate, dtype=float)

    point = {
        "pr_auc": float(average_precision_score(y_true, y_proba)),
        "auroc": float(roc_auc_score(y_true, y_proba)),
        "brier": float(brier_score_loss(y_true, y_proba)),
        **at_threshold,
    }
    baselines = {
        "pr_auc": prevalence,
        "auroc": 0.5,
        "precision": prevalence,
        "brier": float(brier_score_loss(y_true, constant_pred)),
    }
    return {
        "point_metrics": point,
        "baselines": baselines,
        "confusion_matrix": _confusion_counts(y_true, y_proba, threshold),
    }


def _metrics_from_sample(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    threshold: float,
    train_death_rate: float,
) -> dict[str, float]:
    bundle = compute_metric_bundle(y_true, y_proba, threshold, train_death_rate)
    return bundle["point_metrics"]


def bootstrap_intervals(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    threshold: float,
    train_death_rate: float,
    n_resamples: int,
    seed: int,
) -> tuple[dict[str, dict[str, float]], int]:
    """Bootstrap 95 % percentile intervals for test metrics.

    Args:
        y_true: Full test labels.
        y_proba: Full test probabilities.
        threshold: Validation decision threshold.
        train_death_rate: Training death rate for the Brier baseline.
        n_resamples: Number of bootstrap draws.
        seed: Random seed.

    Returns:
        Dict mapping metric name to ``value``, ``ci_low``, ``ci_high``, and count of skipped
        resamples (single class only).
    """
    rng = np.random.default_rng(seed)
    n = len(y_true)
    samples: dict[str, list[float]] = {name: [] for name in BOOTSTRAP_METRIC_NAMES}
    skipped = 0

    for _ in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        y_sample = y_true[idx]
        if len(np.unique(y_sample)) < 2:
            skipped += 1
            continue
        p_sample = y_proba[idx]
        row = _metrics_from_sample(y_sample, p_sample, threshold, train_death_rate)
        for name in BOOTSTRAP_METRIC_NAMES:
            samples[name].append(row[name])

    full = _metrics_from_sample(y_true, y_proba, threshold, train_death_rate)
    intervals: dict[str, dict[str, float]] = {}
    for name in BOOTSTRAP_METRIC_NAMES:
        values = samples[name]
        if values:
            ci_low = float(np.percentile(values, 2.5))
            ci_high = float(np.percentile(values, 97.5))
        else:
            ci_low = full[name]
            ci_high = full[name]
        intervals[name] = {
            "value": full[name],
            "ci_low": ci_low,
            "ci_high": ci_high,
        }
    return intervals, skipped


def paired_bootstrap_diff(
    y_true: np.ndarray,
    proba_logreg: np.ndarray,
    proba_hgb: np.ndarray,
    n_resamples: int,
    seed: int,
) -> dict[str, Any]:
    """Bootstrap intervals for HGB minus logistic regression on PR-AUC and AUROC.

    Args:
        y_true: Test labels.
        proba_logreg: Logistic regression probabilities on the test set.
        proba_hgb: HGB probabilities on the test set.
        n_resamples: Number of bootstrap draws.
        seed: Random seed (offset from the main bootstrap seed).

    Returns:
        Point differences on the full test set and percentile intervals.
    """
    rng = np.random.default_rng(seed + 1)
    n = len(y_true)
    pr_diffs: list[float] = []
    auroc_diffs: list[float] = []
    skipped = 0

    for _ in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        y_sample = y_true[idx]
        if len(np.unique(y_sample)) < 2:
            skipped += 1
            continue
        pl = proba_logreg[idx]
        ph = proba_hgb[idx]
        pr_diffs.append(
            average_precision_score(y_sample, ph) - average_precision_score(y_sample, pl)
        )
        auroc_diffs.append(roc_auc_score(y_sample, ph) - roc_auc_score(y_sample, pl))

    point_pr = float(
        average_precision_score(y_true, proba_hgb) - average_precision_score(y_true, proba_logreg)
    )
    point_auroc = float(roc_auc_score(y_true, proba_hgb) - roc_auc_score(y_true, proba_logreg))

    def _interval(values: list[float], point: float) -> dict[str, float | bool]:
        if values:
            low = float(np.percentile(values, 2.5))
            high = float(np.percentile(values, 97.5))
            contains_zero = low <= 0.0 <= high
        else:
            low = point
            high = point
            contains_zero = point == 0.0
        return {
            "value": point,
            "ci_low": low,
            "ci_high": high,
            "contains_zero": contains_zero,
        }

    return {
        "pr_auc_hgb_minus_logreg": _interval(pr_diffs, point_pr),
        "auroc_hgb_minus_logreg": _interval(auroc_diffs, point_auroc),
        "skipped_resamples": skipped,
    }


def _subgroup_mask(frame: pd.DataFrame, name: str) -> pd.Series:
    if name == "all":
        return pd.Series(True, index=frame.index)
    if name == "any_missing_vital":
        return (
            (frame["hr_missing"] == 1)
            | (frame["resp_rate_missing"] == 1)
            | (frame["temp_missing"] == 1)
        )
    if name == "missing_hr":
        return frame["hr_missing"] == 1
    if name == "missing_resp_rate":
        return frame["resp_rate_missing"] == 1
    if name == "missing_temp":
        return frame["temp_missing"] == 1
    if name == "missing_all_three":
        return (
            (frame["hr_missing"] == 1)
            & (frame["resp_rate_missing"] == 1)
            & (frame["temp_missing"] == 1)
        )
    msg = f"Unknown subgroup: {name}"
    raise ValueError(msg)


def metrics_for_subgroup(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    threshold: float,
    train_death_rate: float,
) -> dict[str, Any] | str:
    """Return metrics for a subgroup or ``too few events`` when counts are too small.

    Args:
        y_true: Labels in the subgroup.
        y_proba: Probabilities in the subgroup.
        threshold: Validation threshold for this model.
        train_death_rate: Training death rate for Brier baseline.

    Returns:
        Metric bundle or the string ``too few events``.
    """
    n_deaths = int(np.sum(y_true == 1))
    n_survivors = int(np.sum(y_true == 0))
    if n_deaths < 10 or n_survivors < 10:
        return "too few events"
    return compute_metric_bundle(y_true, y_proba, threshold, train_death_rate)


def subgroup_analysis(
    test_frame: pd.DataFrame,
    y_test: np.ndarray,
    proba_by_model: dict[str, np.ndarray],
    thresholds: dict[str, float],
    train_death_rate: float,
) -> dict[str, Any]:
    """Natural missing-vital subgroups on the test set for both models.

    Args:
        test_frame: Test rows with feature columns.
        y_test: Test labels aligned with ``test_frame``.
        proba_by_model: Model name to probability array.
        thresholds: Model name to validation threshold.
        train_death_rate: Training death rate.

    Returns:
        JSON-serializable subgroup report.
    """
    report: dict[str, Any] = {}
    for name, description in SUBGROUP_DEFINITIONS.items():
        mask = _subgroup_mask(test_frame, name)
        y_sub = y_test[mask.to_numpy()]
        entry: dict[str, Any] = {
            "description": description,
            "n": int(mask.sum()),
            "n_deaths": int(np.sum(y_sub == 1)),
        }
        models_block: dict[str, Any] = {}
        for model_name, proba in proba_by_model.items():
            p_sub = proba[mask.to_numpy()]
            models_block[model_name] = metrics_for_subgroup(
                y_sub, p_sub, thresholds[model_name], train_death_rate
            )
        entry["models"] = models_block
        report[name] = entry
    return report


def _icu_type_mask(frame: pd.DataFrame, icu_type: str) -> pd.Series:
    """True for rows whose admission ICUType matches ``icu_type`` (1 to 4)."""
    col = f"icu_type_{icu_type}"
    if col not in frame.columns:
        msg = f"Missing ICU type column: {col}"
        raise ValueError(msg)
    return frame[col] == 1


def subgroup_model_block(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    threshold: float,
    train_death_rate: float,
    n_resamples: int,
    seed: int,
) -> dict[str, Any] | str:
    """Subgroup metrics with bootstrap intervals, or ``too few events`` when counts are small.

    Args:
        y_true: Labels in the subgroup.
        y_proba: Probabilities in the subgroup.
        threshold: Validation threshold for this model.
        train_death_rate: Training death rate for Brier baseline.
        n_resamples: Bootstrap resample count.
        seed: Random seed for bootstrap draws.

    Returns:
        Mean predicted probability, point metrics, and bootstrap CIs, or ``too few events``.
    """
    mean_predicted_probability = float(np.mean(y_proba))
    bundle = metrics_for_subgroup(y_true, y_proba, threshold, train_death_rate)
    if bundle == "too few events":
        return {
            "mean_predicted_probability": mean_predicted_probability,
            "metrics": "too few events",
        }
    bootstrap, skipped = bootstrap_intervals(
        y_true, y_proba, threshold, train_death_rate, n_resamples, seed
    )
    for name in BOOTSTRAP_METRIC_NAMES:
        bootstrap[name]["baseline"] = bundle["baselines"].get(name)
    return {
        "mean_predicted_probability": mean_predicted_probability,
        "point_metrics": bundle["point_metrics"],
        "baselines": bundle["baselines"],
        "confusion_matrix": bundle["confusion_matrix"],
        "bootstrap": bootstrap,
        "bootstrap_skipped_resamples": skipped,
    }


def icu_type_subgroup_analysis(
    test_frame: pd.DataFrame,
    y_test: np.ndarray,
    proba_by_model: dict[str, np.ndarray],
    thresholds: dict[str, float],
    train_death_rate: float,
    n_resamples: int,
    seed: int,
) -> dict[str, Any]:
    """ICUType 1 to 4 subgroups on the test set for both models.

    Args:
        test_frame: Test rows with feature columns (including ``icu_type_*``).
        y_test: Test labels aligned with ``test_frame``.
        proba_by_model: Model name to probability array.
        thresholds: Model name to validation threshold.
        train_death_rate: Training death rate.
        n_resamples: Bootstrap resample count from config.
        seed: Base random seed (offsets per ICU type and model).

    Returns:
        JSON-serializable report keyed by ICU type code ``"1"`` through ``"4"``.
    """
    report: dict[str, Any] = {}
    for type_idx, code in enumerate(ICU_TYPE_CODES):
        mask = _icu_type_mask(test_frame, code)
        y_sub = y_test[mask.to_numpy()]
        n = int(mask.sum())
        n_deaths = int(np.sum(y_sub == 1))
        entry: dict[str, Any] = {
            "description": f"ICUType {code}",
            "n": n,
            "n_deaths": n_deaths,
            "observed_death_rate": float(n_deaths / n) if n else 0.0,
            "models": {},
        }
        for model_idx, (model_name, proba) in enumerate(proba_by_model.items()):
            p_sub = proba[mask.to_numpy()]
            block_seed = seed + 1000 * (type_idx + 1) + 10 * (model_idx + 1)
            entry["models"][model_name] = subgroup_model_block(
                y_sub,
                p_sub,
                thresholds[model_name],
                train_death_rate,
                n_resamples,
                block_seed,
            )
        report[code] = entry
    return report


def ablation_analysis(
    config: dict[str, Any],
    test_ids: list[int],
    models: dict[str, Any],
    y_test: np.ndarray,
    thresholds: dict[str, float],
    train_death_rate: float,
    full_metrics: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Drop vitals on test records, recompute features, and score both models.

    Args:
        config: Project configuration.
        test_ids: Held-out record IDs.
        models: Fitted models by name.
        y_test: Test labels (same order as ``test_ids`` after sort).
        thresholds: Validation thresholds by model.
        train_death_rate: Training death rate.
        full_metrics: Point metrics on the unmodified test set per model.

    Returns:
        Ablation results with deltas versus the full test set.
    """
    processed_dir = Path(config["paths"]["processed_dir"])
    admission = pd.read_parquet(processed_dir / ADMISSION_PARQUET)
    vitals = pd.read_parquet(processed_dir / VITALS_PARQUET)
    test_id_set = set(test_ids)
    admission = admission.loc[admission["record_id"].isin(test_id_set)].sort_values("record_id")
    vitals = vitals.loc[vitals["record_id"].isin(test_id_set)]

    vital_params: list[str] = list(config["vitals"])
    ablation_cases: dict[str, list[str]] = {
        "HR": ["HR"],
        "RespRate": ["RespRate"],
        "Temp": ["Temp"],
        "all_three": vital_params,
    }

    report: dict[str, Any] = {}
    for case_name, drop_params in ablation_cases.items():
        vitals_ablated = vitals.loc[~vitals["parameter"].isin(drop_params)]
        features = compute_features(admission, vitals_ablated)
        features = features.reset_index(drop=True)
        case_entry: dict[str, Any] = {}
        for model_name, model in models.items():
            proba = predict_proba(model, features)
            bundle = compute_metric_bundle(y_test, proba, thresholds[model_name], train_death_rate)
            delta = {
                metric: bundle["point_metrics"][metric] - full_metrics[model_name][metric]
                for metric in ("pr_auc", "auroc", "brier", "sensitivity", "specificity")
            }
            case_entry[model_name] = {
                "metrics": bundle,
                "delta_vs_full": delta,
            }
        report[case_name] = case_entry
    return report


def write_figures(
    y_test: np.ndarray,
    proba_by_model: dict[str, np.ndarray],
    figures_dir: Path,
    calibration_bins: int,
) -> None:
    """Write ROC, PR, and calibration figures for the test set.

    Args:
        y_test: Test labels.
        proba_by_model: Model name to test probabilities.
        figures_dir: Output directory.
        calibration_bins: Number of bins for ``calibration_curve``.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures_dir.mkdir(parents=True, exist_ok=True)
    n = len(y_test)
    deaths = int(np.sum(y_test == 1))
    title_suffix = f"Test set (n={n}, deaths={deaths})"
    prevalence = float(np.mean(y_test))

    # ROC
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot([0, 1], [0, 1], linestyle="--", color="0.5", label="AUROC baseline 0.5")
    for model_name, proba in proba_by_model.items():
        fpr, tpr, _ = roc_curve(y_test, proba)
        ax.plot(fpr, tpr, label=model_name)
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.set_title(f"ROC: {title_suffix}")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(figures_dir / "roc.png", dpi=150)
    plt.close(fig)

    # Precision-recall
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.axhline(prevalence, linestyle="--", color="0.5", label=f"Prevalence {prevalence:.3f}")
    for model_name, proba in proba_by_model.items():
        precision, recall, _ = precision_recall_curve(y_test, proba)
        ax.plot(recall, precision, label=model_name)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title(f"Precision-recall: {title_suffix}")
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(figures_dir / "pr.png", dpi=150)
    plt.close(fig)

    # Calibration
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot([0, 1], [0, 1], linestyle="--", color="0.5", label="Perfect calibration")
    for model_name, proba in proba_by_model.items():
        prob_true, prob_pred = calibration_curve(
            y_test, proba, n_bins=calibration_bins, strategy="quantile"
        )
        ax.plot(prob_pred, prob_true, marker="o", label=model_name)
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Fraction of positives")
    ax.set_title(f"Calibration: {title_suffix}")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(figures_dir / "calibration.png", dpi=150)
    plt.close(fig)


def evaluate_model_block(
    y_test: np.ndarray,
    y_proba: np.ndarray,
    threshold: float,
    train_death_rate: float,
    n_resamples: int,
    seed: int,
) -> dict[str, Any]:
    """Full metric block for one model on the test set.

    Args:
        y_test: Test labels.
        y_proba: Test probabilities.
        threshold: Frozen validation threshold.
        train_death_rate: Training death rate.
        n_resamples: Bootstrap resample count.
        seed: Random seed.

    Returns:
        Threshold, point metrics, baselines, confusion matrix, and bootstrap CIs.
    """
    bundle = compute_metric_bundle(y_test, y_proba, threshold, train_death_rate)
    bootstrap, skipped = bootstrap_intervals(
        y_test, y_proba, threshold, train_death_rate, n_resamples, seed
    )
    for name in BOOTSTRAP_METRIC_NAMES:
        bootstrap[name]["baseline"] = bundle["baselines"].get(name)
    return {
        "threshold": threshold,
        "point_metrics": bundle["point_metrics"],
        "baselines": bundle["baselines"],
        "confusion_matrix": bundle["confusion_matrix"],
        "bootstrap": bootstrap,
        "bootstrap_skipped_resamples": skipped,
    }


def main(config_path: Path | str | None = None) -> None:
    """Score the test set once and write evaluation reports."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = load_config(config_path)
    seed = int(config["seed"])
    splits_dir = Path(config["paths"]["splits_dir"])
    reports_dir = Path(config["paths"]["reports_dir"])
    n_resamples = int(config["evaluation"]["bootstrap_resamples"])
    calibration_bins = int(config["evaluation"]["calibration_bins"])

    selection_path = reports_dir / SELECTION_FILENAME
    selection = load_selection(selection_path)
    served = choose_served_model(selection)
    logger.info("Served model (validation rule): %s", served)

    train_ids = read_record_ids(splits_dir / TRAIN_IDS_CSV)
    test_ids = read_record_ids(splits_dir / TEST_IDS_CSV)
    labeled = load_labeled_features(config)

    train_mask = labeled["record_id"].isin(train_ids)
    test_mask = labeled["record_id"].isin(test_ids)
    test_frame = labeled.loc[test_mask].sort_values("record_id").reset_index(drop=True)

    x_train = labeled.loc[train_mask, FEATURE_COLUMNS]
    y_train = labeled.loc[train_mask, "in_hospital_death"].astype(int).to_numpy()
    x_test = test_frame[FEATURE_COLUMNS]
    y_test = test_frame["in_hospital_death"].astype(int).to_numpy()

    if len(x_train) != len(train_ids) or len(test_frame) != len(test_ids):
        msg = "Split IDs do not match labeled feature rows"
        raise ValueError(msg)

    train_death_rate = float(np.mean(y_train))
    logreg_model, hgb_model = fit_frozen_models(selection, x_train, y_train, seed)
    models = {
        LOGISTIC_REGRESSION: logreg_model,
        HIST_GRADIENT_BOOSTING: hgb_model,
    }

    thresholds = {
        LOGISTIC_REGRESSION: float(selection[LOGISTIC_REGRESSION]["threshold"]["threshold"]),
        HIST_GRADIENT_BOOSTING: float(selection[HIST_GRADIENT_BOOSTING]["threshold"]["threshold"]),
    }

    proba_by_model = {name: predict_proba(model, x_test) for name, model in models.items()}

    model_blocks: dict[str, Any] = {}
    skipped_total = 0
    for idx, model_name in enumerate((LOGISTIC_REGRESSION, HIST_GRADIENT_BOOSTING)):
        block = evaluate_model_block(
            y_test,
            proba_by_model[model_name],
            thresholds[model_name],
            train_death_rate,
            n_resamples,
            seed + 10 * (idx + 1),
        )
        skipped_total += block.pop("bootstrap_skipped_resamples")
        model_blocks[model_name] = block

    paired = paired_bootstrap_diff(
        y_test,
        proba_by_model[LOGISTIC_REGRESSION],
        proba_by_model[HIST_GRADIENT_BOOSTING],
        n_resamples,
        seed,
    )

    metrics_doc: dict[str, Any] = {
        "test_n": len(y_test),
        "test_deaths": int(np.sum(y_test == 1)),
        "train_death_rate": train_death_rate,
        "served_model": served,
        "served_model_rule": SERVED_MODEL_RULE,
        "bootstrap_skipped_resamples": skipped_total,
        "paired_bootstrap": paired,
        LOGISTIC_REGRESSION: model_blocks[LOGISTIC_REGRESSION],
        HIST_GRADIENT_BOOSTING: model_blocks[HIST_GRADIENT_BOOSTING],
    }

    metrics_path = reports_dir / METRICS_FILENAME
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics_doc, indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote %s", metrics_path)

    missing_vitals_doc = {
        "subgroups": subgroup_analysis(
            test_frame,
            y_test,
            proba_by_model,
            thresholds,
            train_death_rate,
        ),
        "ablation": ablation_analysis(
            config,
            test_ids,
            models,
            y_test,
            thresholds,
            train_death_rate,
            {
                LOGISTIC_REGRESSION: model_blocks[LOGISTIC_REGRESSION]["point_metrics"],
                HIST_GRADIENT_BOOSTING: model_blocks[HIST_GRADIENT_BOOSTING]["point_metrics"],
            },
        ),
    }
    missing_path = reports_dir / MISSING_VITALS_FILENAME
    missing_path.write_text(json.dumps(missing_vitals_doc, indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote %s", missing_path)

    subgroups_doc = {
        "icu_type": icu_type_subgroup_analysis(
            test_frame,
            y_test,
            proba_by_model,
            thresholds,
            train_death_rate,
            n_resamples,
            seed,
        ),
    }
    subgroups_path = reports_dir / SUBGROUPS_FILENAME
    subgroups_path.write_text(json.dumps(subgroups_doc, indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote %s", subgroups_path)

    write_figures(
        y_test,
        proba_by_model,
        reports_dir / "figures",
        calibration_bins,
    )
    logger.info("Wrote figures under %s", reports_dir / "figures")


if __name__ == "__main__":
    main()
