
"""Reusable E03 rising-limb derivative calculations.

No interpolation or resampling.
Actual UTC observation intervals are preserved.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_rising_limb_derivatives(
    observations: pd.DataFrame,
    max_interval_minutes: float = 60.0,
) -> pd.DataFrame:
    """Calculate stage derivatives within one validated rising limb.

    Required columns:
        datetime: observation timestamp
        Stage_ft: original stage measurement

    Returns:
        Original observations plus interval derivatives.
    """
    required = {"datetime", "Stage_ft"}

    missing = required - set(observations.columns)
    if missing:
        raise ValueError(
            f"Missing observation columns: {sorted(missing)}"
        )

    result = observations.copy()

    result["datetime"] = pd.to_datetime(
        result["datetime"], utc=True
    )

    if result["datetime"].isna().any():
        raise ValueError("Missing observation timestamps.")

    if result["Stage_ft"].isna().any():
        raise ValueError("Missing stage observations.")

    if not np.isfinite(
        result["Stage_ft"].to_numpy(dtype=float)
    ).all():
        raise ValueError("Non-finite stage observations.")

    if not result["datetime"].is_monotonic_increasing:
        raise ValueError("Timestamps must be increasing.")

    dt = (
        result["datetime"].diff()
        .dt.total_seconds() / 3600.0
    )

    if (dt.dropna() <= 0).any():
        raise ValueError("Duplicate or invalid timestamps.")

    valid = dt.gt(0) & dt.le(
        max_interval_minutes / 60.0
    )

    rate = (
        result["Stage_ft"].diff() / dt
    ).where(valid)

    midpoint_dt = (
        dt + dt.shift(1)
    ) / 2.0

    acceleration = (
        (rate - rate.shift(1)) / midpoint_dt
    ).where(
        valid & valid.shift(1, fill_value=False)
    )

    midpoint_stage = (
        result["Stage_ft"]
        + result["Stage_ft"].shift(1)
    ) / 2.0

    result["dt_min"] = dt * 60.0
    result["midpoint_stage_ft"] = midpoint_stage
    result["first_derivative_ft_hr"] = rate
    result["second_derivative_ft_hr2"] = acceleration

    return result


def select_upper_half(
    events: pd.DataFrame,
    metric: str,
) -> pd.DataFrame:
    """Select exactly the highest half of valid event metrics.

    Ties are broken by peak date, start date, and segment ID.
    """

    required = {
        metric,
        "date_peak",
        "date_start",
        "segment_id",
    }

    missing = required - set(events.columns)
    if missing:
        raise ValueError(
            f"Missing event columns: {sorted(missing)}"
        )

    result = events.copy()

    valid = result.loc[
        np.isfinite(
            pd.to_numeric(result[metric], errors="coerce")
        )
    ].copy()

    valid["date_peak"] = pd.to_datetime(
        valid["date_peak"], utc=True
    )

    valid["date_start"] = pd.to_datetime(
        valid["date_start"], utc=True
    )

    valid = valid.sort_values(
        [metric, "date_peak", "date_start", "segment_id"],
        ascending=[False, True, True, True],
        kind="stable",
    )

    n = (len(valid) + 1) // 2

    result["selected"] = False
    result.loc[valid.index[:n], "selected"] = True

    return result
