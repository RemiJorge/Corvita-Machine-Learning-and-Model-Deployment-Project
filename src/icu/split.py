"""Stratified train, validation, and test split by RecordID."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

from icu.config import load_config
from icu.tables import ADMISSION_PARQUET

logger = logging.getLogger(__name__)

TRAIN_IDS_CSV = "train_ids.csv"
VAL_IDS_CSV = "val_ids.csv"
TEST_IDS_CSV = "test_ids.csv"


def stratified_split(
    record_ids: list[int] | pd.Series,
    labels: list[int] | pd.Series,
    train_frac: float,
    val_frac: float,
    test_frac: float,
    seed: int,
) -> tuple[list[int], list[int], list[int]]:
    """Split record IDs into train, validation, and test with stratification on labels.

    Uses two ``train_test_split`` calls: first holdout ``val_frac + test_frac``, then
    split the holdout evenly into validation and test.

    Args:
        record_ids: One ID per ICU stay.
        labels: Binary outcome (0/1), same length as ``record_ids``.
        train_frac: Target fraction for training (e.g. 0.70).
        val_frac: Target fraction for validation (e.g. 0.15).
        test_frac: Target fraction for test (e.g. 0.15).
        seed: Random seed for both splits.

    Returns:
        Three lists of record IDs, each sorted ascending.

    Raises:
        ValueError: If fractions do not sum to 1 or lengths mismatch.
    """
    total_frac = train_frac + val_frac + test_frac
    if abs(total_frac - 1.0) > 1e-9:
        msg = f"Split fractions must sum to 1, got {total_frac}"
        raise ValueError(msg)

    ids = pd.Series(record_ids).astype(int)
    y = pd.Series(labels).astype(int)
    if len(ids) != len(y):
        msg = "record_ids and labels must have the same length"
        raise ValueError(msg)

    order = ids.sort_values().index
    ids_sorted = ids.loc[order].tolist()
    y_sorted = y.loc[order].tolist()

    holdout_frac = val_frac + test_frac
    train_ids, holdout_ids, _, holdout_labels = train_test_split(
        ids_sorted,
        y_sorted,
        test_size=holdout_frac,
        stratify=y_sorted,
        random_state=seed,
    )
    if holdout_frac <= 0:
        msg = "Holdout fraction must be positive"
        raise ValueError(msg)
    inner_test_size = test_frac / holdout_frac
    val_ids, test_ids, _, _ = train_test_split(
        holdout_ids,
        holdout_labels,
        test_size=inner_test_size,
        stratify=holdout_labels,
        random_state=seed,
    )

    return (
        sorted(int(i) for i in train_ids),
        sorted(int(i) for i in val_ids),
        sorted(int(i) for i in test_ids),
    )


def write_split_csv(path: Path, record_ids: list[int]) -> None:
    """Write one column ``record_id`` to a CSV file.

    Args:
        path: Output file path.
        record_ids: IDs to write, sorted ascending by caller.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({"record_id": record_ids})
    frame.to_csv(path, index=False)


def main(config_path: Path | str | None = None) -> None:
    """Write stratified train, validation, and test ID files from admission labels."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = load_config(config_path)
    processed_dir = Path(config["paths"]["processed_dir"])
    splits_dir = Path(config["paths"]["splits_dir"])
    admission_path = processed_dir / ADMISSION_PARQUET
    if not admission_path.is_file():
        raise FileNotFoundError(f"Admission table not found: {admission_path}")

    admission = pd.read_parquet(admission_path, columns=["record_id", "in_hospital_death"])
    admission = admission.sort_values("record_id").reset_index(drop=True)
    record_ids = admission["record_id"].astype(int).tolist()
    labels = admission["in_hospital_death"].astype(int).tolist()

    split_cfg = config["split"]
    train_frac = float(split_cfg["train"])
    val_frac = float(split_cfg["val"])
    test_frac = float(split_cfg["test"])
    seed = int(config["seed"])

    train_ids, val_ids, test_ids = stratified_split(
        record_ids,
        labels,
        train_frac,
        val_frac,
        test_frac,
        seed,
    )

    write_split_csv(splits_dir / TRAIN_IDS_CSV, train_ids)
    write_split_csv(splits_dir / VAL_IDS_CSV, val_ids)
    write_split_csv(splits_dir / TEST_IDS_CSV, test_ids)

    label_by_id = admission.set_index("record_id")["in_hospital_death"]
    for name, ids in (("train", train_ids), ("val", val_ids), ("test", test_ids)):
        rate = float(label_by_id.loc[ids].mean())
        logger.info("%s: n=%s death_rate=%.4f", name, len(ids), rate)


if __name__ == "__main__":
    main()
