"""Tests for the E00 station inventory."""

import json

import pandas as pd
import pytest

from usgs_action_stage_estimator.station_inventory import (
    build_station_inventory,
)


def test_inventory_with_and_without_reference(tmp_path):
    processing = tmp_path / "processing"
    reference_path = tmp_path / "references.csv"

    for site_id, count in [
        ("08165500", 120),
        ("08165501", 80),
    ]:
        station = processing / "TEXAS" / site_id
        station.mkdir(parents=True)

        manifest = {
            "schema_version": 1,
            "package": "usgs-stage-peaks",
            "parameters": {
                "max_interval_minutes": 60,
                "baseflow_alpha": 0.987,
            },
            "counts": {
                "observations": 1000,
                "segments": 3,
                "detected_events": count,
                "peak_candidates": count + 5,
                "top_selected": 100,
            },
        }

        (station / "processing_manifest.json").write_text(
            json.dumps(manifest)
        )

    references = pd.DataFrame([{
        "site_id": "08165500",
        "action_stage_original_ft": 12.0,
        "action_stage_corrected_ft": 12.0,
        "reference_compatible": True,
        "action_comparison_eligible": True,
        "validation_status": "reference_compatible",
        "correction_applied": False,
        "nws_lid": "TEST1",
        "station_name": "Test station",
        "latitude": 30.0,
        "longitude": -98.0,
        "state": "TEXAS",
        "inventory_action_stage_ft": 12.0,
        "noaa_minus_usgs_ft": 0.0,
        "harmonization_status": "recent_offset_applied",
        "qc_status": "stable_recent_offset",
        "vertical_datum": "NAVD88",
        "source": "synthetic_test",
    }])

    references.to_csv(reference_path, index=False)

    inventory = build_station_inventory(
        processing,
        reference_path,
    )

    assert len(inventory) == 2
    assert inventory["site_id"].is_unique

    known = inventory.set_index("site_id").loc["08165500"]
    unknown = inventory.set_index("site_id").loc["08165501"]

    assert known["peak_candidate_count"] == 125
    assert known["validated_action_stage_ft"] == 12.0
    assert known["has_compatible_action_stage"]

    assert unknown["peak_candidate_count"] == 85
    assert pd.isna(unknown["validated_action_stage_ft"])
    assert not unknown["has_compatible_action_stage"]


def test_missing_processing_directory(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_station_inventory(
            tmp_path / "missing",
            tmp_path / "references.csv",
        )
