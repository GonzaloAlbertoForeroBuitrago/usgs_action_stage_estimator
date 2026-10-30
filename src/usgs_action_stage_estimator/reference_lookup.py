"""API-first NOAA Action Stage lookup using a historical USGS/NWS crosswalk."""

from __future__ import annotations

from .identifiers import validate_site_id

import math
from pathlib import Path
from importlib.resources import files

import pandas as pd

from .noaa_api import (
    NOAAAPIError,
    fetch_noaa_gauge,
    normalize_noaa_gauge,
)


def _stage_number(value):
    if value is None or pd.isna(value):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def get_action_stage(
    site_id: str,
    reference_table: str | Path | None = None,
    *,
    timeout: float = 20.0,
) -> dict:
    """Retrieve NOAA Action Stage and historical compatibility evidence.

    The API value is not an experimental threshold estimate.
    """

    site_id = validate_site_id(site_id)

    if reference_table is None:
        resource = files(
            "usgs_action_stage_estimator"
        ).joinpath("data/action_stage_references.parquet")

        with resource.open("rb") as file:
            references = pd.read_parquet(file)
    else:
        path = Path(reference_table)

        if not path.is_file():
            raise FileNotFoundError(path)

        references = pd.read_parquet(path)

    required = {
        "site_id",
        "nws_lid",
        "reference_eligible",
        "validated_action_stage_ft",
        "action_stage_original_ft",
        "validation_status",
    }

    missing = required - set(references.columns)

    if missing:
        raise ValueError(
            f"Missing reference columns: {sorted(missing)}"
        )

    ids = references["site_id"].astype("string")

    matching = references.loc[ids == site_id]

    if len(matching) > 1:
        raise ValueError("Duplicate reference records.")

    result = {
        "site_id": site_id,
        "status": None,
        "action_stage_ft": None,
        "historical_action_stage_ft": None,
        "historical_validation_status": None,
        "nws_lid": None,
        "reference_source": None,
        "retrieved_at_utc": None,
        "flood_categories": None,
        "vertical_datum": None,
        "historical_crests": [],
        "flood_impacts": [],
        "message": None,
    }

    if matching.empty:
        result["status"] = "not_in_inventory"
        result["message"] = (
            "No NOAA station mapping is available for this USGS "
            "station in the current reference inventory."
        )
        return result

    record = matching.iloc[0]

    result["historical_action_stage_ft"] = _stage_number(
        record["action_stage_original_ft"]
    )
    result["historical_validation_status"] = record[
        "validation_status"
    ]

    lid = record["nws_lid"]

    if pd.isna(lid) or not str(lid).strip():
        result["status"] = "mapping_unavailable"
        result["message"] = (
            "No NWS location identifier is available for this station."
        )
        return result

    lid = str(lid).strip().upper()
    result["nws_lid"] = lid

    try:
        payload = fetch_noaa_gauge(lid, timeout=timeout)
        normalized = normalize_noaa_gauge(
            payload,
            expected_usgs_id=site_id,
        )
    except NOAAAPIError as exc:
        result["status"] = "api_error"
        result["message"] = str(exc)
        return result

    result.update({
        "reference_source": normalized["reference_source"],
        "retrieved_at_utc": normalized["retrieved_at_utc"],
        "flood_categories": normalized["flood_categories"],
        "vertical_datum": normalized["vertical_datum"],
        "historical_crests": normalized["historical_crests"],
        "flood_impacts": normalized["flood_impacts"],
    })

    action = normalized["flood_categories"]["action"]["stage_ft"]

    if action is None:
        result["status"] = "reference_unavailable"
        result["message"] = (
            "NOAA returned no valid Action Stage for this station."
        )
        return result

    result["action_stage_ft"] = action

    historical = _stage_number(
        record["validated_action_stage_ft"]
    )

    eligible = record["reference_eligible"]

    is_eligible = (
        pd.notna(eligible)
        and str(eligible).strip().lower() == "true"
    )

    # Agreement is a consistency check, not a new datum validation.
    if (
        is_eligible
        and historical is not None
        and abs(action - historical) <= 0.01
    ):
        result["status"] = "historically_compatible"
        result["message"] = (
            "Current NOAA Action Stage agrees with the previously "
            "validated USGS-compatible reference."
        )
    else:
        result["status"] = "datum_review_required"
        result["message"] = (
            "NOAA Action Stage is available, but its current "
            "compatibility with the USGS reference requires review."
        )

    return result
