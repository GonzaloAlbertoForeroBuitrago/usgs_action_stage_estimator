"""National USGS stage-processing source inventory.

Discovers existing observations without modifying source files.
Preserves exact USGS station identifiers.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from .identifiers import validate_site_id


SOURCE_FILENAME = "stage_hydroeventdetector.parquet"


def discover_stage_sources(
    source_root: str | Path,
) -> pd.DataFrame:
    """Discover and classify national stage observation files."""

    source_root = Path(source_root)

    if not source_root.is_dir():
        raise FileNotFoundError(source_root)

    records = []

    for path in sorted(
        source_root.glob(f"*/*/downloaded_data/{SOURCE_FILENAME}")
    ):
        state = path.parents[2].name
        site_id = validate_site_id(path.parents[1].name)

        record = {
            "state": state,
            "site_id": site_id,
            "source_path": str(path.resolve()),
            "source_rows": None,
            "source_size_bytes": path.stat().st_size,
            "source_status": None,
            "source_error": None,
        }

        try:
            parquet = pq.ParquetFile(path)
            columns = parquet.schema_arrow.names
            rows = parquet.metadata.num_rows

            if not {"datetime", "Stage_ft"}.issubset(columns):
                record["source_status"] = "invalid_schema"
                record["source_error"] = (
                    f"Unexpected columns: {columns}"
                )
            elif rows == 0:
                record["source_status"] = "empty_input"
            else:
                record["source_status"] = "ready"

            record["source_rows"] = rows

        except Exception as exc:
            record["source_status"] = "read_error"
            record["source_error"] = str(exc)

        records.append(record)

    inventory = pd.DataFrame.from_records(records)

    if inventory.empty:
        raise ValueError("No stage observation files found.")

    if inventory["site_id"].duplicated().any():
        raise ValueError("Duplicate USGS station identifiers.")

    return inventory.sort_values(
        ["state", "site_id"]
    ).reset_index(drop=True)


def fingerprint_source(source_path: str | Path) -> dict:
    """Calculate a reproducible fingerprint of one source file."""

    import hashlib

    path = Path(source_path)
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(
            lambda: file.read(8 * 1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return {
        "source_sha256": digest.hexdigest(),
        "source_size_bytes": path.stat().st_size,
    }


PROCESSING_PARAMETERS = {
    "max_interval_minutes": 60.0,
    "baseflow_alpha": 0.987,
    "filter_method": "forward",
    "peak_selection": "all",
    "peak_sort_by": "peak_stage",
    "top_n": 200,
    "peak_fraction": 0.5,
}


def validate_station_outputs(
    output_directory: str | Path,
    *,
    site_id: str,
    source_rows: int,
) -> dict:
    """Verify the saved v0.3.1 processing outputs."""

    import json
    import pyarrow.parquet as pq

    site_id = validate_site_id(site_id)
    directory = Path(output_directory)

    manifest_path = directory / "processing_manifest.json"

    if not manifest_path.is_file():
        raise ValueError("Processing manifest is missing.")

    manifest = json.loads(manifest_path.read_text())

    if manifest.get("site_id") != site_id:
        raise ValueError("Station identifier mismatch.")

    if manifest.get("package") != "usgs-stage-peaks":
        raise ValueError("Unexpected processing package.")

    if manifest.get("parameters") != PROCESSING_PARAMETERS:
        raise ValueError("Processing configuration mismatch.")

    if not manifest.get("observation_preservation_verified"):
        raise ValueError("Observation preservation not verified.")

    if not manifest.get("maximum_observed_stage_preserved"):
        raise ValueError("Maximum observed stage not preserved.")

    counts = manifest["counts"]

    expected_files = {
        "segments.parquet": "segments",
        "filtered_stage.parquet": "observations",
        "detected_events.parquet": "detected_events",
        "peak_candidates.parquet": "peak_candidates",
        "selected_peaks.parquet": "selected_peaks",
    }

    for filename, count_key in expected_files.items():
        path = directory / filename

        if not path.is_file():
            raise ValueError(f"Missing output: {filename}")

        actual_rows = pq.ParquetFile(path).metadata.num_rows

        if actual_rows != counts[count_key]:
            raise ValueError(f"Row-count mismatch: {filename}")

    if counts["observations"] != source_rows:
        raise ValueError("Source observation count mismatch.")

    filtered = pd.read_parquet(
        directory / "filtered_stage.parquet",
        columns=["filter_applied"],
    )

    actual_filtered = int(
        filtered["filter_applied"].fillna(False).astype(bool).sum()
    )

    if actual_filtered != counts["filtered_observations"]:
        raise ValueError("Applied-filter count mismatch.")

    if counts["selected_peaks"] != counts["peak_candidates"]:
        raise ValueError("Not all peak candidates were selected.")

    return manifest


def process_one_station(
    source_path: str | Path,
    output_root: str | Path,
    *,
    state: str,
    site_id: str,
) -> dict:
    """Process one station without overwriting existing outputs."""

    import time
    import pandas as pd
    import pyarrow.parquet as pq
    import usgs_stage_peaks

    import json

    site_id = validate_site_id(site_id)
    source_path = Path(source_path)

    if usgs_stage_peaks.__version__ != "0.3.1":
        raise RuntimeError("usgs-stage-peaks==0.3.1 is required.")

    if not source_path.is_file():
        return {
            "state": state,
            "site_id": site_id,
            "status": "missing_input",
        }

    source_rows = pq.ParquetFile(
        source_path
    ).metadata.num_rows

    if source_rows == 0:
        return {
            "state": state,
            "site_id": site_id,
            "status": "empty_input",
        }

    output = Path(output_root) / state / site_id

    if output.exists():
        try:
            manifest = validate_station_outputs(
                output,
                site_id=site_id,
                source_rows=source_rows,
            )

            provenance_path = output / "source_provenance.json"

            if not provenance_path.is_file():
                return {
                    "state": state,
                    "site_id": site_id,
                    "status": "provenance_missing",
                    "source_rows": source_rows,
                }

            provenance = json.loads(provenance_path.read_text())
            fingerprint = fingerprint_source(source_path)

            if (
                provenance.get("site_id") != site_id
                or provenance.get("processing_version") != "0.3.1"
                or provenance.get("parameters") != PROCESSING_PARAMETERS
                or provenance.get("source_sha256")
                != fingerprint["source_sha256"]
                or provenance.get("source_size_bytes")
                != fingerprint["source_size_bytes"]
            ):
                raise ValueError("Source provenance mismatch.")

        except (ValueError, KeyError, OSError) as exc:
            return {
                "state": state,
                "site_id": site_id,
                "status": "existing_output_invalid",
                "error": str(exc),
            }

        counts = manifest["counts"]

        return {
            "state": state,
            "site_id": site_id,
            "status": "already_completed",
            "source_rows": source_rows,
            "segments": counts["segments"],
            "detected_events": counts["detected_events"],
            "filtered_observations": counts["filtered_observations"],
            "unfiltered_observations": (
                source_rows - counts["filtered_observations"]
            ),
            "peak_candidates": counts["peak_candidates"],
            "selected_peaks": counts["selected_peaks"],
            "processing_version": "0.3.1",
        }

    import tempfile

    fingerprint_before = fingerprint_source(source_path)

    observations = pd.read_parquet(source_path)

    start = time.perf_counter()

    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=f".{site_id}_processing_",
        dir=output.parent,
    ) as temporary:
        staging = Path(temporary) / site_id

        usgs_stage_peaks.process_stage_station(
            observations,
            staging,
            site_id=site_id,
            save_outputs=True,
            **PROCESSING_PARAMETERS,
        )

        manifest = validate_station_outputs(
            staging,
            site_id=site_id,
            source_rows=source_rows,
        )

        fingerprint_after = fingerprint_source(source_path)

        if fingerprint_before != fingerprint_after:
            raise ValueError(
                "Source file changed during processing."
            )

        fingerprint = fingerprint_before

        provenance = {
            "schema_version": 1,
            "site_id": site_id,
            "source_sha256": fingerprint["source_sha256"],
            "source_size_bytes": fingerprint["source_size_bytes"],
            "processing_package": "usgs-stage-peaks",
            "processing_version": "0.3.1",
            "parameters": PROCESSING_PARAMETERS,
        }

        (staging / "source_provenance.json").write_text(
            json.dumps(provenance, indent=2) + "\n"
        )

        if output.exists():
            raise FileExistsError(
                f"Output appeared during processing: {output}"
            )

        staging.rename(output)

    elapsed = time.perf_counter() - start

    return {
        "state": state,
        "site_id": site_id,
        "status": "completed",
        "source_rows": source_rows,
        "segments": manifest["counts"]["segments"],
        "detected_events": manifest["counts"]["detected_events"],
        "filtered_observations": manifest["counts"]["filtered_observations"],
        "unfiltered_observations": (
            source_rows - manifest["counts"]["filtered_observations"]
        ),
        "peak_candidates": manifest["counts"]["peak_candidates"],
        "selected_peaks": manifest["counts"]["selected_peaks"],
        "processing_version": "0.3.1",
        "elapsed_seconds": round(elapsed, 3),
    }


def _process_stage_inventory_unlocked(
    inventory: pd.DataFrame,
    output_root: str | Path,
    *,
    max_stations: int | None = None,
) -> pd.DataFrame:
    """Process a deterministic station queue with failure isolation."""

    import time

    required = {
        "state",
        "site_id",
        "source_path",
        "source_status",
    }

    missing = required - set(inventory.columns)

    if missing:
        raise ValueError(
            f"Missing inventory columns: {sorted(missing)}"
        )

    if max_stations is not None and max_stations < 1:
        raise ValueError("max_stations must be positive.")

    queue = (
        inventory.sort_values(["state", "site_id"])
        .reset_index(drop=True)
    )

    if max_stations is not None:
        queue = queue.head(max_stations)

    records = []

    for row in queue.itertuples(index=False):
        state = row.state
        site_id = validate_site_id(row.site_id)

        start = time.perf_counter()

        if row.source_status != "ready":
            result = {
                "state": state,
                "site_id": site_id,
                "status": row.source_status,
            }
        else:
            try:
                result = process_one_station(
                    row.source_path,
                    output_root,
                    state=state,
                    site_id=site_id,
                )
            except Exception as exc:
                result = {
                    "state": state,
                    "site_id": site_id,
                    "status": "failed",
                    "error": (
                        f"{type(exc).__name__}: {exc}"
                    ),
                }

        result["elapsed_seconds_total"] = round(
            time.perf_counter() - start,
            3,
        )

        records.append(result)

        save_processing_summary(
            pd.DataFrame([result]),
            output_root,
        )

        print(
            f"{state}/{site_id}: {result['status']}",
            flush=True,
        )

    return pd.DataFrame(records)


def save_processing_summary(
    records: pd.DataFrame,
    output_root: str | Path,
) -> Path:
    """Atomically update the national processing summary."""

    import os
    import tempfile

    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    destination = output_root / "national_processing_summary.parquet"

    if destination.exists():
        previous = pd.read_parquet(destination)
        combined = pd.concat(
            [previous, records],
            ignore_index=True,
        )
    else:
        combined = records.copy()

    combined = (
        combined.drop_duplicates(
            subset=["state", "site_id"],
            keep="last",
        )
        .sort_values(["state", "site_id"])
        .reset_index(drop=True)
    )

    with tempfile.NamedTemporaryFile(
        dir=output_root,
        suffix=".parquet",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)

    try:
        combined.to_parquet(temporary_path, index=False)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)

    return destination


from contextlib import contextmanager


@contextmanager
def national_processing_lock(output_root: str | Path):
    """Prevent concurrent national runners on macOS/Unix."""

    import fcntl

    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    lock_path = output_root / ".national_processing.lock"

    with lock_path.open("a+") as lock_file:
        try:
            fcntl.flock(
                lock_file.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError as exc:
            raise RuntimeError(
                "Another national processing run is active."
            ) from exc

        try:
            yield
        finally:
            fcntl.flock(
                lock_file.fileno(),
                fcntl.LOCK_UN,
            )



def process_stage_inventory(
    inventory: pd.DataFrame,
    output_root: str | Path,
    *,
    max_stations: int | None = None,
) -> pd.DataFrame:
    """Process stations under an exclusive national execution lock."""

    with national_processing_lock(output_root):
        return _process_stage_inventory_unlocked(
            inventory,
            output_root,
            max_stations=max_stations,
        )
