"""Tests for API-first Action Stage reference lookup."""

import pandas as pd
import pytest

from usgs_action_stage_estimator.noaa_api import NOAAAPIError
from usgs_action_stage_estimator.reference_lookup import (
    get_action_stage,
)


@pytest.fixture
def reference_table(tmp_path):
    path = tmp_path / "references.parquet"

    pd.DataFrame([
        {
            "site_id": "08165500",
            "nws_lid": "HNTT2",
            "reference_eligible": True,
            "validated_action_stage_ft": 10.0,
            "action_stage_original_ft": 10.0,
            "validation_status": "reference_compatible",
        },
        {
            "site_id": "08165501",
            "nws_lid": "TEST2",
            "reference_eligible": False,
            "validated_action_stage_ft": None,
            "action_stage_original_ft": 15.0,
            "validation_status": "provisional",
        },
    ]).to_parquet(path, index=False)

    return path


def api_payload(lid="HNTT2", usgs_id="08165500", action=10):
    return {
        "lid": lid,
        "usgsId": usgs_id,
        "flood": {
            "stageUnits": "ft",
            "flowUnits": "cfs",
            "categories": {
                "action": {"stage": action, "flow": -9999},
            },
        },
    }


def test_matching_reference(reference_table, monkeypatch):
    monkeypatch.setattr(
        "usgs_action_stage_estimator.reference_lookup.fetch_noaa_gauge",
        lambda lid, timeout: api_payload(),
    )

    result = get_action_stage("08165500", reference_table)

    assert result["status"] == "historically_compatible"
    assert result["action_stage_ft"] == 10.0
    assert result["nws_lid"] == "HNTT2"


def test_changed_action_stage(reference_table, monkeypatch):
    monkeypatch.setattr(
        "usgs_action_stage_estimator.reference_lookup.fetch_noaa_gauge",
        lambda lid, timeout: api_payload(action=11),
    )

    result = get_action_stage("08165500", reference_table)

    assert result["status"] == "datum_review_required"
    assert result["action_stage_ft"] == 11.0


def test_missing_api_action_stage(reference_table, monkeypatch):
    monkeypatch.setattr(
        "usgs_action_stage_estimator.reference_lookup.fetch_noaa_gauge",
        lambda lid, timeout: api_payload(action=-9999),
    )

    result = get_action_stage("08165500", reference_table)

    assert result["status"] == "reference_unavailable"
    assert result["action_stage_ft"] is None


def test_api_failure(reference_table, monkeypatch):
    def fail(lid, timeout):
        raise NOAAAPIError("Service unavailable")

    monkeypatch.setattr(
        "usgs_action_stage_estimator.reference_lookup.fetch_noaa_gauge",
        fail,
    )

    result = get_action_stage("08165500", reference_table)

    assert result["status"] == "api_error"
    assert result["action_stage_ft"] is None
    assert result["historical_action_stage_ft"] == 10.0


def test_missing_station(reference_table):
    result = get_action_stage("08165502", reference_table)

    assert result["status"] == "not_in_inventory"
    assert result["action_stage_ft"] is None


def test_invalid_station_id(reference_table):
    with pytest.raises(ValueError):
        get_action_stage("INVALID", reference_table)
