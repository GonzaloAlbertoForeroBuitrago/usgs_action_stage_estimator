
"""Tests for reusable E03 derivative calculations."""

import numpy as np
import pandas as pd
import pytest

from usgs_action_stage_estimator.e03_dynamics import (
    calculate_rising_limb_derivatives,
    select_upper_half,
)


def test_irregular_time_intervals():
    observations = pd.DataFrame({
        "datetime": pd.to_datetime([
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:05:00Z",
            "2026-01-01T00:20:00Z",
            "2026-01-01T00:50:00Z",
        ]),
        "Stage_ft": [8.0, 8.1, 8.4, 9.0],
    })

    result = calculate_rising_limb_derivatives(
        observations
    )

    rates = result[
        "first_derivative_ft_hr"
    ].to_numpy()

    assert np.isnan(rates[0])
    np.testing.assert_allclose(
        rates[1:],
        [1.2, 1.2, 1.2],
        atol=1e-10,
    )

    acceleration = result[
        "second_derivative_ft_hr2"
    ].to_numpy()

    assert np.isnan(acceleration[:2]).all()
    np.testing.assert_allclose(
        acceleration[2:],
        [0.0, 0.0],
        atol=1e-10,
    )


def test_gap_does_not_generate_derivative():
    observations = pd.DataFrame({
        "datetime": pd.to_datetime([
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:05:00Z",
            "2026-01-01T02:00:00Z",
            "2026-01-01T02:05:00Z",
        ]),
        "Stage_ft": [8.0, 8.1, 9.0, 9.1],
    })

    result = calculate_rising_limb_derivatives(
        observations
    )

    assert np.isnan(
        result.iloc[2]["first_derivative_ft_hr"]
    )

    assert np.isnan(
        result.iloc[3]["second_derivative_ft_hr2"]
    )


def test_upper_half_selection():
    events = pd.DataFrame({
        "date_start": pd.date_range(
            "2026-01-01", periods=5, freq="h", tz="UTC"
        ),
        "date_peak": pd.date_range(
            "2026-01-01 00:30",
            periods=5, freq="h", tz="UTC"
        ),
        "segment_id": [1] * 5,
        "rate": [1.0, 2.0, 3.0, 4.0, 5.0],
    })

    result = select_upper_half(events, "rate")

    assert result["selected"].sum() == 3
    assert result.loc[
        result["selected"], "rate"
    ].tolist() == [3.0, 4.0, 5.0]


def test_duplicate_timestamps_rejected():
    observations = pd.DataFrame({
        "datetime": pd.to_datetime([
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:05:00Z",
            "2026-01-01T00:05:00Z",
        ]),
        "Stage_ft": [8.0, 8.1, 8.2],
    })

    with pytest.raises(ValueError):
        calculate_rising_limb_derivatives(observations)
