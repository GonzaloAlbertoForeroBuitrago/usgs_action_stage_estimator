"""Tests for station-level NOAA flood reference exports."""

import json

import pandas as pd
import pytest

from usgs_action_stage_estimator.flood_reference_export import (
    export_flood_references,
)


@pytest.fixture
def sample_result():
    return {
        "site_id": "08165500",
        "nws_lid": "HNTT2",
        "status": "historically_compatible",
        "action_stage_ft": 10.0,
        "historical_action_stage_ft": 10.0,
        "historical_validation_status": "reference_compatible",
        "reference_source": "NOAA_NWPS_API",
        "retrieved_at_utc": "2026-10-30T20:00:00+00:00",
        "vertical_datum": {"value": []},
        "message": "Compatible historical reference.",
        "flood_categories": {
            "action": {"stage_ft": 10.0, "flow_cfs": None},
            "minor": {"stage_ft": 10.0, "flow_cfs": 1450.0},
        },
        "historical_crests": [{
            "crest_group": "historic",
            "occurred_at_utc": "2025-07-04T10:10:00Z",
            "stage_ft": 37.52,
            "flow_cfs": 0.0,
            "preliminary": "P",
            "old_datum": False,
            "crest_groups": ["historic", "recent"],
        }],
        "flood_impacts": [{
            "stage_ft": 10.0,
            "description": "Water extends into low areas.",
        }],
    }


def test_export_creates_expected_files(tmp_path, sample_result):
    station_dir = export_flood_references(
        sample_result,
        tmp_path,
        state="TEXAS",
    )

    assert station_dir == tmp_path / "TEXAS" / "08165500"

    expected = {
        "station_metadata.json",
        "flood_categories.json",
        "historical_crests.parquet",
        "flood_impacts.parquet",
        "analysis_manifest.json",
    }

    assert {p.name for p in station_dir.iterdir()} == expected

    metadata = json.loads(
        (station_dir / "station_metadata.json").read_text()
    )

    assert metadata["action_stage_ft"] == 10.0

    crests = pd.read_parquet(
        station_dir / "historical_crests.parquet"
    )

    assert len(crests) == 1
    assert crests.iloc[0]["stage_ft"] == 37.52

    impacts = pd.read_parquet(
        station_dir / "flood_impacts.parquet"
    )

    assert len(impacts) == 1


def test_invalid_state_rejected(tmp_path, sample_result):
    with pytest.raises(ValueError):
        export_flood_references(
            sample_result,
            tmp_path,
            state="../TEXAS",
        )


def test_missing_api_source_rejected(tmp_path, sample_result):
    sample_result["reference_source"] = None

    with pytest.raises(ValueError):
        export_flood_references(
            sample_result,
            tmp_path,
            state="TEXAS",
        )
