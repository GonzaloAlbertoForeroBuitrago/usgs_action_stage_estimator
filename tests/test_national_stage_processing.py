"""Tests for national v0.3.1 stage processing."""

import json

import pandas as pd

from usgs_action_stage_estimator.national_stage_processing import (
    process_one_station,
    validate_station_outputs,
)


def test_transactional_processing_and_resume(tmp_path):
    site_id = "384037104472001"
    state = "COLORADO"

    source = tmp_path / "source.parquet"
    output_root = tmp_path / "outputs"

    observations = pd.DataFrame({
        "datetime": pd.date_range(
            "2025-01-01",
            periods=7,
            freq="5min",
            tz="UTC",
        ),
        "Stage_ft": [8, 8, 10, 15, 10, 8, 8],
    })

    observations.to_parquet(source, index=False)

    result = process_one_station(
        source,
        output_root,
        state=state,
        site_id=site_id,
    )

    assert result["status"] == "completed"

    station_dir = output_root / state / site_id

    assert station_dir.is_dir()

    manifest = validate_station_outputs(
        station_dir,
        site_id=site_id,
        source_rows=len(observations),
    )

    assert manifest["site_id"] == site_id

    assert not list(
        station_dir.parent.glob(
            f".{site_id}_processing_*"
        )
    )

    resumed = process_one_station(
        source,
        output_root,
        state=state,
        site_id=site_id,
    )

    assert resumed["status"] == "already_completed"
    assert resumed["peak_candidates"] == result["peak_candidates"]


def test_empty_input_is_not_processed(tmp_path):
    source = tmp_path / "empty.parquet"

    pd.DataFrame({
        "datetime": pd.Series(dtype="datetime64[ns, UTC]"),
        "Stage_ft": pd.Series(dtype="float64"),
    }).to_parquet(source, index=False)

    result = process_one_station(
        source,
        tmp_path / "outputs",
        state="TEXAS",
        site_id="08165500",
    )

    assert result["status"] == "empty_input"
    assert not (tmp_path / "outputs").exists()


def test_source_fingerprint_is_stable(tmp_path):
    from usgs_action_stage_estimator.national_stage_processing import (
        fingerprint_source,
    )

    source = tmp_path / "observations.parquet"
    source.write_bytes(b"original source data")

    first = fingerprint_source(source)
    second = fingerprint_source(source)

    assert first == second
    assert first["source_size_bytes"] == len(b"original source data")

    source.write_bytes(b"modified source data")

    changed = fingerprint_source(source)

    assert changed["source_sha256"] != first["source_sha256"]


def test_changed_source_rejects_resume(tmp_path):
    site_id = "0136230002"
    state = "TEXAS"

    source = tmp_path / "source.parquet"
    output_root = tmp_path / "outputs"

    observations = pd.DataFrame({
        "datetime": pd.date_range(
            "2025-01-01",
            periods=7,
            freq="5min",
            tz="UTC",
        ),
        "Stage_ft": [8, 8, 10, 15, 10, 8, 8],
    })

    observations.to_parquet(source, index=False)

    first = process_one_station(
        source,
        output_root,
        state=state,
        site_id=site_id,
    )

    assert first["status"] == "completed"

    modified = observations.copy()
    modified.loc[3, "Stage_ft"] = 16.0
    modified.to_parquet(source, index=False)

    second = process_one_station(
        source,
        output_root,
        state=state,
        site_id=site_id,
    )

    assert second["status"] == "existing_output_invalid"
    assert second["error"] == "Source provenance mismatch."


def test_isolated_observations_preserved(tmp_path):
    site_id = "07273100"

    source = tmp_path / "isolated.parquet"

    observations = pd.DataFrame({
        "datetime": pd.to_datetime([
            "2019-02-23T18:00:00Z",
            "2020-06-09T18:00:00Z",
            "2021-06-10T18:00:00Z",
        ]),
        "Stage_ft": [8.9, 12.0, 18.67],
    })

    observations.to_parquet(source, index=False)

    result = process_one_station(
        source,
        tmp_path / "outputs",
        state="MISSISSIPPI",
        site_id=site_id,
    )

    assert result["status"] == "completed"

    station = tmp_path / "outputs/MISSISSIPPI" / site_id

    filtered = pd.read_parquet(
        station / "filtered_stage.parquet"
    )

    assert len(filtered) == 3
    assert not filtered["filter_applied"].any()


def test_short_segments_preserved(tmp_path):
    site_id = "02337170"

    source = tmp_path / "short_segments.parquet"

    observations = pd.DataFrame({
        "datetime": pd.to_datetime([
            "2025-01-01T00:00:00Z",
            "2025-01-01T00:15:00Z",
            "2025-01-01T00:30:00Z",
            "2025-01-02T00:00:00Z",
            "2025-01-03T00:00:00Z",
        ]),
        "Stage_ft": [2.0, 3.0, 2.0, 4.0, 5.0],
    })

    observations.to_parquet(source, index=False)

    result = process_one_station(
        source,
        tmp_path / "outputs",
        state="GEORGIA",
        site_id=site_id,
    )

    assert result["status"] == "completed"

    station = tmp_path / "outputs/GEORGIA" / site_id

    filtered = pd.read_parquet(
        station / "filtered_stage.parquet"
    )

    assert len(filtered) == len(observations)
    assert (~filtered["filter_applied"]).sum() >= 2
