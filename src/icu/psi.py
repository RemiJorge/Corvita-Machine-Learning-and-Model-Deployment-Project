"""Population Stability Index helpers for monitoring continuous features."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from icu.train import CONTINUOUS_COLUMNS, COUNT_COLUMNS

PSI_FEATURE_COLUMNS: tuple[str, ...] = tuple(
    col for col in (*CONTINUOUS_COLUMNS, *COUNT_COLUMNS) if col not in ("gender_male",)
)

DECILE_PERCENTILES = np.arange(10, 100, 10)
N_DECILE_BINS = 10
PSI_EPSILON = 1e-4


def compute_psi_bin_spec(series: pd.Series) -> dict[str, Any]:
    """Build decile edges and training bin proportions for one feature.

    Missing values use a dedicated bin after the decile bins (index ``N_DECILE_BINS``).

    Args:
        series: Training column values (may contain NaN).

    Returns:
        Dict with ``edges``, ``proportions``, ``missing_bin``, and ``n_bins``.
    """
    n = len(series)
    if n == 0:
        msg = "PSI bin spec requires at least one row"
        raise ValueError(msg)

    missing_bin = N_DECILE_BINS
    counts = [0] * (N_DECILE_BINS + 1)
    non_missing = series.dropna()
    if len(non_missing) == 0:
        counts[missing_bin] = n
        return {
            "edges": [],
            "proportions": [c / n for c in counts],
            "missing_bin": missing_bin,
            "n_bins": N_DECILE_BINS + 1,
        }

    edges_arr = np.percentile(non_missing.to_numpy(dtype=float), DECILE_PERCENTILES)
    edges = [float(x) for x in edges_arr]

    for value in series:
        if pd.isna(value):
            counts[missing_bin] += 1
        else:
            bin_idx = assign_value_to_decile(float(value), edges)
            counts[bin_idx] += 1

    return {
        "edges": edges,
        "proportions": [c / n for c in counts],
        "missing_bin": missing_bin,
        "n_bins": N_DECILE_BINS + 1,
    }


def compute_psi_bins(x_train: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Compute PSI reference bins for all monitored continuous features.

    Args:
        x_train: Training feature matrix.

    Returns:
        Mapping feature name to bin spec from ``compute_psi_bin_spec``.
    """
    bins: dict[str, dict[str, Any]] = {}
    for column in PSI_FEATURE_COLUMNS:
        if column not in x_train.columns:
            msg = f"Missing PSI feature column: {column}"
            raise ValueError(msg)
        bins[column] = compute_psi_bin_spec(x_train[column])
    return bins


def assign_value_to_decile(value: float, edges: list[float]) -> int:
    """Map a non-missing value to decile bin index 0 through 9."""
    if not edges:
        return 0
    idx = int(np.searchsorted(edges, value, side="right"))
    return min(idx, N_DECILE_BINS - 1)


def assign_feature_bin(value: Any, spec: dict[str, Any]) -> int:
    """Map one feature value to its bin index using a stored spec."""
    missing_bin = int(spec["missing_bin"])
    if value is None:
        return missing_bin
    if isinstance(value, float) and math.isnan(value):
        return missing_bin
    if pd.isna(value):
        return missing_bin
    edges = spec.get("edges") or []
    return assign_value_to_decile(float(value), edges)


def feature_bins_from_row(row: pd.Series, psi_bins: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Assign bin indices for monitored features on one feature row."""
    return {
        column: assign_feature_bin(row[column], psi_bins[column])
        for column in PSI_FEATURE_COLUMNS
        if column in psi_bins
    }


def compute_psi(expected: list[float], actual: list[float], epsilon: float = PSI_EPSILON) -> float:
    """Population Stability Index between two bin proportion vectors."""
    if len(expected) != len(actual):
        msg = "PSI vectors must have the same length"
        raise ValueError(msg)
    total = 0.0
    for exp_prop, act_prop in zip(expected, actual, strict=True):
        e = max(float(exp_prop), epsilon)
        a = max(float(act_prop), epsilon)
        total += (a - e) * math.log(a / e)
    return total
