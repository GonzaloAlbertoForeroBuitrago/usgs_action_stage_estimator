
"""Tests for E03 station-level moving windows."""

import numpy as np
import pandas as pd

from usgs_action_stage_estimator.e03_station_windows import (
    calculate_station_windows,
    select_winning_window,
)


def test_equal_event_weighting():
    df = pd.DataFrame({
        "event_id": ["A", "A", "A", "B"],
        "midpoint_stage_ft": [8.0, 8.0, 8.0, 8.0],
        "first_derivative_ft_hr": [2.0, 2.0, 2.0, 6.0],
    })

    profile = calculate_station_windows(
        df, "first_derivative_ft_hr"
    )

    center = profile.loc[
        np.isclose(profile["center_ft"], 8.0)
    ].iloc[0]

    assert np.isclose(center["event_weighted_mean"], 4.0)
    assert center["contributing_events"] == 2
    assert center["contributing_observations"] == 4


def test_winning_window_and_action_relation():
    profile = pd.DataFrame({
        "center_ft": [8.0, 9.0, 10.0],
        "event_weighted_mean": [1.0, 3.0, 2.0],
        "contributing_events": [8, 7, 6],
        "window_lower_ft": [7.5, 8.5, 9.5],
        "window_upper_ft": [8.5, 9.5, 10.5],
    })

    winner = select_winning_window(
        profile, action_stage_ft=9.0, min_events=5
    )

    assert winner["center_ft"] == 9.0
    assert winner["action_relation"] == "intersects"
    assert winner["contributing_events"] == 7


def test_insufficient_support():
    profile = pd.DataFrame({
        "center_ft": [8.0],
        "event_weighted_mean": [10.0],
        "contributing_events": [2],
        "window_lower_ft": [7.5],
        "window_upper_ft": [8.5],
    })

    assert select_winning_window(
        profile, action_stage_ft=10.0, min_events=5
    ) is None


def test_irregular_stage_spacing():
    df = pd.DataFrame({
        "event_id": ["A", "A", "B", "B"],
        "midpoint_stage_ft": [7.81, 8.13, 7.94, 8.27],
        "second_derivative_ft_hr2": [1.0, 2.0, 3.0, 4.0],
    })

    profile = calculate_station_windows(
        df, "second_derivative_ft_hr2"
    )

    assert not profile.empty
    assert profile["contributing_events"].max() == 2
    assert np.allclose(
        profile["window_upper_ft"] - profile["window_lower_ft"],
        1.0,
    )
