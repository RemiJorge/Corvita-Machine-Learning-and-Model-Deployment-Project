"""Tests for test-set evaluation, bootstrap intervals, and served-model choice (F7)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from icu.evaluate import (
    ICU_TYPE_CODES,
    bootstrap_intervals,
    choose_served_model,
    icu_type_subgroup_analysis,
    metrics_for_subgroup,
    subgroup_model_block,
)
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


def test_metrics_for_subgroup_too_few_events() -> None:
    """Fewer than 10 deaths or survivors yields ``too few events``."""
    y = np.array([1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], dtype=int)
    proba = np.linspace(0.1, 0.9, len(y))
    assert metrics_for_subgroup(y, proba, 0.5, 0.14) == "too few events"


def test_subgroup_model_block_includes_bootstrap() -> None:
    """Large enough subgroup returns bootstrap intervals."""
    rng = np.random.default_rng(1)
    y = rng.integers(0, 2, size=80)
    proba = rng.uniform(0.05, 0.95, size=80)
    block = subgroup_model_block(y, proba, 0.4, 0.14, 100, 7)
    assert isinstance(block, dict)
    assert "mean_predicted_probability" in block
    assert "bootstrap" in block
    assert "pr_auc" in block["bootstrap"]


def test_icu_type_subgroup_partition() -> None:
    """ICU type masks partition the test frame (one-hot encoding)."""
    n = 40
    frame = pd.DataFrame(
        {
            "icu_type_1": [1] * 10 + [0] * 30,
            "icu_type_2": [0] * 10 + [1] * 10 + [0] * 20,
            "icu_type_3": [0] * 20 + [1] * 10 + [0] * 10,
            "icu_type_4": [0] * 30 + [1] * 10,
        }
    )
    y = np.zeros(n, dtype=int)
    y[0] = 1
    y[10] = 1
    proba = np.full(n, 0.2)
    report = icu_type_subgroup_analysis(
        frame,
        y,
        {LOGISTIC_REGRESSION: proba, HIST_GRADIENT_BOOSTING: proba},
        {LOGISTIC_REGRESSION: 0.5, HIST_GRADIENT_BOOSTING: 0.5},
        0.14,
        n_resamples=50,
        seed=99,
    )
    assert set(report) == set(ICU_TYPE_CODES)
    assert sum(report[code]["n"] for code in ICU_TYPE_CODES) == n
    for code in ICU_TYPE_CODES:
        block = report[code]["models"][LOGISTIC_REGRESSION]
        assert block["metrics"] == "too few events"
        assert "mean_predicted_probability" in block
