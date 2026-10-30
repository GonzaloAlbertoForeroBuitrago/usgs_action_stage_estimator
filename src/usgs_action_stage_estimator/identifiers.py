"""Preserve USGS station identifiers exactly as supplied."""

from __future__ import annotations


def validate_site_id(site_id: str) -> str:
    """Validate a USGS station ID without changing its representation."""
    if not isinstance(site_id, str):
        raise TypeError("USGS station ID must be a string.")

    if not site_id:
        raise ValueError("USGS station ID cannot be empty.")

    if not site_id.isascii() or not site_id.isdigit():
        raise ValueError("USGS station ID must contain ASCII digits.")

    return site_id
