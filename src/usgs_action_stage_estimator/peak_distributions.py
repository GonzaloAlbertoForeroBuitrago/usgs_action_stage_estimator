"""Observed peak-stage and event-magnitude distributions.

E01: Independent hydrological analysis.
NOAA Action Stage is not required for these calculations.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


RISE_THRESHOLDS_FT = (
    0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0
)

PERCENTILES = (
    0.01, 0.05, 0.10, 0.25,
    0.50, 0.75, 0.90, 0.95, 0.99
)


def prepare_peak_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    """Add derived metrics without removing original candidates."""

    required = {
        "flow_peak",
        "flow_start",
        "quick_stage_at_peak_ft",
        "candidate_type",
        "event_status",
    }

    missing = required - set(candidates.columns)

    if missing:
        raise ValueError(
            f"Missing candidate columns: {sorted(missing)}"
        )

    data = candidates.copy()

    data["event_rise_ft"] = (
        pd.to_numeric(data["flow_peak"], errors="coerce")
        - pd.to_numeric(data["flow_start"], errors="coerce")
    )

    data["quick_peak_ft"] = pd.to_numeric(
        data["quick_stage_at_peak_ft"],
        errors="coerce",
    )

    data["is_detected_event"] = (
        data["candidate_type"] == "detected_event"
    )

    data["is_complete_event"] = (
        data["is_detected_event"]
        & (data["event_status"] == "complete")
    )

    return data


def calculate_peak_distributions(
    candidates: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate stage and magnitude distributions by population."""

    data = prepare_peak_candidates(candidates)

    populations = {
        "all_candidates": data,
        "detected_events": data.loc[data["is_detected_event"]],
        "complete_events": data.loc[data["is_complete_event"]],
    }

    records = []

    for population, subset in populations.items():
        for metric in (
            "flow_peak",
            "event_rise_ft",
            "quick_peak_ft",
        ):
            values = pd.to_numeric(
                subset[metric], errors="coerce"
            ).dropna()

            record = {
                "population": population,
                "metric": metric,
                "candidate_count": len(subset),
                "valid_count": len(values),
                "minimum": (
                    float(values.min()) if len(values) else np.nan
                ),
                "maximum": (
                    float(values.max()) if len(values) else np.nan
                ),
                "mean": (
                    float(values.mean()) if len(values) else np.nan
                ),
            }

            for percentile in PERCENTILES:
                name = f"p{int(percentile * 100):02d}"
                record[name] = (
                    float(values.quantile(percentile))
                    if len(values) else np.nan
                )

            records.append(record)

    return pd.DataFrame(records)


def calculate_rise_sensitivity(
    candidates: pd.DataFrame,
    thresholds: tuple[float, ...] = RISE_THRESHOLDS_FT,
) -> pd.DataFrame:
    """Evaluate event populations under minimum-rise thresholds."""

    data = prepare_peak_candidates(candidates)
    events = data.loc[data["is_detected_event"]]

    records = []

    for threshold in thresholds:
        selected = events.loc[
            events["event_rise_ft"] >= threshold
        ]

        records.append({
            "minimum_rise_ft": float(threshold),
            "retained_events": len(selected),
            "retained_fraction": (
                len(selected) / len(events)
                if len(events) else np.nan
            ),
            "median_peak_ft": (
                float(selected["flow_peak"].median())
                if len(selected) else np.nan
            ),
            "maximum_peak_ft": (
                float(selected["flow_peak"].max())
                if len(selected) else np.nan
            ),
        })

    return pd.DataFrame(records)


def compare_action_stage(
    candidates: pd.DataFrame,
    action_stage_ft: float,
    thresholds: tuple[float, ...] = RISE_THRESHOLDS_FT,
) -> pd.DataFrame:
    """Compare observed event peaks against an external reference."""

    if not np.isfinite(action_stage_ft):
        raise ValueError("Action Stage must be finite.")

    data = prepare_peak_candidates(candidates)
    events = data.loc[data["is_detected_event"]]

    records = []

    for threshold in thresholds:
        selected = events.loc[
            events["event_rise_ft"] >= threshold
        ]

        peaks = pd.to_numeric(
            selected["flow_peak"], errors="coerce"
        ).dropna()

        records.append({
            "minimum_rise_ft": float(threshold),
            "retained_events": len(peaks),
            "action_stage_ft": float(action_stage_ft),
            "peaks_below_action": int(
                (peaks < action_stage_ft).sum()
            ),
            "peaks_equal_action": int(
                (peaks == action_stage_ft).sum()
            ),
            "peaks_above_action": int(
                (peaks > action_stage_ft).sum()
            ),
            "peaks_at_or_above_action": int(
                (peaks >= action_stage_ft).sum()
            ),
            "action_ecdf_percentile": (
                100.0 * (peaks <= action_stage_ft).mean()
                if len(peaks) else np.nan
            ),
        })

    return pd.DataFrame(records)
