"""Tests for stage-reference scale diagnostics."""

import numpy as np
import pandas as pd
import pytest

from usgs_action_stage_estimator.reference_validation import (
    assess_stage_reference_scale,
)


def test_stage_reference_scale_inside_observed_range():
    result = assess_stage_reference_scale(
        pd.Series([1.0, 2.0, 3.0, 4.0]),
        3.5,
    )
    assert result["diagnostic_status"] == "inside_observed_stage_range"
    assert result["action_within_observed_minmax"] is True


def test_stage_reference_scale_within_margin():
    result = assess_stage_reference_scale(
        [1.0, 2.0, 3.0, 4.0],
        8.0,
        margin_ft=5.0,
    )
    assert result["diagnostic_status"] == "within_observed_stage_range_margin"
    assert result["action_within_observed_minmax"] is False
    assert result["action_within_observed_minmax_plus_margin"] is True


def test_stage_reference_scale_requires_review():
    result = assess_stage_reference_scale(
        [1.0, 2.0, 3.0, 4.0],
        100.0,
    )
    assert result["diagnostic_status"] == "reference_scale_review_required"
    assert result["action_within_observed_minmax_plus_margin"] is False
    assert result["action_minus_stage_median_ft"] == 97.5


def test_stage_reference_scale_ignores_nonfinite_stage_values():
    result = assess_stage_reference_scale(
        [1.0, np.nan, np.inf, 3.0],
        2.0,
    )
    assert result["stage_rows"] == 2
    assert result["stage_min_ft"] == 1.0
    assert result["stage_max_ft"] == 3.0


def test_stage_reference_scale_rejects_invalid_values():
    with pytest.raises(ValueError):
        assess_stage_reference_scale([1.0, 2.0], np.nan)

    with pytest.raises(ValueError):
        assess_stage_reference_scale(
            [1.0, 2.0],
            2.0,
            margin_ft=-1,
        )
