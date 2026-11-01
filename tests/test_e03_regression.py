
"""Regression tests for the original four-station E03-J experiment.

Reads existing E03-E outputs. Does not modify files.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from usgs_action_stage_estimator.e03_station_windows import (
    calculate_station_windows,
    select_winning_window,
)


ROOT = (
    Path.home()
    / "Documents/usgs_mrms_research/outputs/"
    "action_stage_estimator/E03"
)

CONTROLS = [
    ("TEXAS", "08165500", 10.0, 13.25, 10.75, 5, 5),
    ("WISCONSIN", "05430500", 8.0, 9.75, 9.75, 7, 7),
    ("GEORGIA", "02337170", 17.0, 11.50, 1.25, 44, 173),
    ("MARYLAND", "0158397967", 8.0, 7.75, 4.75, 18, 131),
]


@pytest.mark.parametrize(
    "state,site_id,action,first_center,second_center,"
    "first_support,second_support",
    CONTROLS,
)
def test_original_e03_winning_windows(
    state,
    site_id,
    action,
    first_center,
    second_center,
    first_support,
    second_support,
):
    path = (
        ROOT / state / site_id
        / "e03_rising_limb_dynamics.parquet"
    )

    if not path.is_file():
        pytest.fail(f"Missing E03-E regression fixture: {path}")

    df = pd.read_parquet(path)

    selected = df.loc[df["selected_both"]].copy()

    expected = [
        ("first_derivative_ft_hr", first_center, first_support),
        ("second_derivative_ft_hr2", second_center, second_support),
    ]

    for metric, center, support in expected:
        profile = calculate_station_windows(
            selected,
            metric,
            window_width_ft=1.0,
            center_step_ft=0.25,
        )

        winner = select_winning_window(
            profile,
            action_stage_ft=action,
            min_events=5,
        )

        assert winner is not None

        assert np.isclose(
            winner["center_ft"],
            center,
            rtol=0,
            atol=1e-10,
        )

        assert int(winner["contributing_events"]) == support

        assert np.isclose(
            winner["window_upper_ft"]
            - winner["window_lower_ft"],
            1.0,
        )
