"""Train logistic regression and HGB models; tune on validation and set the threshold."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import ParameterGrid
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from icu.config import load_config
from icu.features import FEATURE_COLUMNS, FEATURES_PARQUET
from icu.split import TRAIN_IDS_CSV, VAL_IDS_CSV
from icu.tables import ADMISSION_PARQUET

logger = logging.getLogger(__name__)

LOGISTIC_REGRESSION = "logistic_regression"
HIST_GRADIENT_BOOSTING = "hist_gradient_boosting"

CONTINUOUS_COLUMNS: list[str] = [
    "age",
    "gender_male",
    "hr_mean",
    "hr_last",
    "resp_rate_mean",
    "resp_rate_last",
    "temp_mean",
    "temp_last",
]

COUNT_COLUMNS: list[str] = [
    "hr_count",
    "resp_rate_count",
    "temp_count",
]

PASSTHROUGH_COLUMNS: list[str] = [
    "gender_missing",
    "icu_type_1",
    "icu_type_2",
    "icu_type_3",
    "icu_type_4",
    "hr_missing",
    "resp_rate_missing",
    "temp_missing",
]

PR_AUC_TIE_TOLERANCE = 0.005


def read_record_ids(path: Path) -> list[int]:
    """Load record IDs from a one-column CSV file.

    Args:
        path: CSV with column ``record_id``.

    Returns:
        Sorted list of integer IDs as stored in the file.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """
    frame = pd.read_csv(path)
    return frame["record_id"].astype(int).tolist()


def load_labeled_features(config: dict[str, Any]) -> pd.DataFrame:
    """Join feature matrix with in-hospital death labels.

    Args:
        config: Loaded project configuration.

    Returns:
        DataFrame with ``record_id``, feature columns, and ``in_hospital_death``.

    Raises:
        FileNotFoundError: If required parquet files are missing.
    """
    processed_dir = Path(config["paths"]["processed_dir"])
    features_path = processed_dir / FEATURES_PARQUET
    admission_path = processed_dir / ADMISSION_PARQUET
    if not features_path.is_file():
        raise FileNotFoundError(f"Features not found: {features_path}")
    if not admission_path.is_file():
        raise FileNotFoundError(f"Admission table not found: {admission_path}")

    features = pd.read_parquet(features_path)
    labels = pd.read_parquet(admission_path, columns=["record_id", "in_hospital_death"])
    merged = features.merge(labels, on="record_id", how="inner")
    if len(merged) != len(features):
        msg = "Feature rows and admission labels do not align one-to-one"
        raise ValueError(msg)
    return merged


def build_logreg_pipeline(c_strength: float, seed: int) -> Pipeline:
    """Build the logistic regression pipeline with median imputation and scaling.

    Args:
        c_strength: Inverse regularization strength (sklearn ``C``).
        seed: Random seed for the solver.

    Returns:
        Fitted-ready scikit-learn ``Pipeline``.
    """
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "continuous",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler()),
                    ]
                ),
                CONTINUOUS_COLUMNS,
            ),
            ("counts", StandardScaler(), COUNT_COLUMNS),
            ("binary", "passthrough", PASSTHROUGH_COLUMNS),
        ]
    )
    classifier = LogisticRegression(C=c_strength, max_iter=2000, random_state=seed)
    return Pipeline([("preprocessor", preprocessor), ("classifier", classifier)])


def build_hgb_pipeline(
    learning_rate: float,
    max_depth: int,
    min_samples_leaf: int,
    max_iter: int,
    seed: int,
) -> HistGradientBoostingClassifier:
    """Build a histogram gradient boosting classifier (no imputation pipeline).

    Args:
        learning_rate: Learning rate hyperparameter.
        max_depth: Maximum tree depth.
        min_samples_leaf: Minimum samples per leaf.
        max_iter: Maximum boosting iterations.
        seed: Random seed.

    Returns:
        Unfitted ``HistGradientBoostingClassifier``.
    """
    return HistGradientBoostingClassifier(
        learning_rate=learning_rate,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        max_iter=max_iter,
        early_stopping=False,
        random_state=seed,
    )


def score_validation(y_true: np.ndarray, y_proba: np.ndarray) -> dict[str, float]:
    """Compute validation ranking and calibration metrics.

    Args:
        y_true: Binary labels (0/1).
        y_proba: Predicted probability of class 1.

    Returns:
        Dict with ``val_pr_auc``, ``val_auroc``, and ``val_brier``.
    """
    return {
        "val_pr_auc": float(average_precision_score(y_true, y_proba)),
        "val_auroc": float(roc_auc_score(y_true, y_proba)),
        "val_brier": float(brier_score_loss(y_true, y_proba)),
    }


def _simplicity_key(row: dict[str, Any], model_name: str) -> tuple[float, ...]:
    if model_name == LOGISTIC_REGRESSION:
        return (float(row["C"]),)
    return (float(row["max_iter"]), float(row["max_depth"]))


def select_candidate(rows: list[dict[str, Any]], model_name: str) -> dict[str, Any]:
    """Pick the best grid row using validation PR-AUC, Brier, and simplicity tie-breaks.

    Args:
        rows: Tuning rows for one model (non-empty).
        model_name: ``logistic_regression`` or ``hist_gradient_boosting``.

    Returns:
        The selected tuning row.

    Raises:
        ValueError: If ``rows`` is empty.
    """
    if not rows:
        msg = "Cannot select from an empty candidate list"
        raise ValueError(msg)

    best_pr = max(row["val_pr_auc"] for row in rows)
    pool = [row for row in rows if row["val_pr_auc"] >= best_pr - PR_AUC_TIE_TOLERANCE]
    best_brier = min(row["val_brier"] for row in pool)
    pool = [row for row in pool if row["val_brier"] == best_brier]
    return min(pool, key=lambda row: _simplicity_key(row, model_name))


def threshold_at_target_sensitivity(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    target_sensitivity: float,
) -> float:
    """Return the highest threshold whose sensitivity is at least the target.

    Args:
        y_true: Binary labels.
        y_proba: Predicted probability of class 1.
        target_sensitivity: Minimum recall for the positive class (e.g. 0.80).

    Returns:
        Decision threshold in [0, 1].

    Raises:
        ValueError: If no threshold meets the target (e.g. no positive labels).
    """
    fpr, tpr, thresholds = roc_curve(y_true, y_proba)
    if len(thresholds) == 0:
        msg = "roc_curve produced no thresholds"
        raise ValueError(msg)
    # Each threshold pairs with the TPR at the same ROC index (sklearn convention).
    sensitivities = tpr[: len(thresholds)]

    qualifying = thresholds[sensitivities >= target_sensitivity]
    if qualifying.size == 0:
        msg = f"No threshold reaches target sensitivity {target_sensitivity}"
        raise ValueError(msg)
    return float(np.max(qualifying))


def youden_threshold(y_true: np.ndarray, y_proba: np.ndarray) -> float:
    """Threshold that maximizes sensitivity plus specificity minus one (Youden index).

    Args:
        y_true: Binary labels.
        y_proba: Predicted probability of class 1.

    Returns:
        Decision threshold from the ROC curve.
    """
    fpr, tpr, thresholds = roc_curve(y_true, y_proba)
    if len(thresholds) == 0:
        return 0.5
    youden = tpr - fpr
    idx = int(np.argmax(youden))
    if idx >= len(thresholds):
        idx = len(thresholds) - 1
    return float(thresholds[idx])


def threshold_metrics(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    threshold: float,
) -> dict[str, float]:
    """Binary metrics at a fixed probability threshold.

    Args:
        y_true: Binary labels.
        y_proba: Predicted probability of class 1.
        threshold: Decision threshold.

    Returns:
        Sensitivity, specificity, precision, and alerts per 100 patients.
    """
    y_pred = (y_proba >= threshold).astype(int)
    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))
    tn = int(np.sum((y_true == 0) & (y_pred == 0)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))

    sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    precision = float(precision_score(y_true, y_pred, zero_division=0.0))
    alerts_per_100 = float(np.mean(y_pred) * 100.0)

    return {
        "sensitivity": float(sensitivity),
        "specificity": float(specificity),
        "precision": precision,
        "alerts_per_100": alerts_per_100,
    }


def tune_on_grid(
    model_name: str,
    x_train: pd.DataFrame,
    y_train: np.ndarray,
    x_val: pd.DataFrame,
    y_val: np.ndarray,
    param_grid: dict[str, list[Any]],
    build_fn: Callable[..., Any],
    seed: int,
) -> list[dict[str, Any]]:
    """Fit every grid combination on train and score on validation.

    Args:
        model_name: Name written to each tuning row.
        x_train: Training features (``FEATURE_COLUMNS`` only).
        y_train: Training labels.
        x_val: Validation features.
        y_val: Validation labels.
        param_grid: Hyperparameter grid for ``ParameterGrid``.
        build_fn: Callable that accepts grid params plus ``seed`` and returns an estimator.
        seed: Random seed passed to ``build_fn``.

    Returns:
        One dict per grid point, including metrics and ``fit_seconds``.
    """
    rows: list[dict[str, Any]] = []
    for params in ParameterGrid(param_grid):
        estimator = build_fn(**params, seed=seed)
        start = time.perf_counter()
        estimator.fit(x_train, y_train)
        fit_seconds = time.perf_counter() - start
        y_proba = estimator.predict_proba(x_val)[:, 1]
        metrics = score_validation(y_val, y_proba)
        row = {"model": model_name, **params, **metrics, "fit_seconds": fit_seconds}
        rows.append(row)
    return rows


def _fit_selected_logreg(
    c_strength: float,
    seed: int,
    x_train: pd.DataFrame,
    y_train: np.ndarray,
) -> Pipeline:
    pipeline = build_logreg_pipeline(c_strength, seed)
    pipeline.fit(x_train, y_train)
    return pipeline


def _fit_selected_hgb(
    params: dict[str, Any],
    seed: int,
    x_train: pd.DataFrame,
    y_train: np.ndarray,
) -> HistGradientBoostingClassifier:
    model = build_hgb_pipeline(
        learning_rate=float(params["learning_rate"]),
        max_depth=int(params["max_depth"]),
        min_samples_leaf=int(params["min_samples_leaf"]),
        max_iter=int(params["max_iter"]),
        seed=seed,
    )
    model.fit(x_train, y_train)
    return model


def _predict_proba(model: Any, features: pd.DataFrame) -> np.ndarray:
    if isinstance(model, Pipeline):
        return model.predict_proba(features)[:, 1]
    return model.predict_proba(features)[:, 1]


def _selection_block(
    model_name: str,
    rows: list[dict[str, Any]],
    x_train: pd.DataFrame,
    y_train: np.ndarray,
    x_val: pd.DataFrame,
    y_val: np.ndarray,
    target_sensitivity: float,
    seed: int,
) -> dict[str, Any]:
    selected_row = select_candidate(rows, model_name)
    param_keys = [
        k
        for k in selected_row
        if k
        not in {
            "model",
            "val_pr_auc",
            "val_auroc",
            "val_brier",
            "fit_seconds",
        }
    ]
    selected_params = {k: selected_row[k] for k in param_keys}

    if model_name == LOGISTIC_REGRESSION:
        model = _fit_selected_logreg(float(selected_params["C"]), seed, x_train, y_train)
    else:
        model = _fit_selected_hgb(selected_params, seed, x_train, y_train)

    y_proba = _predict_proba(model, x_val)
    threshold = threshold_at_target_sensitivity(y_val, y_proba, target_sensitivity)
    at_threshold = threshold_metrics(y_val, y_proba, threshold)
    youden = youden_threshold(y_val, y_proba)
    at_youden = threshold_metrics(y_val, y_proba, youden)

    return {
        "selected_params": selected_params,
        "validation_metrics": {
            "val_pr_auc": selected_row["val_pr_auc"],
            "val_auroc": selected_row["val_auroc"],
            "val_brier": selected_row["val_brier"],
        },
        "threshold": {
            "threshold": threshold,
            **at_threshold,
            "youden_threshold": youden,
            "youden_sensitivity": at_youden["sensitivity"],
            "youden_specificity": at_youden["specificity"],
            "youden_precision": at_youden["precision"],
            "youden_alerts_per_100": at_youden["alerts_per_100"],
        },
        "candidates": rows,
    }


def write_tuning_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write all tuning rows to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(path, index=False)


def main(config_path: Path | str | None = None) -> None:
    """Tune both models on validation and write tuning and selection reports."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = load_config(config_path)
    seed = int(config["seed"])
    splits_dir = Path(config["paths"]["splits_dir"])
    reports_dir = Path(config["paths"]["reports_dir"])
    target_sensitivity = float(config["threshold"]["target_sensitivity"])

    train_ids = read_record_ids(splits_dir / TRAIN_IDS_CSV)
    val_ids = read_record_ids(splits_dir / VAL_IDS_CSV)

    labeled = load_labeled_features(config)
    train_mask = labeled["record_id"].isin(train_ids)
    val_mask = labeled["record_id"].isin(val_ids)

    x_train = labeled.loc[train_mask, FEATURE_COLUMNS]
    y_train = labeled.loc[train_mask, "in_hospital_death"].astype(int).to_numpy()
    x_val = labeled.loc[val_mask, FEATURE_COLUMNS]
    y_val = labeled.loc[val_mask, "in_hospital_death"].astype(int).to_numpy()

    if len(x_train) != len(train_ids) or len(x_val) != len(val_ids):
        msg = "Split IDs do not match labeled feature rows"
        raise ValueError(msg)

    def _logreg_tune_fn(c_regularization: float, seed: int) -> Pipeline:
        return build_logreg_pipeline(c_regularization, seed)

    logreg_grid = {
        "c_regularization": config["models"]["logreg"]["C"],
    }

    logreg_rows = tune_on_grid(
        LOGISTIC_REGRESSION,
        x_train,
        y_train,
        x_val,
        y_val,
        logreg_grid,
        _logreg_tune_fn,
        seed,
    )
    for row in logreg_rows:
        row["C"] = row.pop("c_regularization")

    hgb_rows = tune_on_grid(
        HIST_GRADIENT_BOOSTING,
        x_train,
        y_train,
        x_val,
        y_val,
        config["models"]["hgb"],
        lambda learning_rate, max_depth, min_samples_leaf, max_iter, seed: build_hgb_pipeline(
            learning_rate,
            max_depth,
            min_samples_leaf,
            max_iter,
            seed,
        ),
        seed,
    )

    all_rows = logreg_rows + hgb_rows
    tuning_path = reports_dir / "tuning.csv"
    write_tuning_csv(tuning_path, all_rows)
    logger.info("Wrote %s (%s rows)", tuning_path, len(all_rows))

    selection = {
        "target_sensitivity": target_sensitivity,
        LOGISTIC_REGRESSION: _selection_block(
            LOGISTIC_REGRESSION,
            logreg_rows,
            x_train,
            y_train,
            x_val,
            y_val,
            target_sensitivity,
            seed,
        ),
        HIST_GRADIENT_BOOSTING: _selection_block(
            HIST_GRADIENT_BOOSTING,
            hgb_rows,
            x_train,
            y_train,
            x_val,
            y_val,
            target_sensitivity,
            seed,
        ),
    }
    selection_path = reports_dir / "selection.json"
    selection_path.parent.mkdir(parents=True, exist_ok=True)
    selection_path.write_text(json.dumps(selection, indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote %s", selection_path)

    for name in (LOGISTIC_REGRESSION, HIST_GRADIENT_BOOSTING):
        block = selection[name]
        logger.info(
            "%s: pr_auc=%.4f threshold=%.4f sens=%.4f spec=%.4f alerts_per_100=%.2f",
            name,
            block["validation_metrics"]["val_pr_auc"],
            block["threshold"]["threshold"],
            block["threshold"]["sensitivity"],
            block["threshold"]["specificity"],
            block["threshold"]["alerts_per_100"],
        )


if __name__ == "__main__":
    main()
