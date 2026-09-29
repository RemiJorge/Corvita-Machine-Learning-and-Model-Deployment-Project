"""Tests for test-set evaluation, bootstrap intervals, and served-model choice (F7)."""

from __future__ import annotations

import numpy as np

from icu.evaluate import bootstrap_intervals, choose_served_model
from icu.train import HIST_GRADIENT_BOOSTING, LOGISTIC_REGRESSION


def test_bootstrap_deterministic() -> None:
    """Same seed and data yield identical bootstrap intervals."""
    rng = np.random.default_rng(99)
    y = rng.integers(0, 2, size=40)
    proba = rng.uniform(0.05, 0.95, size=40)
    threshold = 0.4
    train_rate = 0.14
    n_resamples = 200
    seed = 42

    first, skipped_a = bootstrap_intervals(y, proba, threshold, train_rate, n_resamples, seed)
    second, skipped_b = bootstrap_intervals(y, proba, threshold, train_rate, n_resamples, seed)
    assert skipped_a == skipped_b
    for name in first:
        assert first[name]["ci_low"] == second[name]["ci_low"]
        assert first[name]["ci_high"] == second[name]["ci_high"]


def test_choose_served_model_logreg_clear_win() -> None:
    """Higher validation PR-AUC for logistic regression selects it."""
    selection = {
        LOGISTIC_REGRESSION: {"validation_metrics": {"val_pr_auc": 0.40}},
        HIST_GRADIENT_BOOSTING: {"validation_metrics": {"val_pr_auc": 0.35}},
    }
    assert choose_served_model(selection) == LOGISTIC_REGRESSION


def test_choose_served_model_hgb_clear_win() -> None:
    """Higher validation PR-AUC for HGB selects it when the gap exceeds 0.01."""
    selection = {
        LOGISTIC_REGRESSION: {"validation_metrics": {"val_pr_auc": 0.30}},
        HIST_GRADIENT_BOOSTING: {"validation_metrics": {"val_pr_auc": 0.35}},
    }
    assert choose_served_model(selection) == HIST_GRADIENT_BOOSTING


def test_choose_served_model_tie_prefers_logreg() -> None:
    """When validation PR-AUC differs by less than 0.01, prefer logistic regression."""
    selection = {
        LOGISTIC_REGRESSION: {"validation_metrics": {"val_pr_auc": 0.370}},
        HIST_GRADIENT_BOOSTING: {"validation_metrics": {"val_pr_auc": 0.375}},
    }
    assert choose_served_model(selection) == LOGISTIC_REGRESSION


def test_evaluate_module_references_test_split() -> None:
    """Evaluation must load the held-out test split."""
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "src" / "icu" / "evaluate.py"
    text = source.read_text(encoding="utf-8")
    assert "test_ids" in text
