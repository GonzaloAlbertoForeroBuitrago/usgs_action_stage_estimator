"""NOAA National Water Prediction Service gauge reference client.

Retrieves flood categories, gauge identifiers, datum metadata,
historical crests, and flood impacts.

No hydrological threshold estimation is performed here.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


NOAA_API_BASE = "https://api.water.noaa.gov/nwps/v1/gauges"

FLOOD_CATEGORIES = ("action", "minor", "moderate", "major")


class NOAAAPIError(RuntimeError):
    """NOAA request or response validation failed."""


def _valid_number(value):
    """Convert finite NOAA numeric values; reject missing sentinels."""
    if value is None or isinstance(value, bool):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number) or number == -9999:
        return None

    return number


def fetch_noaa_gauge(
    nws_lid: str,
    *,
    timeout: float = 20.0,
) -> dict:
    """Retrieve a NOAA gauge record using its NWS location identifier."""

    lid = str(nws_lid).strip().upper()

    if not lid or not lid.isalnum():
        raise ValueError("Invalid NWS location identifier.")

    if not 0 < timeout <= 120:
        raise ValueError("timeout must be between 0 and 120 seconds.")

    url = f"{NOAA_API_BASE}/{quote(lid, safe='')}"

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "usgs-action-stage-estimator/0.1",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)

    except HTTPError as exc:
        raise NOAAAPIError(
            f"NOAA HTTP error {exc.code} for {lid}"
        ) from exc

    except (URLError, TimeoutError, OSError) as exc:
        raise NOAAAPIError(
            f"NOAA request failed for {lid}: {exc}"
        ) from exc

    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise NOAAAPIError(
            f"Invalid NOAA JSON response for {lid}"
        ) from exc

    if not isinstance(payload, dict):
        raise NOAAAPIError("NOAA response must be a JSON object.")

    returned_lid = str(payload.get("lid") or "").strip().upper()

    if returned_lid != lid:
        raise NOAAAPIError(
            f"NWS LID mismatch: requested {lid}, received {returned_lid}"
        )

    return payload


def normalize_noaa_gauge(
    payload: dict,
    *,
    expected_usgs_id: str | None = None,
) -> dict:
    """Normalize NOAA gauge metadata and flood reference information."""

    if not isinstance(payload, dict):
        raise ValueError("NOAA payload must be a dictionary.")

    usgs_id = str(payload.get("usgsId") or "").strip()

    if expected_usgs_id is not None:
        expected = str(expected_usgs_id).strip().zfill(8)

        if usgs_id != expected:
            raise NOAAAPIError(
                f"USGS ID mismatch: expected {expected}, got {usgs_id}"
            )

    flood = payload.get("flood") or {}
    categories = flood.get("categories") or {}

    stage_units = flood.get("stageUnits")
    flow_units = flood.get("flowUnits")

    if stage_units != "ft":
        raise NOAAAPIError(
            f"Unexpected stage units: {stage_units!r}"
        )

    normalized_categories = {}

    for category in FLOOD_CATEGORIES:
        values = categories.get(category) or {}

        normalized_categories[category] = {
            "stage_ft": _valid_number(values.get("stage")),
            "flow_cfs": (
                _valid_number(values.get("flow"))
                if flow_units == "cfs"
                else None
            ),
        }

    crests = flood.get("crests") or {}

    historical_crests = []

    for crest_group in ("historic", "recent"):
        for crest in crests.get(crest_group) or []:
            historical_crests.append({
                "crest_group": crest_group,
                "occurred_at_utc": crest.get("occurredTime"),
                "stage_ft": _valid_number(crest.get("stage")),
                "flow_cfs": (
                    _valid_number(crest.get("flow"))
                    if flow_units == "cfs"
                    else None
                ),
                "preliminary": crest.get("preliminary"),
                "old_datum": crest.get("olddatum"),
                "flow_reported_cfs": (
                    _valid_number(crest.get("flow"))
                    if flow_units == "cfs"
                    else None
                ),
                "flow_quality_status": (
                    "unavailable"
                    if flow_units != "cfs"
                    or _valid_number(crest.get("flow")) is None
                    else (
                        "zero_reported_unverified"
                        if _valid_number(crest.get("flow")) == 0
                        else "reported_positive"
                        if _valid_number(crest.get("flow")) > 0
                        else "reported_negative_unverified"
                    )
                ),
            })

    # Historic and recent collections may contain the same crest.
    unique_crests = {}

    for crest in historical_crests:
        key = (
            crest["occurred_at_utc"],
            crest["stage_ft"],
        )

        if key not in unique_crests:
            unique_crests[key] = {
                **crest,
                "crest_groups": [crest["crest_group"]],
            }
        else:
            groups = unique_crests[key]["crest_groups"]
            if crest["crest_group"] not in groups:
                groups.append(crest["crest_group"])

    impacts = []

    for impact in flood.get("impacts") or []:
        impacts.append({
            "stage_ft": _valid_number(impact.get("stage")),
            "description": impact.get("statement"),
        })

    return {
        "site_id": usgs_id or None,
        "nws_lid": payload.get("lid"),
        "reference_source": "NOAA_NWPS_API",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage_units": stage_units,
        "flow_units": flow_units,
        "flood_categories": normalized_categories,
        "vertical_datum": (
            payload.get("datums") or {}
        ).get("vertical"),
        "historical_crests": list(unique_crests.values()),
        "flood_impacts": impacts,
    }
