#!/usr/bin/env python3
"""National reference-free E03 recurrent-stage runner.

This runner is separate from the historical ``run_national_e03.py`` workflow:
the historical runner consumes validated NOAA Action Stage references, while
this runner does not read any NOAA/reference table.

Inputs are existing P00 station products:
  * filtered_stage.parquet
  * peak_candidates.parquet

Outputs are station-specific, atomic and resumable by methodology version.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import traceback

import numpy as np

from usgs_action_stage_estimator.e03_recurrent_stage import (
    METHODOLOGY_VERSION,
    estimate_recurrent_stage,
)


ROOT = (
    Path.home()
    / "Documents/usgs_mrms_research"
)

P00 = (
    ROOT
    / "outputs/national_stage_peaks_v031"
)

OUTPUT = (
    ROOT
    / "outputs/action_stage_estimator/E03/"
      "recurrent_stage_v15_national"
)


def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def clean(value):
    if isinstance(value, dict):
        return {
            str(key): clean(item)
            for key, item
            in value.items()
        }

    if isinstance(
        value,
        (list, tuple),
    ):
        return [
            clean(item)
            for item in value
        ]

    if isinstance(
        value,
        (np.integer, np.bool_),
    ):
        return value.item()

    if isinstance(
        value,
        (float, np.floating),
    ):
        return (
            float(value)
            if np.isfinite(value)
            else None
        )

    return value


def atomic_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_name(
        path.name + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            clean(data),
            indent=2,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )

    os.replace(
        temporary,
        path,
    )


def discover_sites(p00):
    records = []

    for peak_path in p00.glob(
        "*/*/peak_candidates.parquet"
    ):
        directory = peak_path.parent

        stage_path = (
            directory
            / "filtered_stage.parquet"
        )

        if not stage_path.is_file():
            continue

        records.append(
            (
                directory.parent.name,
                directory.name,
            )
        )

    return sorted(
        set(records)
    )


def process_station(
    state,
    site_id,
    p00,
):
    directory = (
        p00 / state / site_id
    )

    return estimate_recurrent_stage(
        directory
        / "peak_candidates.parquet",
        directory
        / "filtered_stage.parquet",
        state=state,
        site_id=site_id,
    )


def resume_compatible(
    path,
    state,
    site_id,
):
    try:
        existing = json.loads(
            path.read_text()
        )
    except (
        OSError,
        ValueError,
        TypeError,
    ):
        return False

    return (
        existing.get(
            "methodology_version"
        ) == METHODOLOGY_VERSION
        and existing.get(
            "state"
        ) == state
        and existing.get(
            "site_id"
        ) == site_id
    )


def run(args):
    p00 = (
        args.p00
        .expanduser()
        .resolve()
    )

    output = (
        args.output
        .expanduser()
        .resolve()
    )

    sites = discover_sites(
        p00
    )

    if args.state:
        sites = [
            pair
            for pair in sites
            if pair[0] == args.state
        ]

    if args.site:
        sites = [
            pair
            for pair in sites
            if pair[1] == args.site
        ]

    if args.limit is not None:
        sites = sites[
            :args.limit
        ]

    if not sites:
        raise RuntimeError(
            "No P00 stations selected."
        )

    print(
        "Methodology:",
        METHODOLOGY_VERSION,
        flush=True,
    )
    print(
        "Stations scheduled:",
        len(sites),
        flush=True,
    )
    print(
        "Output:",
        output,
        flush=True,
    )
    print(
        "NO NOAA/Action Stage "
        "reference is read.",
        flush=True,
    )

    completed = 0
    skipped = 0
    failed = 0

    for index, (
        state,
        site_id,
    ) in enumerate(
        sites,
        1,
    ):
        destination = (
            output
            / state
            / site_id
            / "result.json"
        )

        if (
            args.resume
            and destination.is_file()
            and resume_compatible(
                destination,
                state,
                site_id,
            )
        ):
            skipped += 1
            continue

        try:
            result = process_station(
                state,
                site_id,
                p00,
            )

            atomic_json(
                destination,
                result,
            )

            completed += 1

            if (
                index % 25 == 0
                or index == len(sites)
            ):
                print(
                    f"[{index}/{len(sites)}] "
                    f"{state}/{site_id}: "
                    f"{result['status']}; "
                    f"stage="
                    f"{result.get('estimated_stage_ft')}; "
                    f"completed/skipped/failed="
                    f"{completed}/{skipped}/{failed}",
                    flush=True,
                )

        except Exception as exc:
            failed += 1

            error_path = (
                output
                / state
                / site_id
                / "error.json"
            )

            atomic_json(
                error_path,
                {
                    "methodology_version": (
                        METHODOLOGY_VERSION
                    ),
                    "state": state,
                    "site_id": site_id,
                    "status": "failed",
                    "error_type": (
                        type(exc).__name__
                    ),
                    "message": str(exc),
                    "traceback": (
                        traceback.format_exc()
                    ),
                    "timestamp_utc": (
                        utc_now()
                    ),
                },
            )

            print(
                f"FAILED "
                f"{state}/{site_id}: "
                f"{exc}",
                flush=True,
            )

            if args.fail_fast:
                raise

    print(
        "\n=== RECURRENT-STAGE SUMMARY ==="
    )
    print(
        "Processed:",
        completed,
    )
    print(
        "Skipped:",
        skipped,
    )
    print(
        "Failed:",
        failed,
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--p00",
        type=Path,
        default=P00,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
    )
    parser.add_argument(
        "--state",
        type=str,
    )
    parser.add_argument(
        "--site",
        type=str,
    )
    parser.add_argument(
        "--limit",
        type=int,
    )
    parser.add_argument(
        "--resume",
        action="store_true",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
    )

    run(
        parser.parse_args()
    )


if __name__ == "__main__":
    main()
