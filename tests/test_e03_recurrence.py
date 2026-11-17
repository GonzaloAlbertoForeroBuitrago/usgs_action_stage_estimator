"""Tests for E03 independent-event recurrence mechanics."""

import numpy as np
import pandas as pd

from usgs_action_stage_estimator.e03_recurrence import (
    adaptive_p50_width,
    crossing_times,
    event_regions,
    recurrence_by_overlap,
    recurrence_concentrations,
)


def test_adaptive_p50_width_has_one_foot_floor():
    events = pd.DataFrame({
        "rise_ft": [0.2, 0.8, 0.9],
    })
    assert adaptive_p50_width(events) == 1.0

    events = pd.DataFrame({
        "rise_ft": [1.2, 2.0, 5.0],
    })
    assert adaptive_p50_width(events) == 2.0


def test_crossing_times_interpolates_actual_time():
    time_ns = np.array(
        [0, int(3.6e12)],
        dtype=np.int64,
    )
    stage = np.array(
        [0.0, 2.0],
        dtype=float,
    )

    assert crossing_times(
        time_ns,
        stage,
        1.0,
    ) == [int(1.8e12)]


def test_same_event_counts_once_at_stage():
    flagged = pd.DataFrame([
        {
            "event_id": "A",
            "window_lower_ft": 1.0,
            "window_upper_ft": 3.0,
            "high_first": True,
            "high_second": True,
        },
        {
            "event_id": "A",
            "window_lower_ft": 2.0,
            "window_upper_ft": 4.0,
            "high_first": True,
            "high_second": True,
        },
        {
            "event_id": "B",
            "window_lower_ft": 2.0,
            "window_upper_ft": 4.0,
            "high_first": True,
            "high_second": True,
        },
    ])

    regions = event_regions(flagged)
    ranking = recurrence_by_overlap(regions)

    at_25 = ranking.loc[
        ranking["stage_lower_ft"].le(2.5)
        & ranking["stage_upper_ft"].gt(2.5)
    ]

    assert len(at_25) == 1
    assert int(
        at_25.iloc[0][
            "events_high_both"
        ]
    ) == 2


def test_concentration_plateau_midpoint():
    ranking = pd.DataFrame([
        {
            "stage_lower_ft": 1.0,
            "stage_upper_ft": 2.0,
            "events_high_both": 2,
        },
        {
            "stage_lower_ft": 2.0,
            "stage_upper_ft": 3.0,
            "events_high_both": 4,
        },
        {
            "stage_lower_ft": 3.0,
            "stage_upper_ft": 4.0,
            "events_high_both": 4,
        },
        {
            "stage_lower_ft": 4.0,
            "stage_upper_ft": 5.0,
            "events_high_both": 2,
        },
    ])

    peaks = recurrence_concentrations(
        ranking
    )

    assert len(peaks) == 1
    assert peaks.iloc[0][
        "height_ft"
    ] == 3.0
    assert peaks.iloc[0][
        "joint_events"
    ] == 4
