"""Export NOAA flood references for station-level analysis and Tethys.

Each station has one set of reference files under STATE/SITE_ID.
No USGS observations or experimental estimates are duplicated.
"""

from __future__ import annotations

from .identifiers import validate_site_id

import json
import os
import tempfile
from pathlib import Path

import pandas as pd


def _write_json(path: Path, data: dict) -> None:
    """Atomically replace a JSON file after successful serialization."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)

        try:
            json.dump(data, temporary, indent=2, allow_nan=False)
            temporary.write("\n")
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise

    os.replace(temporary_path, path)


def _write_parquet(path: Path, data: pd.DataFrame) -> None:
    """Atomically replace a Parquet file."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        suffix=".parquet",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)

    try:
        data.to_parquet(temporary_path, index=False)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def export_flood_references(
    result: dict,
    output_root: str | Path,
    *,
    state: str,
) -> Path:
    """Export normalized NOAA reference information for one station."""

    if result.get("reference_source") != "NOAA_NWPS_API":
        raise ValueError("A successful NOAA API response is required.")

    site_id = validate_site_id(result["site_id"])

    state = str(state).strip().upper()

    if not state or not all(
        char.isascii() and (char.isupper() or char == "_")
        for char in state
    ):
        raise ValueError("Invalid state directory name.")

    station_dir = Path(output_root) / state / site_id

    categories = result.get("flood_categories") or {}

    metadata = {
        "site_id": site_id,
        "state": state,
        "nws_lid": result.get("nws_lid"),
        "reference_status": result.get("status"),
        "action_stage_ft": result.get("action_stage_ft"),
        "historical_action_stage_ft": result.get(
            "historical_action_stage_ft"
        ),
        "historical_validation_status": result.get(
            "historical_validation_status"
        ),
        "reference_source": result["reference_source"],
        "retrieved_at_utc": result.get("retrieved_at_utc"),
        "vertical_datum": result.get("vertical_datum"),
        "message": result.get("message"),
    }

    crests = pd.DataFrame(
        result.get("historical_crests") or [],
        columns=[
            "crest_group",
            "occurred_at_utc",
            "stage_ft",
            "flow_cfs",
            "preliminary",
            "old_datum",
            "crest_groups",
            "flow_reported_cfs",
            "flow_quality_status",
        ],
    )

    impacts = pd.DataFrame(
        result.get("flood_impacts") or [],
        columns=["stage_ft", "description"],
    )

    # Prepare the data before changing any destination file.
    station_dir.mkdir(parents=True, exist_ok=True)

    _write_json(station_dir / "station_metadata.json", metadata)
    _write_json(station_dir / "flood_categories.json", categories)
    _write_parquet(station_dir / "historical_crests.parquet", crests)
    _write_parquet(station_dir / "flood_impacts.parquet", impacts)

    manifest = {
        "schema_version": 1,
        "site_id": site_id,
        "state": state,
        "reference_source": result["reference_source"],
        "retrieved_at_utc": result.get("retrieved_at_utc"),
        "reference_status": result.get("status"),
        "counts": {
            "historical_crests": len(crests),
            "flood_impacts": len(impacts),
        },
        "files": [
            "station_metadata.json",
            "flood_categories.json",
            "historical_crests.parquet",
            "flood_impacts.parquet",
        ],
    }

    _write_json(
        station_dir / "analysis_manifest.json",
        manifest,
    )

    return station_dir
