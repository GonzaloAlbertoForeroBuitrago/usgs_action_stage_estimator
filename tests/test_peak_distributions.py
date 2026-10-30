"""Tests for E01 peak-stage distribution calculations."""

import pandas as pd
import pytest

from usgs_action_stage_estimator.peak_distributions import (
    prepare_peak_candidates,
    calculate_peak_distributions,
    calculate_rise_sensitivity,
    compare_action_stage,
)


@pytest.fixture
def candidates():
    return pd.DataFrame({
        "flow_peak": [8.0, 9.0, 10.0, 12.0],
        "flow_start": [7.5, 8.0, 9.0, None],
        "quick_stage_at_peak_ft": [0.3, 0.8, 0.9, 0.0],
        "candidate_type": [
            "detected_event",
            "detected_event",
            "detected_event",
            "segment_boundary_or_maximum",
        ],
        "event_status": [
            "complete",
            "complete",
            "right_censored",
            None,
        ],
    })


def test_prepare_preserves_candidates(candidates):
    result = prepare_peak_candidates(candidates)

    assert len(result) == 4
    assert result["is_detected_event"].sum() == 3
    assert result["is_complete_event"].sum() == 2
    assert result["event_rise_ft"].notna().sum() == 3


def test_distributions_preserve_populations(candidates):
    result = calculate_peak_distributions(candidates)

    selected = result.loc[
        (result["population"] == "detected_events")
        & (result["metric"] == "flow_peak")
    ].iloc[0]

    assert selected["candidate_count"] == 3
    assert selected["maximum"] == 10.0


def test_rise_sensitivity(candidates):
    result = calculate_rise_sensitivity(
        candidates,
        thresholds=(0.0, 1.0),
    )

    assert result["retained_events"].tolist() == [3, 2]


def test_action_stage_ecdf_and_ties(candidates):
    result = compare_action_stage(
        candidates,
        action_stage_ft=10.0,
        thresholds=(0.0,),
    )

    row = result.iloc[0]

    assert row["peaks_below_action"] == 2
    assert row["peaks_equal_action"] == 1
    assert row["peaks_above_action"] == 0
    assert row["peaks_at_or_above_action"] == 1
    assert row["action_ecdf_percentile"] == 100.0


def test_missing_columns_rejected():
    with pytest.raises(ValueError):
        prepare_peak_candidates(pd.DataFrame())


def test_invalid_action_stage_rejected(candidates):
    with pytest.raises(ValueError):
        compare_action_stage(candidates, float("nan"))
