"""Validate and standardize historical Action Stage references."""

from __future__ import annotations

from .identifiers import validate_site_id

from pathlib import Path

import numpy as np
import pandas as pd


REFERENCE_COLUMNS = [
    "site_id",
    "state",
    "station_name",
    "nws_lid",
    "inventory_action_stage_ft",
    "action_stage_original_ft",
    "action_stage_corrected_ft",
    "reference_compatible",
    "action_comparison_eligible",
    "validation_status",
    "correction_applied",
    "noaa_minus_usgs_ft",
    "harmonization_status",
    "qc_status",
    "latitude",
    "longitude",
    "vertical_datum",
    "source",
]


def _boolean_flag(series: pd.Series) -> pd.Series:
    """Preserve missing values in nullable boolean fields."""
    normalized = series.astype("string").str.strip().str.lower()

    invalid = (
        normalized.notna()
        & ~normalized.isin(["true", "false"])
    )

    if invalid.any():
        raise ValueError("Unexpected boolean flag value.")

    return normalized.map({
        "true": True,
        "false": False,
    }).astype("boolean")


def clean_action_stage_references(
    source_csv: str | Path,
) -> pd.DataFrame:
    """Clean reference metadata without estimating Action Stage."""

    source_csv = Path(source_csv)

    if not source_csv.is_file():
        raise FileNotFoundError(source_csv)

    data = pd.read_csv(
        source_csv,
        dtype={"site_id": "string"},
    )

    missing = set(REFERENCE_COLUMNS) - set(data.columns)

    if missing:
        raise ValueError(
            f"Missing reference columns: {sorted(missing)}"
        )

    data = data[REFERENCE_COLUMNS].copy()

    data["site_id"] = data["site_id"].map(
        validate_site_id,
        na_action="ignore",
    )

    if data["site_id"].isna().any():
        raise ValueError("Missing station identifiers.")

    if data["site_id"].duplicated().any():
        raise ValueError("Duplicate station identifiers.")

    for column in [
        "reference_compatible",
        "action_comparison_eligible",
        "correction_applied",
    ]:
        data[column] = _boolean_flag(data[column])

    for column in [
        "inventory_action_stage_ft",
        "action_stage_original_ft",
        "action_stage_corrected_ft",
        "noaa_minus_usgs_ft",
        "latitude",
        "longitude",
    ]:
        data[column] = pd.to_numeric(
            data[column],
            errors="coerce",
        )

    valid_reference = np.isfinite(
        data["action_stage_corrected_ft"]
    )

    eligible = (
        data["reference_compatible"].fillna(False)
        & data["action_comparison_eligible"].fillna(False)
        & valid_reference
    )

    data["reference_eligible"] = eligible.astype(bool)

    data["validated_action_stage_ft"] = (
        data["action_stage_corrected_ft"]
        .where(data["reference_eligible"])
    )

    return data.sort_values("site_id").reset_index(drop=True)
