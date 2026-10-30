"""Export E01 peak-distribution results for analysis and visualization."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pandas as pd

from .identifiers import validate_site_id
from .peak_distributions import (
    calculate_peak_distributions,
    calculate_rise_sensitivity,
    compare_action_stage,
)


def _write_parquet_atomic(data: pd.DataFrame, destination: Path) -> None:
    """Write a Parquet file without exposing partial output."""

    with tempfile.NamedTemporaryFile(
        dir=destination.parent,
        suffix=".parquet",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)

    try:
        data.to_parquet(temporary_path, index=False)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def export_peak_distributions(
    candidates: pd.DataFrame,
    output_root: str | Path,
    *,
    state: str,
    site_id: str,
    action_stage_ft: float | None = None,
) -> Path:
    """Export independent E01 calculations and optional NOAA comparison."""

    site_id = validate_site_id(site_id)

    station_dir = Path(output_root) / state / site_id
    station_dir.mkdir(parents=True, exist_ok=True)

    distributions = calculate_peak_distributions(candidates)
    sensitivity = calculate_rise_sensitivity(candidates)

    _write_parquet_atomic(
        distributions,
        station_dir / "peak_distribution_summary.parquet",
    )

    _write_parquet_atomic(
        sensitivity,
        station_dir / "peak_distribution_sensitivity.parquet",
    )

    comparison_path = station_dir / "action_stage_comparison.parquet"

    if action_stage_ft is not None:
        comparison = compare_action_stage(
            candidates,
            action_stage_ft,
        )

        _write_parquet_atomic(
            comparison,
            comparison_path,
        )

    metadata = {
        "schema_version": 1,
        "experiment": "E01",
        "site_id": site_id,
        "state": state,
        "candidate_count": len(candidates),
        "action_stage_comparison_included": (
            action_stage_ft is not None
        ),
        "action_stage_ft": action_stage_ft,
    }

    destination = station_dir / "peak_distribution_metadata.json"

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=station_dir,
        suffix=".json",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        json.dump(metadata, temporary, indent=2)
        temporary.write("\n")

    try:
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)

    if action_stage_ft is None:
        comparison_path.unlink(missing_ok=True)

    return station_dir
