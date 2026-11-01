
"""Reusable E03-J station-level moving-window analysis.

Uses precomputed derivatives, without interpolation or resampling.
Each event contributes one mean derivative per stage window.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


WINDOW_WIDTH_FT = 1.0
CENTER_STEP_FT = 0.25
MIN_EVENTS = 5

METRICS = {
    "first": "first_derivative_ft_hr",
    "second": "second_derivative_ft_hr2",
}


def calculate_station_windows(
    observations: pd.DataFrame,
    metric: str,
    window_width_ft: float = WINDOW_WIDTH_FT,
    center_step_ft: float = CENTER_STEP_FT,
) -> pd.DataFrame:
    """Calculate event-weighted derivative profiles by stage window."""

    required = {"event_id", "midpoint_stage_ft", metric}
    missing = required - set(observations.columns)

    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    if not np.isfinite(window_width_ft) or window_width_ft <= 0:
        raise ValueError("Window width must be positive.")

    if not np.isfinite(center_step_ft) or center_step_ft <= 0:
        raise ValueError("Center step must be positive.")

    valid = observations.loc[
        np.isfinite(observations["midpoint_stage_ft"])
        & np.isfinite(observations[metric])
    ]

    columns = [
        "center_ft",
        "event_weighted_mean",
        "median_event_mean",
        "contributing_events",
        "contributing_observations",
        "window_lower_ft",
        "window_upper_ft",
    ]

    if valid.empty:
        return pd.DataFrame(columns=columns)

    hmin = valid["midpoint_stage_ft"].min()
    hmax = valid["midpoint_stage_ft"].max()

    lower = np.floor(hmin / center_step_ft)
    upper = np.ceil(hmax / center_step_ft)

    centers = (
        np.arange(lower, upper + 1, dtype=float)
        * center_step_ft
    )

    half_width = window_width_ft / 2
    records = []

    for event_id, group in valid.groupby("event_id", sort=False):
        h = group["midpoint_stage_ft"].to_numpy(dtype=float)
        values = group[metric].to_numpy(dtype=float)

        order = np.argsort(h, kind="stable")
        h = h[order]
        values = values[order]

        cumulative = np.concatenate(
            ([0.0], np.cumsum(values))
        )

        start = np.searchsorted(
            centers, h.min() - half_width, side="left"
        )
        stop = np.searchsorted(
            centers, h.max() + half_width, side="right"
        )

        local_centers = centers[start:stop]

        left = np.searchsorted(
            h, local_centers - half_width, side="left"
        )
        right = np.searchsorted(
            h, local_centers + half_width, side="right"
        )

        counts = right - left
        supported = counts > 0

        means = (
            cumulative[right[supported]]
            - cumulative[left[supported]]
        ) / counts[supported]

        records.extend(
            (event_id, float(c), float(m), int(n))
            for c, m, n in zip(
                local_centers[supported],
                means,
                counts[supported],
            )
        )

    event_windows = pd.DataFrame(
        records,
        columns=[
            "event_id",
            "center_ft",
            "event_mean",
            "observation_count",
        ],
    )

    profile = (
        event_windows.groupby("center_ft")
        .agg(
            event_weighted_mean=("event_mean", "mean"),
            median_event_mean=("event_mean", "median"),
            contributing_events=("event_id", "nunique"),
            contributing_observations=(
                "observation_count", "sum"
            ),
        )
        .reset_index()
    )

    profile["window_lower_ft"] = (
        profile["center_ft"] - half_width
    )
    profile["window_upper_ft"] = (
        profile["center_ft"] + half_width
    )

    return profile[columns]


def select_winning_window(
    profile: pd.DataFrame,
    action_stage_ft: float,
    min_events: int = MIN_EVENTS,
) -> dict | None:
    """Select highest event-weighted mean among supported windows."""

    if min_events < 1:
        raise ValueError("min_events must be positive.")

    if not np.isfinite(action_stage_ft):
        raise ValueError("Action Stage must be finite.")

    eligible = profile.loc[
        (profile["contributing_events"] >= min_events)
        & np.isfinite(profile["event_weighted_mean"])
    ]

    if eligible.empty:
        return None

    winner = eligible.sort_values(
        [
            "event_weighted_mean",
            "contributing_events",
            "center_ft",
        ],
        ascending=[False, False, True],
        kind="stable",
    ).iloc[0]

    result = winner.to_dict()

    result["action_stage_ft"] = float(action_stage_ft)
    result["action_minus_center_ft"] = (
        action_stage_ft - result["center_ft"]
    )

    if result["window_upper_ft"] < action_stage_ft:
        relation = "below"
    elif result["window_lower_ft"] > action_stage_ft:
        relation = "above"
    else:
        relation = "intersects"

    result["action_relation"] = relation

    return result
