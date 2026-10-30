"""Build a national station inventory from existing processing outputs.

The inventory preserves historical processing counts and joins optional
Action Stage reference metadata. It does not estimate thresholds.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .reference_validation import clean_action_stage_references


def build_station_inventory(
    processing_root: str | Path,
    reference_csv: str | Path,
) -> pd.DataFrame:
    """Inventory processed stations and optional Action Stage references."""

    processing_root = Path(processing_root)
    reference_csv = Path(reference_csv)

    if not processing_root.is_dir():
        raise FileNotFoundError(processing_root)

    if not reference_csv.is_file():
        raise FileNotFoundError(reference_csv)

    records = []

    for manifest_path in sorted(
        processing_root.glob("*/*/processing_manifest.json")
    ):
        station_dir = manifest_path.parent

        with manifest_path.open() as file:
            manifest = json.load(file)

        counts = manifest.get("counts", {})
        parameters = manifest.get("parameters", {})

        site_id = station_dir.name.zfill(8)

        records.append({
            "site_id": site_id,
            "state": station_dir.parent.name,
            "observation_count": counts.get("observations"),
            "segment_count": counts.get("segments"),
            "detected_event_count": counts.get("detected_events"),
            "peak_candidate_count": counts.get("peak_candidates"),
            "selected_peak_count": counts.get("top_selected"),
            "max_interval_minutes": parameters.get(
                "max_interval_minutes"
            ),
            "baseflow_alpha": parameters.get("baseflow_alpha"),
            "source_processing_directory": str(station_dir.resolve()),
            "source_schema_version": manifest.get("schema_version"),
            "source_package": manifest.get("package"),
            "source_processing_version": "historical_v020",
        })

    inventory = pd.DataFrame.from_records(records)

    if inventory.empty:
        raise ValueError("No station processing manifests found.")

    if inventory["site_id"].duplicated().any():
        raise ValueError("Duplicate processed station IDs.")

    references = clean_action_stage_references(reference_csv)

    reference_columns = [
        "site_id",
        "station_name",
        "nws_lid",
        "action_stage_original_ft",
        "action_stage_corrected_ft",
        "validated_action_stage_ft",
        "reference_compatible",
        "action_comparison_eligible",
        "reference_eligible",
        "validation_status",
        "correction_applied",
        "latitude",
        "longitude",
    ]

    references = references[reference_columns].copy()

    inventory = inventory.merge(
        references,
        on="site_id",
        how="left",
        validate="one_to_one",
    )

    inventory["has_compatible_action_stage"] = (
        inventory["reference_eligible"]
        .astype("boolean")
        .fillna(False)
        .astype(bool)
    )

    return (
        inventory.sort_values(["state", "site_id"])
        .reset_index(drop=True)
    )
