"""Tests for exact USGS station identifier preservation."""

import pytest

from usgs_action_stage_estimator.identifiers import validate_site_id


@pytest.mark.parametrize(
    "site_id",
    [
        "08165500",
        "01011500",
        "0136230002",
        "384037104472001",
        "001",
        "1",
    ],
)
def test_preserves_original_identifier(site_id):
    assert validate_site_id(site_id) == site_id


@pytest.mark.parametrize(
    "site_id",
    [
        8165500,
        None,
        "",
        "08165500 ",
        " 08165500",
        "ABC123",
    ],
)
def test_rejects_invalid_identifier(site_id):
    with pytest.raises((TypeError, ValueError)):
        validate_site_id(site_id)


def test_noaa_normalization_preserves_long_identifier():
    from usgs_action_stage_estimator.noaa_api import (
        normalize_noaa_gauge,
    )

    site_id = "384037104472001"

    payload = {
        "lid": "TEST1",
        "usgsId": site_id,
        "flood": {
            "stageUnits": "ft",
            "flowUnits": "cfs",
            "categories": {
                "action": {"stage": 10.0, "flow": None},
            },
        },
    }

    result = normalize_noaa_gauge(
        payload,
        expected_usgs_id=site_id,
    )

    assert result["site_id"] == site_id


def test_export_preserves_long_identifier(tmp_path):
    from usgs_action_stage_estimator.flood_reference_export import (
        export_flood_references,
    )

    site_id = "384037104472001"

    result = {
        "site_id": site_id,
        "nws_lid": "TEST1",
        "status": "datum_review_required",
        "action_stage_ft": 10.0,
        "reference_source": "NOAA_NWPS_API",
        "flood_categories": {
            "action": {"stage_ft": 10.0, "flow_cfs": None},
        },
        "historical_crests": [],
        "flood_impacts": [],
    }

    station_dir = export_flood_references(
        result,
        tmp_path,
        state="COLORADO",
    )

    assert station_dir.name == site_id
    assert station_dir.is_dir()
