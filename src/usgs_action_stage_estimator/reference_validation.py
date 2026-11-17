"""Validate Action Stage references and diagnose stage-reference scale.

Reference handling in this module is evaluation/QC only. It must not alter the
reference-free recurrent-stage estimator.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .identifiers import validate_site_id


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


def assess_stage_reference_scale(
    stage_ft,
    action_stage_ft: float,
    *,
    margin_ft: float = 10.0,
) -> dict:
    """Diagnose whether Action Stage is on a plausible observed stage scale.

    This is an evaluation/interoperability diagnostic, not an estimator input
    and not proof that two vertical datums are identical.

    Parameters
    ----------
    stage_ft
        Raw observed USGS/P00 stage values in feet. Any array-like object
        accepted by :class:`pandas.Series` may be supplied.
    action_stage_ft
        Official/reference Action Stage in feet.
    margin_ft
        Symmetric margin added to the observed minimum/maximum for the
        diagnostic check. The default 10 ft reproduces the post-validation
        reference-scale audit.

    Returns
    -------
    dict
        Observed-stage distribution statistics and a non-destructive diagnostic
        status. The result must not be used to change a recurrent-stage estimate.

    Notes
    -----
    In the frozen prospective validation, every one of the 39 evaluable
    stations with absolute V22 signed error greater than 100 ft also had Action
    Stage outside the raw observed Stage_ft minimum/maximum expanded by +/-10 ft.
    That finding motivated this QC function. Those stations remained in the
    primary validation and this function does not define an exclusion rule.
    """

    try:
        action = float(action_stage_ft)
    except (TypeError, ValueError) as exc:
        raise ValueError("Action Stage must be finite.") from exc

    if not np.isfinite(action):
        raise ValueError("Action Stage must be finite.")

    try:
        margin = float(margin_ft)
    except (TypeError, ValueError) as exc:
        raise ValueError("margin_ft must be finite and nonnegative.") from exc

    if not np.isfinite(margin) or margin < 0:
        raise ValueError("margin_ft must be finite and nonnegative.")

    values = pd.to_numeric(
        pd.Series(stage_ft, dtype="object"),
        errors="coerce",
    )

    values = values.loc[
        np.isfinite(values.to_numpy(dtype=float))
    ].astype(float)

    base = {
        "action_stage_ft": action,
        "margin_ft": margin,
        "stage_rows": int(len(values)),
        "stage_min_ft": np.nan,
        "stage_q01_ft": np.nan,
        "stage_q05_ft": np.nan,
        "stage_median_ft": np.nan,
        "stage_q95_ft": np.nan,
        "stage_q99_ft": np.nan,
        "stage_max_ft": np.nan,
        "stage_range_ft": np.nan,
        "action_minus_stage_median_ft": np.nan,
        "action_within_observed_minmax": False,
        "action_within_observed_minmax_plus_margin": False,
        "diagnostic_status": "stage_series_unavailable",
    }

    if values.empty:
        return base

    quantiles = values.quantile(
        [0.01, 0.05, 0.50, 0.95, 0.99]
    )

    stage_min = float(values.min())
    stage_max = float(values.max())
    stage_median = float(quantiles.loc[0.50])

    inside = bool(
        stage_min <= action <= stage_max
    )

    inside_margin = bool(
        stage_min - margin
        <= action
        <= stage_max + margin
    )

    if inside:
        status = "inside_observed_stage_range"
    elif inside_margin:
        status = "within_observed_stage_range_margin"
    else:
        status = "reference_scale_review_required"

    base.update({
        "stage_min_ft": stage_min,
        "stage_q01_ft": float(quantiles.loc[0.01]),
        "stage_q05_ft": float(quantiles.loc[0.05]),
        "stage_median_ft": stage_median,
        "stage_q95_ft": float(quantiles.loc[0.95]),
        "stage_q99_ft": float(quantiles.loc[0.99]),
        "stage_max_ft": stage_max,
        "stage_range_ft": stage_max - stage_min,
        "action_minus_stage_median_ft": (
            action - stage_median
        ),
        "action_within_observed_minmax": inside,
        "action_within_observed_minmax_plus_margin": (
            inside_margin
        ),
        "diagnostic_status": status,
    })

    return base
