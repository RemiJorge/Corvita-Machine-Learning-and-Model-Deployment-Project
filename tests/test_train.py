"""Tests for model training, tuning selection, and thresholds (F6)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from icu.features import FEATURE_COLUMNS
from icu.train import (
    CONTINUOUS_COLUMNS,
    HIST_GRADIENT_BOOSTING,
    LOGISTIC_REGRESSION,
    build_logreg_pipeline,
    select_candidate,
    threshold_at_target_sensitivity,
)

TRAIN_SOURCE = Path(__file__).resolve().parents[1] / "src" / "icu" / "train.py"


def _synthetic_feature_frame(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    data: dict[str, list[float | int]] = {}
    for col in FEATURE_COLUMNS:
        if col.endswith("_missing") or col.startswith("icu_type_"):
            data[col] = rng.integers(0, 2, size=n).tolist()
        elif col.endswith("_count"):
            data[col] = rng.integers(0, 50, size=n).tolist()
        else:
            values = rng.normal(size=n)
            if col == "age":
                values = rng.uniform(20, 90, size=n)
            data[col] = values.tolist()
    return pd.DataFrame(data)


def test_preprocessing_fitted_on_train_only() -> None:
    """Imputer medians equal training medians, not validation."""
    train_x = _synthetic_feature_frame(80, seed=1)
    val_x = _synthetic_feature_frame(20, seed=2)
    y_train = np.zeros(80, dtype=int)
    y_train[:12] = 1

    pipeline = build_logreg_pipeline(c_strength=1.0, seed=42)
    pipeline.fit(train_x, y_train)

    preprocessor = pipeline.named_steps["preprocessor"]
    continuous_pipe = preprocessor.named_transformers_["continuous"]
    imputer = continuous_pipe.named_steps["imputer"]
    train_medians = train_x[CONTINUOUS_COLUMNS].median().to_numpy()
    np.testing.assert_allclose(imputer.statistics_, train_medians, rtol=1e-10, atol=1e-10)

    val_medians = val_x[CONTINUOUS_COLUMNS].median().to_numpy()
    assert not np.allclose(imputer.statistics_, val_medians)


def test_threshold_meets_target() -> None:
    """Chosen threshold reaches target sensitivity and is the highest that does."""
    y = np.array([0, 0, 1, 1, 1], dtype=int)
    proba = np.array([0.1, 0.4, 0.5, 0.7, 0.9])
    target = 0.8

    threshold = threshold_at_target_sensitivity(y, proba, target)
    assert threshold == 0.5
    predicted = proba >= threshold
    sensitivity = np.sum((y == 1) & predicted) / np.sum(y == 1)
    assert sensitivity >= target

    slightly_lower_target = threshold_at_target_sensitivity(y, proba, 0.67)
    assert slightly_lower_target >= threshold


def test_train_module_does_not_reference_test_split() -> None:
    """Training code must not load or name the held-out test split."""
    source = TRAIN_SOURCE.read_text(encoding="utf-8")
    assert "test_ids" not in source


def test_select_candidate_prefers_higher_pr_auc() -> None:
    rows = [
        {
            "model": LOGISTIC_REGRESSION,
            "C": 0.1,
            "val_pr_auc": 0.40,
            "val_brier": 0.20,
            "fit_seconds": 1.0,
        },
        {
            "model": LOGISTIC_REGRESSION,
            "C": 1.0,
            "val_pr_auc": 0.45,
            "val_brier": 0.22,
            "fit_seconds": 1.0,
        },
    ]
    chosen = select_candidate(rows, LOGISTIC_REGRESSION)
    assert chosen["C"] == 1.0


def test_select_candidate_tie_break_brier_and_simplicity() -> None:
    rows = [
        {
            "model": LOGISTIC_REGRESSION,
            "C": 10.0,
            "val_pr_auc": 0.50,
            "val_brier": 0.18,
            "fit_seconds": 1.0,
        },
        {
            "model": LOGISTIC_REGRESSION,
            "C": 0.1,
            "val_pr_auc": 0.498,
            "val_brier": 0.18,
            "fit_seconds": 1.0,
        },
        {
            "model": LOGISTIC_REGRESSION,
            "C": 1.0,
            "val_pr_auc": 0.497,
            "val_brier": 0.17,
            "fit_seconds": 1.0,
        },
    ]
    chosen = select_candidate(rows, LOGISTIC_REGRESSION)
    assert chosen["C"] == 1.0

    hgb_rows = [
        {
            "model": HIST_GRADIENT_BOOSTING,
            "learning_rate": 0.1,
            "max_depth": 3,
            "min_samples_leaf": 20,
            "max_iter": 300,
            "val_pr_auc": 0.55,
            "val_brier": 0.15,
            "fit_seconds": 2.0,
        },
        {
            "model": HIST_GRADIENT_BOOSTING,
            "learning_rate": 0.1,
            "max_depth": 2,
            "min_samples_leaf": 20,
            "max_iter": 100,
            "val_pr_auc": 0.548,
            "val_brier": 0.15,
            "fit_seconds": 1.0,
        },
    ]
    hgb_chosen = select_candidate(hgb_rows, HIST_GRADIENT_BOOSTING)
    assert hgb_chosen["max_iter"] == 100
    assert hgb_chosen["max_depth"] == 2
