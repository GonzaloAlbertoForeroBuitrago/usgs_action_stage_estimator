"""Tests for E01 research output export."""

import json

import pandas as pd
import pytest

from usgs_action_stage_estimator.peak_distribution_export import (
    export_peak_distributions,
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


def test_export_preserves_station_identifier(tmp_path, candidates):
    site_id = "384037104472001"

    directory = export_peak_distributions(
        candidates,
        tmp_path,
        state="COLORADO",
        site_id=site_id,
        action_stage_ft=10.0,
    )

    assert directory.name == site_id

    metadata = json.loads(
        (directory / "peak_distribution_metadata.json").read_text()
    )

    assert metadata["site_id"] == site_id
    assert metadata["candidate_count"] == 4
    assert (directory / "action_stage_comparison.parquet").is_file()


def test_export_without_reference(tmp_path, candidates):
    directory = export_peak_distributions(
        candidates,
        tmp_path,
        state="TEXAS",
        site_id="08165500",
    )

    metadata = json.loads(
        (directory / "peak_distribution_metadata.json").read_text()
    )

    assert metadata["action_stage_comparison_included"] is False
    assert not (directory / "action_stage_comparison.parquet").exists()


def test_invalid_candidates_do_not_replace_existing_files(
    tmp_path, candidates
):
    directory = export_peak_distributions(
        candidates,
        tmp_path,
        state="TEXAS",
        site_id="08165500",
        action_stage_ft=10.0,
    )

    existing = (
        directory / "peak_distribution_summary.parquet"
    ).read_bytes()

    with pytest.raises(ValueError):
        export_peak_distributions(
            pd.DataFrame(),
            tmp_path,
            state="TEXAS",
            site_id="08165500",
            action_stage_ft=10.0,
        )

    assert (
        directory / "peak_distribution_summary.parquet"
    ).read_bytes() == existing


def test_reexport_without_reference_removes_stale_comparison(
    tmp_path, candidates
):
    directory = export_peak_distributions(
        candidates,
        tmp_path,
        state="TEXAS",
        site_id="08165500",
        action_stage_ft=10.0,
    )

    comparison = directory / "action_stage_comparison.parquet"

    assert comparison.is_file()

    export_peak_distributions(
        candidates,
        tmp_path,
        state="TEXAS",
        site_id="08165500",
        action_stage_ft=None,
    )

    assert not comparison.exists()

    metadata = json.loads(
        (directory / "peak_distribution_metadata.json").read_text()
    )

    assert metadata["action_stage_comparison_included"] is False
