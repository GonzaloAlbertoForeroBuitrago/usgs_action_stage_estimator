"""Tests for NOAA gauge response normalization."""

import pytest

from usgs_action_stage_estimator.noaa_api import (
    NOAAAPIError,
    normalize_noaa_gauge,
)


@pytest.fixture
def sample_response():
    return {
        "lid": "HNTT2",
        "usgsId": "08165500",
        "flood": {
            "stageUnits": "ft",
            "flowUnits": "cfs",
            "categories": {
                "action": {"stage": 10, "flow": -9999},
                "minor": {"stage": 10, "flow": 1450},
                "moderate": {"stage": 12, "flow": 4750},
                "major": {"stage": 22, "flow": -9999},
            },
            "crests": {
                "historic": [{
                    "occurredTime": "2025-07-04T10:10:00Z",
                    "stage": 37.52,
                    "flow": 0,
                    "preliminary": "P",
                    "olddatum": False,
                }],
                "recent": [{
                    "occurredTime": "2025-07-04T10:10:00Z",
                    "stage": 37.52,
                    "flow": 0,
                    "preliminary": "P",
                    "olddatum": False,
                }],
            },
            "impacts": [{
                "stage": 10,
                "statement": "Water extends into low floodplain areas.",
            }],
        },
        "datums": {
            "vertical": {
                "value": [{
                    "abbrev": "NAVD88",
                    "value": 1722.82,
                }],
            },
        },
    }


def test_flood_categories(sample_response):
    result = normalize_noaa_gauge(
        sample_response,
        expected_usgs_id="08165500",
    )

    assert result["flood_categories"]["action"]["stage_ft"] == 10
    assert result["flood_categories"]["moderate"]["stage_ft"] == 12
    assert result["flood_categories"]["action"]["flow_cfs"] is None


def test_duplicate_crests_are_merged(sample_response):
    result = normalize_noaa_gauge(sample_response)

    assert len(result["historical_crests"]) == 1

    crest = result["historical_crests"][0]

    assert crest["stage_ft"] == 37.52
    assert set(crest["crest_groups"]) == {"historic", "recent"}


def test_impacts_and_datum_preserved(sample_response):
    result = normalize_noaa_gauge(sample_response)

    assert len(result["flood_impacts"]) == 1
    assert result["flood_impacts"][0]["stage_ft"] == 10
    assert result["vertical_datum"]["value"][0]["abbrev"] == "NAVD88"


def test_usgs_identifier_mismatch(sample_response):
    with pytest.raises(NOAAAPIError):
        normalize_noaa_gauge(
            sample_response,
            expected_usgs_id="08165501",
        )


def test_invalid_stage_units(sample_response):
    sample_response["flood"]["stageUnits"] = "m"

    with pytest.raises(NOAAAPIError):
        normalize_noaa_gauge(sample_response)
