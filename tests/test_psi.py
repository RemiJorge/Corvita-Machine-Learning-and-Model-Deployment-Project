"""Tests for PSI binning and score computation."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from icu.psi import (
    assign_feature_bin,
    compute_psi,
    compute_psi_bin_spec,
    compute_psi_bins,
)


def test_compute_psi_identical_is_near_zero() -> None:
    props = [0.1] * 10
    psi = compute_psi(props, props)
    assert psi == pytest.approx(0.0, abs=1e-9)


def test_compute_psi_shifted_is_positive() -> None:
    expected = [0.1] * 10
    actual = [0.0] * 9 + [1.0]
    psi = compute_psi(expected, actual)
    assert psi > 0.25


def test_compute_psi_bins_includes_missing_bin() -> None:
    series = pd.Series([1.0, 2.0, 3.0, math.nan, 5.0])
    spec = compute_psi_bin_spec(series)
    assert spec["n_bins"] == 11
    assert len(spec["proportions"]) == 11
    assert sum(spec["proportions"]) == pytest.approx(1.0)


def test_assign_feature_bin_respects_missing() -> None:
    spec = compute_psi_bin_spec(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]))
    missing_bin = spec["missing_bin"]
    assert assign_feature_bin(float("nan"), spec) == missing_bin


def test_compute_psi_bins_all_features() -> None:
    import numpy as np

    from icu.features import FEATURE_COLUMNS

    rng = np.random.default_rng(0)
    frame = pd.DataFrame(rng.normal(size=(50, len(FEATURE_COLUMNS))), columns=FEATURE_COLUMNS)
    frame["age"] = rng.uniform(20, 90, size=50)
    bins = compute_psi_bins(frame)
    assert "temp_mean" in bins
    assert "hr_count" in bins
