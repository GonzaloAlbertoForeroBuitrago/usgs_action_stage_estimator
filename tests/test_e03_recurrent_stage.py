"""Tests for the cleaned V15 recurrent-stage selector."""

import inspect

import pandas as pd

from usgs_action_stage_estimator.e03_recurrent_stage import (
    HEIGHT_GATE,
    SCORE_RULE,
    estimate_recurrent_stage,
    select_v15_candidate,
)


def test_estimator_has_no_action_stage_argument():
    parameters = set(
        inspect.signature(
            estimate_recurrent_stage
        ).parameters
    )

    assert "action_stage_ft" not in parameters
    assert "action_stage" not in parameters
    assert "noaa" not in parameters


def test_v15_frozen_rule_identity():
    assert HEIGHT_GATE == "top3"
    assert SCORE_RULE == "recurrence_intensity"


def test_top3_recurrence_intensity_selection():
    candidates = pd.DataFrame([
        {
            "concentration_rank": 1,
            "height_ft": 4.0,
            "joint_events": 10,
            "events_exposed_at_height": 12,
            "joint_intensity_at_stage_median": 0.99,
            "first_value_ft_hr_median": 1.0,
            "second_value_ft_hr_median": 1.0,
        },
        {
            "concentration_rank": 2,
            "height_ft": 6.0,
            "joint_events": 8,
            "events_exposed_at_height": 10,
            "joint_intensity_at_stage_median": 0.60,
            "first_value_ft_hr_median": 1.0,
            "second_value_ft_hr_median": 1.0,
        },
        {
            "concentration_rank": 3,
            "height_ft": 8.0,
            "joint_events": 6,
            "events_exposed_at_height": 8,
            "joint_intensity_at_stage_median": 0.90,
            "first_value_ft_hr_median": 1.0,
            "second_value_ft_hr_median": 1.0,
        },
        {
            "concentration_rank": 4,
            "height_ft": 10.0,
            "joint_events": 5,
            "events_exposed_at_height": 7,
            "joint_intensity_at_stage_median": 0.80,
            "first_value_ft_hr_median": 1.0,
            "second_value_ft_hr_median": 1.0,
        },
    ])

    winner, considered = (
        select_v15_candidate(
            candidates
        )
    )

    assert considered == 3
    assert winner is not None
    assert winner["height_ft"] == 8.0
