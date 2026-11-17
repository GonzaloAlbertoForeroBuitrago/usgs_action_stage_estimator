#!/usr/bin/env python3
"""Regression-check the clean package V15 implementation against frozen V15.

This script does not use NOAA Action Stage. It compares the clean reference-free
implementation to the already-frozen V15 reference-free selections:

    v15__p50__d50__top3__recurrence_intensity

Run a deterministic sample first. Use ``--all`` only after the sample passes.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from usgs_action_stage_estimator.e03_recurrent_stage import (
    METHODOLOGY_VERSION,
    estimate_recurrent_stage,
)


CONFIG = (
    "v15__p50__d50__top3__"
    "recurrence_intensity"
)

DEFAULT_V15 = (
    Path.home()
    / "Documents/usgs_mrms_research/"
      "outputs/action_stage_estimator/E03/"
      "v15_dynamic_selection_national_r1"
)

DEFAULT_P00 = (
    Path.home()
    / "Documents/usgs_mrms_research/"
      "outputs/national_stage_peaks_v031"
)

CONTROLS = (
    ("GEORGIA", "02337170"),
    ("MARYLAND", "0158397967"),
    ("TEXAS", "08165500"),
    ("WISCONSIN", "05430500"),
    ("COLORADO", "09165000"),
    ("NEW_MEXICO", "09355500"),
)


def deterministic_sample(
    keys,
    limit,
):
    keys = sorted(
        set(keys)
    )

    key_set = set(keys)

    controls = [
        key
        for key in CONTROLS
        if key in key_set
    ]

    remaining = [
        key
        for key in keys
        if key not in controls
    ]

    remaining = sorted(
        remaining,
        key=lambda key: hashlib.sha256(
            (
                "E03-RS-V15-REGRESSION|"
                + "/".join(key)
            ).encode()
        ).hexdigest(),
    )

    return (
        controls
        + remaining[
            :max(
                0,
                limit - len(controls),
            )
        ]
    )


def compare_float(
    actual,
    expected,
    atol=1e-8,
):
    return bool(
        np.isclose(
            actual,
            expected,
            atol=atol,
            rtol=0,
            equal_nan=True,
        )
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--v15",
        type=Path,
        default=DEFAULT_V15,
    )
    parser.add_argument(
        "--p00",
        type=Path,
        default=DEFAULT_P00,
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--all",
        action="store_true",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "/tmp/e03_recurrent_stage_regression.csv"
        ),
    )

    args = parser.parse_args()

    v15 = (
        args.v15
        .expanduser()
        .resolve()
    )
    p00 = (
        args.p00
        .expanduser()
        .resolve()
    )

    frozen_path = (
        v15
        / "01a_reference_free_selections.csv"
    )

    if not frozen_path.is_file():
        raise SystemExit(
            f"Missing frozen V15 file: "
            f"{frozen_path}"
        )

    frozen = pd.read_csv(
        frozen_path,
        dtype={
            "state": str,
            "site_id": str,
        },
        float_precision="round_trip",
    )

    expected = frozen.loc[
        frozen[
            "configuration"
        ].eq(CONFIG)
    ].copy()

    if expected.duplicated(
        ["state", "site_id"]
    ).any():
        raise ValueError(
            "Duplicate frozen V15 station rows."
        )

    keys = list(
        zip(
            expected["state"],
            expected["site_id"],
        )
    )

    sites = (
        sorted(set(keys))
        if args.all
        else deterministic_sample(
            keys,
            args.sample,
        )
    )

    indexed = expected.set_index(
        ["state", "site_id"]
    )

    records = []

    print(
        "Clean methodology:",
        METHODOLOGY_VERSION,
        flush=True,
    )
    print(
        "Frozen configuration:",
        CONFIG,
        flush=True,
    )
    print(
        "Regression stations:",
        len(sites),
        flush=True,
    )

    for index, (
        state,
        site_id,
    ) in enumerate(
        sites,
        1,
    ):
        row = indexed.loc[
            (state, site_id)
        ]

        directory = (
            p00
            / state
            / site_id
        )

        result = (
            estimate_recurrent_stage(
                directory
                / "peak_candidates.parquet",
                directory
                / "filtered_stage.parquet",
                state=state,
                site_id=site_id,
            )
        )

        expected_stage = float(
            row[
                "estimated_stage_ft"
            ]
        )

        actual_stage = float(
            result[
                "estimated_stage_ft"
            ]
        )

        stage_pass = compare_float(
            actual_stage,
            expected_stage,
        )

        expected_joint = int(
            row[
                "joint_events"
            ]
        )

        actual_joint = int(
            result[
                "joint_events"
            ]
        )

        joint_pass = (
            actual_joint
            == expected_joint
        )

        expected_rank = float(
            row[
                "selected_rank"
            ]
        )

        actual_rank = float(
            result[
                "selected_rank"
            ]
        )

        rank_pass = compare_float(
            actual_rank,
            expected_rank,
            atol=0,
        )

        score_checks = {}

        for field in (
            "R",
            "I",
            "F",
            "selection_score",
            "first_value_ft_hr_median",
            "second_value_ft_hr_median",
        ):
            if field not in row.index:
                continue

            score_checks[field] = (
                compare_float(
                    float(
                        result[field]
                    ),
                    float(
                        row[field]
                    ),
                )
            )

        expected_status = str(
            row.get("status", "")
        )

        status_pass = (
            result["status"]
            not in {
                "invalid_input",
                "event_processing_failed",
            }
            and (
                expected_status != "candidate"
                or result["status"] == "candidate"
            )
        )

        passed = (
            stage_pass
            and joint_pass
            and rank_pass
            and status_pass
            and all(
                score_checks.values()
            )
        )

        records.append({
            "state": state,
            "site_id": site_id,
            "result": (
                "pass"
                if passed
                else "fail"
            ),
            "clean_status": (
                result["status"]
            ),
            "expected_stage_ft": (
                expected_stage
            ),
            "actual_stage_ft": (
                actual_stage
            ),
            "expected_joint_events": (
                expected_joint
            ),
            "actual_joint_events": (
                actual_joint
            ),
            "expected_rank": (
                expected_rank
            ),
            "actual_rank": (
                actual_rank
            ),
            "stage_pass": stage_pass,
            "joint_pass": joint_pass,
            "expected_status": expected_status,
            "status_pass": status_pass,
            "rank_pass": rank_pass,
            "score_checks": repr(
                score_checks
            ),
        })

        print(
            f"[{index}/{len(sites)}] "
            f"{state}/{site_id}: "
            f"{'PASS' if passed else 'FAIL'}",
            flush=True,
        )

    table = pd.DataFrame(
        records
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    table.to_csv(
        args.output,
        index=False,
    )

    failures = table.loc[
        table["result"].eq(
            "fail"
        )
    ]

    print(
        "\n=== V15 CLEAN REGRESSION ==="
    )
    print(
        "Stations:",
        len(table),
    )
    print(
        "Passes:",
        int(
            table[
                "result"
            ].eq("pass").sum()
        ),
    )
    print(
        "Failures:",
        len(failures),
    )
    print(
        "Output:",
        args.output,
    )

    if len(failures):
        print(
            "\nFAILURES:"
        )
        print(
            failures.to_string(
                index=False
            )
        )
        raise SystemExit(2)

    print(
        "CLEAN V15 REGRESSION PASSED."
    )


if __name__ == "__main__":
    main()
