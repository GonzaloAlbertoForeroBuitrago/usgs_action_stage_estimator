

"""National E03: derivative-selected, event-weighted stage windows.

Reads existing P00 outputs and validated historical NOAA references.

Methods match the four-station E03 experiment:
- Exact UTC start/peak validation against segment-local observations
- Average start-to-peak rise rate
- P90 of positive second derivatives for event ranking
- Independent exact-count upper-half selections
- Intersection population for station-level analysis
- 1-ft windows, 0.25-ft center spacing, five-event minimum
- Actual observation intervals; no resampling or interpolation

Outputs are resumable, station-specific, and written atomically.
"""

from __future__ import annotations

import argparse
import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from usgs_action_stage_estimator.e03_dynamics import (
    calculate_rising_limb_derivatives,
    select_upper_half,
)
from usgs_action_stage_estimator.e03_station_windows import (
    calculate_station_windows,
    select_winning_window,
)


ROOT = Path.home() / "Documents/usgs_mrms_research"

P00 = ROOT / "outputs/national_stage_peaks_v031"

REFERENCES = (
    Path(__file__).resolve().parents[1]
    / "src/usgs_action_stage_estimator/data/action_stage_references.parquet"
)

OUTPUT = ROOT / "outputs/action_stage_estimator/E03/national"

CONTROLS = [
    "08165500",
    "05430500",
    "02337170",
    "0158397967",
]

EXPECTED_CONTROLS = {
    "08165500": {"first": (13.25, 5), "second": (10.75, 5)},
    "05430500": {"first": (9.75, 7), "second": (9.75, 7)},
    "02337170": {"first": (11.50, 44), "second": (1.25, 173)},
    "0158397967": {"first": (7.75, 18), "second": (4.75, 131)},
}

MAX_INTERVAL_MIN = 60.0
WINDOW_WIDTH_FT = 1.0
CENTER_STEP_FT = 0.25
MIN_EVENTS = 5
METHODOLOGY_VERSION = "E03-J-v1"


KEYS = ["segment_id", "date_start", "date_peak"]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")

    with temporary.open("w") as file:
        json.dump(data, file, indent=2, allow_nan=False)

    os.replace(temporary, path)


def load_inventory():
    references = pd.read_parquet(REFERENCES)

    references["site_id"] = references["site_id"].astype("string")

    if references["site_id"].duplicated().any():
        raise ValueError("Duplicate NOAA reference identifiers.")

    eligible = (
        references["reference_eligible"]
        .astype("boolean")
        .fillna(False)
        & pd.to_numeric(
            references["validated_action_stage_ft"],
            errors="coerce",
        ).notna()
    )

    references = references.loc[eligible].copy()

    records = []

    for row in references.itertuples(index=False):
        state = str(row.state)
        site_id = str(row.site_id)

        directory = P00 / state / site_id

        if not (
            (directory / "filtered_stage.parquet").is_file()
            and (directory / "peak_candidates.parquet").is_file()
        ):
            continue

        records.append({
            "state": state,
            "site_id": site_id,
            "action_stage_ft": float(
                row.validated_action_stage_ft
            ),
            "nws_lid": str(row.nws_lid),
            "source_directory": str(directory),
        })

    result = pd.DataFrame(records)

    if result.empty:
        raise RuntimeError("No eligible P00/NOAA stations found.")

    return result.sort_values(["state", "site_id"])


def load_station(state, site_id):
    directory = P00 / state / site_id

    stage = pd.read_parquet(
        directory / "filtered_stage.parquet",
        columns=["datetime", "Stage_ft", "segment_id"],
    )

    peaks = pd.read_parquet(
        directory / "peak_candidates.parquet"
    )

    stage["datetime"] = pd.to_datetime(
        stage["datetime"], utc=True
    )

    events = peaks.loc[
        peaks["candidate_type"] == "detected_event"
    ].copy()

    events["date_start"] = pd.to_datetime(
        events["date_start"], utc=True
    )
    events["date_peak"] = pd.to_datetime(
        events["date_peak"], utc=True
    )

    if events.duplicated(KEYS).any():
        raise ValueError("Duplicate event identifiers.")

    if events.empty:
        return {}, events

    groups = {}

    for segment_id, group in stage.groupby(
        "segment_id", sort=False
    ):
        observations = (
            group.sort_values("datetime", kind="stable")
            .reset_index(drop=True)
        )

        times = observations["datetime"].astype("int64").to_numpy()

        if len(times) > 1 and np.any(np.diff(times) <= 0):
            raise ValueError("Duplicate or non-increasing timestamps.")

        groups[segment_id] = observations

    return groups, events


def event_observations(groups, event):
    observations = groups[event.segment_id]

    times = observations["datetime"].astype("int64").to_numpy()
    heights = observations["Stage_ft"].to_numpy(dtype=float)

    start = int(np.searchsorted(times, event.date_start.value))
    peak = int(np.searchsorted(times, event.date_peak.value))

    if not (
        0 <= start < peak < len(times)
        and times[start] == event.date_start.value
        and times[peak] == event.date_peak.value
    ):
        raise ValueError("Event timestamp/index mismatch.")

    if not (
        np.isclose(heights[start], event.flow_start, rtol=0, atol=1e-9)
        and np.isclose(heights[peak], event.flow_peak, rtol=0, atol=1e-9)
    ):
        raise ValueError("Event stage boundary mismatch.")

    if (
        int(event.i_start) != start
        or int(event.i_peak) != peak
    ):
        raise ValueError("Segment-local event index mismatch.")

    return observations.iloc[start:peak + 1].copy()


def calculate_event_metrics(groups, events):
    records = []

    for event in events.itertuples(index=False):
        limb = event_observations(groups, event)

        duration = (
            event.date_peak - event.date_start
        ).total_seconds() / 3600.0

        if duration <= 0:
            raise ValueError("Non-positive event duration.")

        rate = (
            float(event.flow_peak) - float(event.flow_start)
        ) / duration

        # Reuse the validated derivative implementation.
        derivatives = calculate_rising_limb_derivatives(
            limb,
            max_interval_minutes=MAX_INTERVAL_MIN,
        )

        acceleration = derivatives[
            "second_derivative_ft_hr2"
        ].to_numpy(dtype=float)

        positive = acceleration[
            np.isfinite(acceleration) & (acceleration > 0)
        ]

        p90 = (
            float(np.percentile(positive, 90))
            if len(positive) else np.nan
        )

        records.append({
            "segment_id": event.segment_id,
            "date_start": event.date_start,
            "date_peak": event.date_peak,
            "average_rise_rate_ft_hr": rate,
            "p90_positive_acceleration_ft_hr2": p90,
        })

    return pd.DataFrame(records)


def select_events(metrics):
    first = select_upper_half(
        metrics, "average_rise_rate_ft_hr"
    )

    second = select_upper_half(
        metrics, "p90_positive_acceleration_ft_hr2"
    )

    selected = metrics.copy()

    selected["selected_first"] = first["selected"]
    selected["selected_second"] = second["selected"]

    selected["selected_both"] = (
        selected["selected_first"]
        & selected["selected_second"]
    )

    return selected


def build_selected_observations(groups, events, selection, site_id):
    selected = selection.loc[
        selection["selected_both"]
    ]

    if selected.empty:
        return pd.DataFrame()

    selected_events = events.merge(
        selected[KEYS],
        on=KEYS,
        how="inner",
        validate="one_to_one",
    )

    frames = []

    for event in selected_events.itertuples(index=False):
        limb = event_observations(groups, event)

        derivatives = calculate_rising_limb_derivatives(
            limb,
            max_interval_minutes=MAX_INTERVAL_MIN,
        )

        derivatives["event_id"] = (
            f"{site_id}|{event.segment_id}|"
            f"{event.date_start.isoformat()}|"
            f"{event.date_peak.isoformat()}"
        )

        frames.append(
            derivatives[
                [
                    "event_id",
                    "midpoint_stage_ft",
                    "first_derivative_ft_hr",
                    "second_derivative_ft_hr2",
                ]
            ]
        )

    return pd.concat(frames, ignore_index=True)


def process_station(row):
    state = str(row.state)
    site_id = str(row.site_id)
    action = float(row.action_stage_ft)

    groups, events = load_station(state, site_id)

    if events.empty:
        return {
            "methodology_version": METHODOLOGY_VERSION,
            "state": state,
            "site_id": site_id,
            "action_stage_ft": action,
            "status": "no_detected_events",
            "detected_events": 0,
            "selected_both": 0,
            "winners": {},
        }

    metrics = calculate_event_metrics(groups, events)
    selection = select_events(metrics)

    observations = build_selected_observations(
        groups, events, selection, site_id
    )

    winners = {}

    if not observations.empty:
        for name, metric in [
            ("first", "first_derivative_ft_hr"),
            ("second", "second_derivative_ft_hr2"),
        ]:
            profile = calculate_station_windows(
                observations,
                metric,
                window_width_ft=WINDOW_WIDTH_FT,
                center_step_ft=CENTER_STEP_FT,
            )

            winner = select_winning_window(
                profile,
                action_stage_ft=action,
                min_events=MIN_EVENTS,
            )

            winners[name] = winner

    selected_both = int(selection["selected_both"].sum())

    return {
        "methodology_version": METHODOLOGY_VERSION,
        "state": state,
        "site_id": site_id,
        "action_stage_ft": action,
        "status": (
            "completed"
            if all(winners.get(k) is not None for k in ("first", "second"))
            else "insufficient_window_support"
        ),
        "detected_events": len(events),
        "valid_positive_acceleration_events": int(
            metrics["p90_positive_acceleration_ft_hr2"].notna().sum()
        ),
        "selected_first": int(selection["selected_first"].sum()),
        "selected_second": int(selection["selected_second"].sum()),
        "selected_both": selected_both,
        "winners": winners,
    }


def check_control(result):
    site_id = result["site_id"]

    if site_id not in EXPECTED_CONTROLS:
        return

    for derivative, (expected_center, expected_support) in (
        EXPECTED_CONTROLS[site_id].items()
    ):
        winner = result["winners"].get(derivative)

        if winner is None:
            raise AssertionError(
                f"{site_id}/{derivative}: missing winner"
            )

        if not np.isclose(
            winner["center_ft"],
            expected_center,
            rtol=0,
            atol=1e-10,
        ):
            raise AssertionError(
                f"{site_id}/{derivative}: unexpected center "
                f"{winner['center_ft']} != {expected_center}"
            )

        if int(winner["contributing_events"]) != expected_support:
            raise AssertionError(
                f"{site_id}/{derivative}: unexpected support"
            )


def run(args):
    inventory = load_inventory()

    if args.controls:
        inventory = inventory.loc[
            inventory["site_id"].isin(CONTROLS)
        ]

        if len(inventory) != len(CONTROLS):
            raise RuntimeError("Not all control stations are eligible.")

    if args.site:
        inventory = inventory.loc[
            inventory["site_id"] == args.site
        ]

        if inventory.empty:
            raise ValueError("Requested site is not eligible.")

    if args.limit is not None:
        inventory = inventory.head(args.limit)

    print("Stations scheduled:", len(inventory), flush=True)

    completed = 0
    skipped = 0
    failed = 0

    for row in inventory.itertuples(index=False):
        destination = (
            OUTPUT / row.state / row.site_id / "result.json"
        )

        if args.resume and destination.is_file():
            try:
                with destination.open() as file:
                    existing = json.load(file)

                if (
                    existing.get("methodology_version")
                    == METHODOLOGY_VERSION
                    and existing.get("site_id") == row.site_id
                    and existing.get("state") == row.state
                    and np.isclose(
                        existing.get("action_stage_ft", np.nan),
                        row.action_stage_ft,
                        rtol=0,
                        atol=1e-9,
                    )
                ):
                    skipped += 1
                    continue

            except (OSError, ValueError, TypeError):
                pass

        try:
            result = process_station(row)

            check_control(result)
            atomic_json(destination, result)

            completed += 1

            print(
                f"{row.state}/{row.site_id}: "
                f"{result['status']}; "
                f"selected_both={result['selected_both']}",
                flush=True,
            )

        except Exception as exc:
            failed += 1

            error_path = (
                OUTPUT / row.state / row.site_id / "error.json"
            )

            atomic_json(error_path, {
                "state": row.state,
                "site_id": row.site_id,
                "status": "failed",
                "error_type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
                "timestamp_utc": utc_now(),
            })

            print(
                f"FAILED {row.state}/{row.site_id}: {exc}",
                flush=True,
            )

            if args.fail_fast:
                raise

    print("\n=== NATIONAL E03 SUMMARY ===")
    print("Processed:", completed)
    print("Skipped:", skipped)
    print("Failed:", failed)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--controls", action="store_true")
    parser.add_argument("--site", type=str)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")

    args = parser.parse_args()

    run(args)


if __name__ == "__main__":
    main()
