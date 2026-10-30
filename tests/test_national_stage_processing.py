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


def test_national_queue_handles_empty_and_missing(tmp_path):
    from usgs_action_stage_estimator.national_stage_processing import (
        process_stage_inventory,
    )

    inventory = pd.DataFrame([
        {
            "state": "TEXAS",
            "site_id": "08165500",
            "source_path": str(tmp_path / "missing.parquet"),
            "source_status": "ready",
        },
        {
            "state": "IOWA",
            "site_id": "05400000",
            "source_path": str(tmp_path / "empty.parquet"),
            "source_status": "empty_input",
        },
    ])

    result = process_stage_inventory(
        inventory,
        tmp_path / "outputs",
    )

    assert len(result) == 2

    statuses = dict(zip(result["site_id"], result["status"]))

    assert statuses["08165500"] == "missing_input"
    assert statuses["05400000"] == "empty_input"


def test_national_queue_rejects_invalid_limit(tmp_path):
    from usgs_action_stage_estimator.national_stage_processing import (
        process_stage_inventory,
    )

    inventory = pd.DataFrame(columns=[
        "state",
        "site_id",
        "source_path",
        "source_status",
    ])

    import pytest

    with pytest.raises(ValueError):
        process_stage_inventory(
            inventory,
            tmp_path,
            max_stations=0,
        )


def test_processing_summary_updates_without_duplicates(tmp_path):
    from usgs_action_stage_estimator.national_stage_processing import (
        save_processing_summary,
    )

    first = pd.DataFrame([{
        "state": "TEXAS",
        "site_id": "08165500",
        "status": "completed",
        "peak_candidates": 100,
    }])

    second = pd.DataFrame([{
        "state": "TEXAS",
        "site_id": "08165500",
        "status": "already_completed",
        "peak_candidates": 100,
    }])

    save_processing_summary(first, tmp_path)
    destination = save_processing_summary(second, tmp_path)

    saved = pd.read_parquet(destination)

    assert len(saved) == 1
    assert saved.iloc[0]["site_id"] == "08165500"
    assert saved.iloc[0]["status"] == "already_completed"
    assert saved.iloc[0]["peak_candidates"] == 100


def test_processing_summary_updates_without_duplicates(tmp_path):
    from usgs_action_stage_estimator.national_stage_processing import (
        save_processing_summary,
    )

    first = pd.DataFrame([{
        "state": "TEXAS",
        "site_id": "08165500",
        "status": "completed",
        "peak_candidates": 100,
    }])

    second = pd.DataFrame([{
        "state": "TEXAS",
        "site_id": "08165500",
        "status": "already_completed",
        "peak_candidates": 100,
    }])

    save_processing_summary(first, tmp_path)
    destination = save_processing_summary(second, tmp_path)

    saved = pd.read_parquet(destination)

    assert len(saved) == 1
    assert saved.iloc[0]["site_id"] == "08165500"
    assert saved.iloc[0]["status"] == "already_completed"
    assert saved.iloc[0]["peak_candidates"] == 100


def test_national_runner_persists_progress(tmp_path):
    from usgs_action_stage_estimator.national_stage_processing import (
        process_stage_inventory,
    )

    inventory = pd.DataFrame([
        {
            "state": "IOWA",
            "site_id": "05400000",
            "source_path": str(tmp_path / "missing.parquet"),
            "source_status": "ready",
        },
        {
            "state": "TEXAS",
            "site_id": "08165500",
            "source_path": str(tmp_path / "empty.parquet"),
            "source_status": "empty_input",
        },
    ])

    output_root = tmp_path / "outputs"

    result = process_stage_inventory(
        inventory,
        output_root,
    )

    saved = pd.read_parquet(
        output_root / "national_processing_summary.parquet"
    )

    assert len(result) == 2
    assert len(saved) == 2
    assert saved["site_id"].is_unique

    statuses = dict(zip(saved["site_id"], saved["status"]))

    assert statuses["05400000"] == "missing_input"
    assert statuses["08165500"] == "empty_input"


def test_national_runner_resumes_without_duplicates(tmp_path):
    from usgs_action_stage_estimator.national_stage_processing import (
        process_stage_inventory,
    )

    source = tmp_path / "source.parquet"

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

    inventory = pd.DataFrame([
        {
            "state": "COLORADO",
            "site_id": "384037104472001",
            "source_path": str(source),
            "source_status": "ready",
        },
        {
            "state": "TEXAS",
            "site_id": "08165500",
            "source_path": str(tmp_path / "missing.parquet"),
            "source_status": "ready",
        },
    ])

    output_root = tmp_path / "outputs"

    first = process_stage_inventory(
        inventory,
        output_root,
        max_stations=1,
    )

    assert first.iloc[0]["status"] == "completed"

    second = process_stage_inventory(
        inventory,
        output_root,
    )

    statuses = dict(zip(second["site_id"], second["status"]))

    assert statuses["384037104472001"] == "already_completed"
    assert statuses["08165500"] == "missing_input"

    summary = pd.read_parquet(
        output_root / "national_processing_summary.parquet"
    )

    assert len(summary) == 2
    assert summary["site_id"].is_unique


def test_national_processing_lock_rejects_second_runner(tmp_path):
    import pytest

    from usgs_action_stage_estimator.national_stage_processing import (
        national_processing_lock,
    )

    with national_processing_lock(tmp_path):
        with pytest.raises(
            RuntimeError,
            match="Another national processing run is active",
        ):
            with national_processing_lock(tmp_path):
                pass


def test_completed_and_resumed_summary_fields(tmp_path):
    from usgs_action_stage_estimator.national_stage_processing import (
        process_one_station,
    )

    source = tmp_path / "source.parquet"

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

    kwargs = {
        "state": "TEXAS",
        "site_id": "0136230002",
    }

    first = process_one_station(
        source, tmp_path / "outputs", **kwargs
    )

    second = process_one_station(
        source, tmp_path / "outputs", **kwargs
    )

    fields = {
        "source_rows",
        "segments",
        "detected_events",
        "filtered_observations",
        "unfiltered_observations",
        "peak_candidates",
        "selected_peaks",
        "processing_version",
    }

    assert first["status"] == "completed"
    assert second["status"] == "already_completed"

    for field in fields:
        assert first[field] == second[field]


def test_national_processing_lock_rejects_second_runner(tmp_path):
    import pytest

    from usgs_action_stage_estimator.national_stage_processing import (
        national_processing_lock,
    )

    with national_processing_lock(tmp_path):
        with pytest.raises(
            RuntimeError,
            match="Another national processing run is active",
        ):
            with national_processing_lock(tmp_path):
                pass


def test_completed_and_resumed_summary_fields(tmp_path):
    from usgs_action_stage_estimator.national_stage_processing import (
        process_one_station,
    )

    source = tmp_path / "source.parquet"

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

    kwargs = {
        "state": "TEXAS",
        "site_id": "0136230002",
    }

    first = process_one_station(
        source, tmp_path / "outputs", **kwargs
    )

    second = process_one_station(
        source, tmp_path / "outputs", **kwargs
    )

    fields = {
        "source_rows",
        "segments",
        "detected_events",
        "filtered_observations",
        "unfiltered_observations",
        "peak_candidates",
        "selected_peaks",
        "processing_version",
    }

    assert first["status"] == "completed"
    assert second["status"] == "already_completed"

    for field in fields:
        assert first[field] == second[field]


def test_runner_respects_national_lock(tmp_path):
    import pytest

    from usgs_action_stage_estimator.national_stage_processing import (
        national_processing_lock,
        process_stage_inventory,
    )

    inventory = pd.DataFrame([{
        "state": "TEXAS",
        "site_id": "08165500",
        "source_path": str(tmp_path / "missing.parquet"),
        "source_status": "ready",
    }])

    with national_processing_lock(tmp_path / "outputs"):
        with pytest.raises(
            RuntimeError,
            match="Another national processing run is active",
        ):
            process_stage_inventory(
                inventory,
                tmp_path / "outputs",
            )
