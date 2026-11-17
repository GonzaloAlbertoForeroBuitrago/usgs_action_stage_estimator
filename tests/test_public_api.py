"""Tests for the intentionally small public package API."""

import inspect

import usgs_action_stage_estimator as package


def test_recurrent_stage_is_public_and_reference_free():
    assert callable(package.estimate_recurrent_stage)
    assert callable(package.get_action_stage)
    assert callable(package.assess_stage_reference_scale)

    parameters = set(
        inspect.signature(
            package.estimate_recurrent_stage
        ).parameters
    )

    assert "action_stage" not in parameters
    assert "action_stage_ft" not in parameters
    assert "noaa" not in parameters


def test_public_methodology_version_matches_v15():
    assert (
        package.RECURRENT_STAGE_METHODOLOGY_VERSION
        == "E03-RS-V15-p50-d50-top3-RI-v1"
    )
