"""Reference-free E03 independent-event recurrence mechanics.

This module is the cleaned production extraction of the validated E03
V7/V8/V13/V15 research lineage.

It intentionally does NOT read NOAA/NWS Action Stage and does not import any
reference-validation module.

Terminology
-----------
``mean_first_ft_hr``
    Mean stage-rise rate across one complete stage traversal, in ft/h.
    This is stage rise rate, not water/stream velocity.

``cumulative_positive_second_ft_hr``
    Cumulative positive change in stage-rise rate across the traversal, in ft/h.
    This is the historically validated recurrence metric used by V15. It is not
    the instantaneous second derivative/acceleration in ft/h^2 implemented by
    the older :mod:`e03_dynamics` workflow.

Method
------
* detected rising events with rise > 1 ft
* adaptive traversal width = max(1 ft, median eligible-event rise)
* complete event-local rising-limb traversals using actual UTC observations
* strict station-wide P50 thresholds for both metrics
* independent-event interval unions and exact overlap recurrence
* local recurrence concentrations supported by >= 2 independent events
* per-concentration event evidence used by the V15 selector

No fixed stage bins are introduced in recurrence and each event counts at most
once at a given stage.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


FIRST = "mean_first_ft_hr"
SECOND = "cumulative_positive_second_ft_hr"

MIN_EVENT_RISE_FT = 1.0
MIN_WINDOW_WIDTH_FT = 1.0
DERIVATIVE_QUANTILE = 0.50
MIN_JOINT_EVENTS = 2
DECIMALS = 8

WINDOW_COLUMNS = [
    "event_id",
    "window_lower_ft",
    "window_upper_ft",
    "window_center_ft",
    "window_width_ft",
    "start_utc",
    "end_utc",
    "duration_hr",
    "valid_intervals",
    FIRST,
    SECOND,
    "normalized_second_ft_hr2",
    "normalized_signed_ft_hr2",
]

CONCENTRATION_COLUMNS = [
    "concentration_rank",
    "component_id",
    "height_ft",
    "stage_lower_ft",
    "stage_upper_ft",
    "plateau_width_ft",
    "plateau_regions",
    "joint_events",
]


def load_events(
    path,
    *,
    min_rise_ft: float = MIN_EVENT_RISE_FT,
) -> pd.DataFrame:
    """Load eligible detected rising events from P00 peak candidates.

    The eligible-event rule is strictly ``rise_ft > min_rise_ft``.
    """
    required = [
        "segment_id",
        "date_start",
        "date_peak",
        "flow_start",
        "flow_peak",
        "candidate_type",
    ]

    try:
        frame = pd.read_parquet(path, columns=required)
    except Exception as exc:
        message = str(exc)
        if "date_start" in message and "No match for" in message:
            raise ValueError(
                "Incompatible peak-candidate schema: required field "
                "'date_start' is missing."
            ) from exc
        raise

    frame = frame.loc[
        frame["candidate_type"].eq("detected_event")
    ].copy()

    for column in ("date_start", "date_peak"):
        frame[column] = pd.to_datetime(frame[column], utc=True)

    for column in ("flow_start", "flow_peak"):
        frame[column] = pd.to_numeric(
            frame[column], errors="coerce"
        )

    frame["rise_ft"] = (
        frame["flow_peak"] - frame["flow_start"]
    )

    frame = frame.loc[
        np.isfinite(frame["rise_ft"])
        & (frame["rise_ft"] > float(min_rise_ft))
        & (frame["date_peak"] > frame["date_start"])
    ].copy()

    if frame.duplicated(
        ["segment_id", "date_start", "date_peak"]
    ).any():
        raise ValueError("Duplicate event boundaries.")

    return frame.sort_values(
        ["segment_id", "date_start", "date_peak"],
        kind="stable",
    ).reset_index(drop=True)


def load_segments(path) -> dict[Any, pd.DataFrame]:
    """Load P00 stage observations grouped by segment."""
    frame = pd.read_parquet(
        path,
        columns=["datetime", "Stage_ft", "segment_id"],
    )

    frame["datetime"] = pd.to_datetime(
        frame["datetime"], utc=True
    )
    frame["Stage_ft"] = pd.to_numeric(
        frame["Stage_ft"], errors="coerce"
    )

    result: dict[Any, pd.DataFrame] = {}

    for segment_id, group in frame.groupby("segment_id"):
        observations = (
            group.sort_values("datetime", kind="stable")
            .reset_index(drop=True)
        )

        if observations["datetime"].duplicated().any():
            raise ValueError("Duplicate UTC timestamps.")

        result[segment_id] = observations

    return result


def crossing_times(
    time_ns: np.ndarray,
    stage_ft: np.ndarray,
    level_ft: float,
) -> list[int]:
    """Return interpolated upward crossings of one stage level."""
    result: list[int] = []

    if np.isclose(
        stage_ft[0], level_ft, atol=1e-9, rtol=0
    ):
        result.append(int(time_ns[0]))

    for index in range(1, len(stage_ft)):
        if (
            stage_ft[index - 1]
            < level_ft
            <= stage_ft[index]
        ):
            fraction = (
                level_ft - stage_ft[index - 1]
            ) / (
                stage_ft[index] - stage_ft[index - 1]
            )

            result.append(
                int(
                    round(
                        time_ns[index - 1]
                        + fraction
                        * (
                            time_ns[index]
                            - time_ns[index - 1]
                        )
                    )
                )
            )

    return sorted(set(result))


def make_traversal_windows(
    limb: pd.DataFrame,
    event_id: str,
    state: str,
    site_id: str,
    width_ft: float,
) -> list[dict[str, Any]]:
    """Build complete validated traversal windows for one rising limb.

    This preserves the historical V7 implementation used by the frozen V15
    experiment, except that the legacy unused Action Stage metadata field has
    been removed.
    """
    time_ns = (
        limb["datetime"]
        .astype("int64")
        .to_numpy(dtype=np.int64)
    )
    stage_ft = limb["Stage_ft"].to_numpy(dtype=float)

    delta_hours = np.diff(time_ns) / 3.6e12

    if (
        not np.isfinite(stage_ft).all()
        or not np.isfinite(delta_hours).all()
        or (delta_hours <= 0).any()
    ):
        raise ValueError("Invalid stage or time.")

    rise_rates = np.diff(stage_ft) / delta_hours
    rate_changes = np.r_[0.0, np.diff(rise_rates)]

    records: list[dict[str, Any]] = []

    for low in np.unique(stage_ft):
        low = float(low)
        high = float(low + width_ft)

        if high > float(np.max(stage_ft)) + 1e-9:
            continue

        starts = crossing_times(
            time_ns, stage_ft, low
        )
        ends = crossing_times(
            time_ns, stage_ft, high
        )

        options = [
            (
                start,
                next(
                    (
                        end
                        for end in ends
                        if end > start
                    ),
                    None,
                ),
            )
            for start in starts
        ]
        options = [
            (start, end)
            for start, end in options
            if end is not None
        ]

        if not options:
            continue

        start, end = min(
            options,
            key=lambda pair: (
                pair[1] - pair[0],
                pair[0],
            ),
        )

        overlap_ns = np.maximum(
            0,
            np.minimum(time_ns[1:], end)
            - np.maximum(time_ns[:-1], start),
        ).astype(float)

        fractions = overlap_ns / np.diff(time_ns)
        used = fractions > 1e-12

        # Historical V7 rule: reject a traversal if any contributing
        # observation interval is longer than 60 minutes.
        if (
            not used.any()
            or (
                delta_hours[used] * 60
                > 60 + 1e-8
            ).any()
        ):
            continue

        duration_hours = (
            end - start
        ) / 3.6e12

        if duration_hours <= 0:
            continue

        positive_change = float(
            np.sum(
                np.maximum(rate_changes, 0.0)
                * fractions
            )
        )

        signed_change = float(
            np.sum(
                rate_changes * fractions
            )
        )

        records.append({
            "event_id": event_id,
            "state": state,
            "site_id": site_id,
            "window_lower_ft": low,
            "window_upper_ft": high,
            "window_center_ft": (
                low + width_ft / 2
            ),
            "window_width_ft": float(width_ft),
            "start_utc": pd.Timestamp(
                start, tz="UTC"
            ),
            "end_utc": pd.Timestamp(
                end, tz="UTC"
            ),
            "duration_hr": duration_hours,
            "valid_intervals": int(
                used.sum()
            ),
            FIRST: (
                width_ft / duration_hours
            ),
            SECOND: positive_change,
            "normalized_second_ft_hr2": (
                positive_change / duration_hours
            ),
            "normalized_signed_ft_hr2": (
                signed_change / duration_hours
            ),
        })

    return records


def adaptive_p50_width(
    events: pd.DataFrame,
) -> float:
    """Return the frozen V15 p50 traversal width."""
    if events.empty:
        return MIN_WINDOW_WIDTH_FT

    return max(
        MIN_WINDOW_WIDTH_FT,
        float(events["rise_ft"].quantile(0.50)),
    )


def build_station_windows(
    events: pd.DataFrame,
    segments: dict[Any, pd.DataFrame],
    state: str,
    site_id: str,
    width_ft: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build all eligible-event windows and coverage diagnostics.

    Any event validation failure blocks station scoring; no partial-station
    estimate is emitted.
    """
    records: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []

    for event in events.itertuples(index=False):
        row = {
            "event_id": str(event.event_id),
            "rise_ft": float(event.rise_ft),
            "window_width_ft": float(width_ft),
            "candidate_windows": 0,
            "status": "",
            "error": "",
        }

        if event.rise_ft + 1e-9 < width_ft:
            row["status"] = (
                "rise_below_window_width"
            )
            coverage.append(row)
            continue

        try:
            group = segments[event.segment_id]

            limb = group.loc[
                group["datetime"].between(
                    event.date_start,
                    event.date_peak,
                    inclusive="both",
                )
            ]

            if (
                len(limb) < 2
                or limb["datetime"].iloc[0]
                != event.date_start
                or limb["datetime"].iloc[-1]
                != event.date_peak
            ):
                raise ValueError(
                    "Missing event boundaries."
                )

            if not np.isclose(
                limb["Stage_ft"].iloc[0],
                event.flow_start,
                atol=1e-8,
                rtol=0,
            ):
                raise ValueError(
                    "Start stage mismatch."
                )

            if not np.isclose(
                limb["Stage_ft"].iloc[-1],
                event.flow_peak,
                atol=1e-8,
                rtol=0,
            ):
                raise ValueError(
                    "Peak stage mismatch."
                )

            found = make_traversal_windows(
                limb,
                str(event.event_id),
                state,
                site_id,
                width_ft,
            )

            records.extend(found)
            row["candidate_windows"] = len(found)
            row["status"] = (
                "complete"
                if found
                else "no_complete_window"
            )

        except (
            ValueError,
            KeyError,
            IndexError,
            AssertionError,
        ) as exc:
            row["status"] = "failed"
            row["error"] = (
                f"{type(exc).__name__}: {exc}"
            )

        coverage.append(row)

    windows = pd.DataFrame(
        records,
        columns=WINDOW_COLUMNS,
    )

    if not windows.empty:
        for column in (
            FIRST,
            SECOND,
            "duration_hr",
            "window_lower_ft",
            "window_upper_ft",
        ):
            values = windows[
                column
            ].to_numpy(float)

            if not np.isfinite(values).all():
                raise ValueError(
                    f"Nonfinite {column}."
                )

        if not windows[
            "duration_hr"
        ].gt(0).all():
            raise ValueError(
                "Nonpositive duration."
            )

        if not np.allclose(
            (
                windows["window_upper_ft"]
                - windows["window_lower_ft"]
            ),
            width_ft,
            rtol=0,
            atol=1e-8,
        ):
            raise ValueError(
                "Window width mismatch."
            )

        if not np.allclose(
            windows[FIRST],
            (
                width_ft
                / windows["duration_hr"]
            ),
            rtol=1e-8,
            atol=1e-8,
        ):
            raise ValueError(
                "First-rate identity failed."
            )

        actual_duration = (
            pd.to_datetime(
                windows["end_utc"], utc=True
            )
            - pd.to_datetime(
                windows["start_utc"], utc=True
            )
        ).dt.total_seconds() / 3600

        if not np.allclose(
            actual_duration,
            windows["duration_hr"],
            rtol=1e-8,
            atol=1e-8,
        ):
            raise ValueError(
                "UTC duration identity failed."
            )

    coverage_frame = pd.DataFrame(
        coverage,
        columns=[
            "event_id",
            "rise_ft",
            "window_width_ft",
            "candidate_windows",
            "status",
            "error",
        ],
    )

    return windows, coverage_frame


def apply_strict_p50(
    windows: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply strict station-wide P50 thresholds to both metrics."""
    frame = windows.copy()

    first_threshold = float(
        frame[FIRST].quantile(
            DERIVATIVE_QUANTILE
        )
    )

    second_threshold = float(
        frame[SECOND].quantile(
            DERIVATIVE_QUANTILE
        )
    )

    frame["high_first"] = (
        np.isfinite(frame[FIRST])
        & (
            frame[FIRST]
            > first_threshold
        )
    )

    frame["high_second"] = (
        np.isfinite(frame[SECOND])
        & (
            frame[SECOND]
            > second_threshold
        )
    )

    frame["high_both_same_window"] = (
        frame["high_first"]
        & frame["high_second"]
    )

    # Descriptive percentile ranks later used by V15's event-level
    # joint-intensity score.
    frame["first_rank"] = (
        windows[FIRST]
        .rank(
            method="average",
            pct=True,
        )
    )

    frame["second_rank"] = (
        windows[SECOND]
        .rank(
            method="average",
            pct=True,
        )
    )

    thresholds = {
        "quantile": DERIVATIVE_QUANTILE,
        "first_metric": FIRST,
        "first_units": "ft/h",
        "first_threshold": first_threshold,
        "second_metric": SECOND,
        "second_units": "ft/h",
        "second_threshold": second_threshold,
        "comparison": "strictly greater",
        "total_windows": int(
            len(frame)
        ),
        "high_first_windows": int(
            frame["high_first"].sum()
        ),
        "high_second_windows": int(
            frame["high_second"].sum()
        ),
        "high_both_same_window": int(
            frame[
                "high_both_same_window"
            ].sum()
        ),
    }

    return frame, thresholds


def union_intervals(
    frame: pd.DataFrame,
) -> list[list[float]]:
    """Merge overlapping intervals belonging to one independent event."""
    if frame.empty:
        return []

    intervals = sorted(
        (
            round(float(low), DECIMALS),
            round(float(high), DECIMALS),
        )
        for low, high in zip(
            frame["window_lower_ft"],
            frame["window_upper_ft"],
        )
        if (
            np.isfinite(low)
            and np.isfinite(high)
            and high > low
        )
    )

    merged: list[list[float]] = []

    for low, high in intervals:
        if (
            not merged
            or low > merged[-1][1]
        ):
            merged.append(
                [low, high]
            )
        else:
            merged[-1][1] = max(
                merged[-1][1],
                high,
            )

    return merged


def intersect_intervals(
    first: list[list[float]],
    second: list[list[float]],
) -> list[list[float]]:
    """Intersect first/second unions for the same event."""
    result: list[list[float]] = []
    i = 0
    j = 0

    while (
        i < len(first)
        and j < len(second)
    ):
        low = max(
            first[i][0],
            second[j][0],
        )
        high = min(
            first[i][1],
            second[j][1],
        )

        if high > low:
            result.append(
                [low, high]
            )

        if first[i][1] < second[j][1]:
            i += 1
        elif second[j][1] < first[i][1]:
            j += 1
        else:
            i += 1
            j += 1

    return result


def event_regions(
    flagged: pd.DataFrame,
) -> pd.DataFrame:
    """Create all/first/second/joint interval unions per event."""
    records: list[dict[str, Any]] = []

    for event_id, group in flagged.groupby(
        "event_id",
        sort=False,
    ):
        all_intervals = union_intervals(
            group
        )

        first_intervals = union_intervals(
            group.loc[
                group["high_first"]
            ]
        )

        second_intervals = union_intervals(
            group.loc[
                group["high_second"]
            ]
        )

        joint_intervals = (
            intersect_intervals(
                first_intervals,
                second_intervals,
            )
        )

        for signal, intervals in (
            ("all", all_intervals),
            ("first", first_intervals),
            ("second", second_intervals),
            ("joint", joint_intervals),
        ):
            for low, high in intervals:
                records.append({
                    "event_id": str(
                        event_id
                    ),
                    "signal": signal,
                    "stage_lower_ft": low,
                    "stage_upper_ft": high,
                    "stage_width_ft": (
                        high - low
                    ),
                })

    return pd.DataFrame(
        records,
        columns=[
            "event_id",
            "signal",
            "stage_lower_ft",
            "stage_upper_ft",
            "stage_width_ft",
        ],
    )


def recurrence_by_overlap(
    regions: pd.DataFrame,
) -> pd.DataFrame:
    """Exact independent-event recurrence sweep over interval boundaries."""
    if regions.empty:
        return pd.DataFrame()

    boundaries = np.unique(
        np.concatenate([
            regions[
                "stage_lower_ft"
            ].to_numpy(float),
            regions[
                "stage_upper_ft"
            ].to_numpy(float),
        ])
    )
    boundaries.sort()

    if len(boundaries) < 2:
        return pd.DataFrame()

    counts: dict[
        str, np.ndarray
    ] = {}

    for signal in (
        "all",
        "first",
        "second",
        "joint",
    ):
        difference = np.zeros(
            len(boundaries) + 1,
            dtype=np.int64,
        )

        subset = regions.loc[
            regions["signal"].eq(signal)
        ]

        for row in subset.itertuples(
            index=False
        ):
            left = np.searchsorted(
                boundaries,
                row.stage_lower_ft,
            )
            right = np.searchsorted(
                boundaries,
                row.stage_upper_ft,
            )

            difference[left] += 1
            difference[right] -= 1

        counts[signal] = np.cumsum(
            difference
        )[:-2]

    rows: list[dict[str, Any]] = []

    for index in range(
        len(boundaries) - 1
    ):
        low = float(
            boundaries[index]
        )
        high = float(
            boundaries[index + 1]
        )

        if (
            high <= low
            or counts["all"][index] == 0
        ):
            continue

        rows.append({
            "stage_lower_ft": low,
            "stage_upper_ft": high,
            "events_with_windows": int(
                counts["all"][index]
            ),
            "events_high_first": int(
                counts["first"][index]
            ),
            "events_high_second": int(
                counts["second"][index]
            ),
            "events_high_both": int(
                counts["joint"][index]
            ),
        })

    if not rows:
        return pd.DataFrame()

    merged: list[
        dict[str, Any]
    ] = []

    keys = [
        "events_with_windows",
        "events_high_first",
        "events_high_second",
        "events_high_both",
    ]

    for row in rows:
        if (
            merged
            and np.isclose(
                merged[-1][
                    "stage_upper_ft"
                ],
                row[
                    "stage_lower_ft"
                ],
                atol=1e-8,
                rtol=0,
            )
            and all(
                merged[-1][key]
                == row[key]
                for key in keys
            )
        ):
            merged[-1][
                "stage_upper_ft"
            ] = row[
                "stage_upper_ft"
            ]
        else:
            merged.append(
                row.copy()
            )

    result = pd.DataFrame(
        merged
    )

    result[
        "stage_center_ft"
    ] = (
        result[
            "stage_lower_ft"
        ]
        + result[
            "stage_upper_ft"
        ]
    ) / 2

    result[
        "region_width_ft"
    ] = (
        result[
            "stage_upper_ft"
        ]
        - result[
            "stage_lower_ft"
        ]
    )

    result[
        "joint_recurrence_fraction"
    ] = (
        result[
            "events_high_both"
        ]
        / result[
            "events_with_windows"
        ]
    )

    # Historical V8 sort; concentration geometry later sorts by stage.
    result = result.sort_values(
        [
            "events_high_both",
            "stage_upper_ft",
        ],
        ascending=[
            False,
            False,
        ],
        kind="stable",
    ).reset_index(drop=True)

    result.insert(
        0,
        "recurrence_rank",
        np.arange(
            1,
            len(result) + 1,
        ),
    )

    return result


def recurrence_concentrations(
    ranking: pd.DataFrame,
) -> pd.DataFrame:
    """Find V13 local recurrence maxima/plateaus.

    The original V13 code also computed a SciPy prominence field. Prominence
    was not used by the frozen V15 selector, so it is intentionally omitted
    from the production selection interface.
    """
    if ranking.empty:
        return pd.DataFrame(
            columns=CONCENTRATION_COLUMNS
        )

    frame = ranking.loc[
        ranking[
            "events_high_both"
        ] >= MIN_JOINT_EVENTS
    ].sort_values(
        [
            "stage_lower_ft",
            "stage_upper_ft",
        ],
        kind="stable",
    ).reset_index(drop=True)

    if frame.empty:
        return pd.DataFrame(
            columns=CONCENTRATION_COLUMNS
        )

    lows = frame[
        "stage_lower_ft"
    ].to_numpy(float)

    highs = frame[
        "stage_upper_ft"
    ].to_numpy(float)

    counts = frame[
        "events_high_both"
    ].to_numpy(int)

    if (
        not np.isfinite(
            np.c_[lows, highs]
        ).all()
        or np.any(
            highs <= lows
        )
    ):
        raise ValueError(
            "Invalid overlap geometry."
        )

    if np.any(
        lows[1:]
        < highs[:-1] - 1e-8
    ):
        raise ValueError(
            "Overlapping recurrence regions."
        )

    boundaries = np.r_[
        0,
        np.flatnonzero(
            ~np.isclose(
                lows[1:],
                highs[:-1],
                atol=1e-8,
                rtol=0,
            )
        ) + 1,
        len(frame),
    ]

    records: list[
        dict[str, Any]
    ] = []

    for component_id, (
        start,
        stop,
    ) in enumerate(
        zip(
            boundaries[:-1],
            boundaries[1:],
        ),
        1,
    ):
        values = counts[
            start:stop
        ]

        cuts = np.r_[
            0,
            np.flatnonzero(
                values[1:]
                != values[:-1]
            ) + 1,
            len(values),
        ]

        runs = [
            (
                int(a),
                int(b),
                int(values[a]),
            )
            for a, b in zip(
                cuts[:-1],
                cuts[1:],
            )
        ]

        for run_index, (
            a,
            b,
            count,
        ) in enumerate(runs):
            left = (
                runs[
                    run_index - 1
                ][2]
                if run_index
                else 0
            )

            right = (
                runs[
                    run_index + 1
                ][2]
                if (
                    run_index + 1
                    < len(runs)
                )
                else 0
            )

            is_local_maximum = (
                count >= left
                and count >= right
                and (
                    count > left
                    or count > right
                )
            )

            if not is_local_maximum:
                continue

            low = float(
                lows[
                    start + a
                ]
            )
            high = float(
                highs[
                    start + b - 1
                ]
            )

            records.append({
                "component_id": int(
                    component_id
                ),
                "height_ft": (
                    low + high
                ) / 2,
                "stage_lower_ft": low,
                "stage_upper_ft": high,
                "plateau_width_ft": (
                    high - low
                ),
                "plateau_regions": int(
                    b - a
                ),
                "joint_events": int(
                    count
                ),
            })

    if not records:
        return pd.DataFrame(
            columns=CONCENTRATION_COLUMNS
        )

    peaks = pd.DataFrame(
        records
    ).sort_values(
        [
            "height_ft",
            "stage_lower_ft",
        ],
        kind="stable",
    ).reset_index(drop=True)

    peaks.insert(
        0,
        "concentration_rank",
        np.arange(
            1,
            len(peaks) + 1,
        ),
    )

    return peaks[
        CONCENTRATION_COLUMNS
    ]


def event_support_at_height(
    flagged: pd.DataFrame,
    intervals: pd.DataFrame,
    concentration: pd.Series,
) -> pd.DataFrame:
    """Return independent-event dynamic evidence at one concentration height."""
    height = float(
        concentration["height_ft"]
    )

    joint = intervals.loc[
        intervals["signal"].eq(
            "joint"
        )
        & intervals[
            "stage_lower_ft"
        ].le(height)
        & intervals[
            "stage_upper_ft"
        ].gt(height)
    ]

    event_ids = set(
        joint[
            "event_id"
        ].astype(str)
    )

    expected = int(
        concentration[
            "joint_events"
        ]
    )

    if len(event_ids) != expected:
        raise ValueError(
            "Point recurrence mismatch at "
            f"{height}: expected={expected}, "
            f"observed={len(event_ids)}."
        )

    low = np.round(
        flagged[
            "window_lower_ft"
        ].to_numpy(float),
        DECIMALS,
    )

    high = np.round(
        flagged[
            "window_upper_ft"
        ].to_numpy(float),
        DECIMALS,
    )

    at_point = flagged.loc[
        (low <= height)
        & (height < high)
        & flagged[
            "event_id"
        ].astype(str).isin(
            event_ids
        )
    ]

    records: list[
        dict[str, Any]
    ] = []

    for event_id, group in (
        at_point.groupby(
            "event_id",
            sort=True,
        )
    ):
        first = group.loc[
            group["high_first"],
            FIRST,
        ]

        second = group.loc[
            group["high_second"],
            SECOND,
        ]

        if (
            first.empty
            or second.empty
        ):
            raise ValueError(
                "Joint event lacks pointwise "
                f"supporting windows: {event_id}"
            )

        first_rank = float(
            group.loc[
                group["high_first"],
                "first_rank",
            ].max()
        )

        second_rank = float(
            group.loc[
                group["high_second"],
                "second_rank",
            ].max()
        )

        records.append({
            "event_id": str(
                event_id
            ),
            "height_ft": height,
            "first_value_ft_hr": float(
                first.max()
            ),
            "second_value_ft_hr": float(
                second.max()
            ),
            "first_rank": (
                first_rank
            ),
            "second_rank": (
                second_rank
            ),
            "joint_intensity_at_stage": min(
                first_rank,
                second_rank,
            ),
        })

    if len(records) != len(
        event_ids
    ):
        raise ValueError(
            "Point-support records do not "
            "match joint event IDs."
        )

    return pd.DataFrame(
        records
    )


def summarize_concentration_evidence(
    concentrations: pd.DataFrame,
    intervals: pd.DataFrame,
    flagged: pd.DataFrame,
    *,
    eligible_events: int,
    events_with_windows: int,
) -> pd.DataFrame:
    """Build one V15 evidence row per recurrence concentration."""
    summaries: list[
        dict[str, Any]
    ] = []

    for _, concentration in (
        concentrations.iterrows()
    ):
        support = (
            event_support_at_height(
                flagged,
                intervals,
                concentration,
            )
        )

        height = float(
            concentration[
                "height_ft"
            ]
        )

        count = int(
            concentration[
                "joint_events"
            ]
        )

        if (
            support[
                "event_id"
            ].duplicated().any()
            or len(support) != count
        ):
            raise ValueError(
                "Independent-event support "
                "inventory mismatch."
            )

        for field in (
            "first_rank",
            "second_rank",
            "joint_intensity_at_stage",
        ):
            values = support[
                field
            ].to_numpy(float)

            if (
                not np.isfinite(
                    values
                ).all()
                or np.any(
                    values <= 0
                )
                or np.any(
                    values > 1
                )
            ):
                raise ValueError(
                    "Invalid percentile ranks "
                    f"in {field}."
                )

        if not np.array_equal(
            support[
                "joint_intensity_at_stage"
            ].to_numpy(float),
            np.minimum(
                support[
                    "first_rank"
                ],
                support[
                    "second_rank"
                ],
            ),
        ):
            raise ValueError(
                "Joint intensity differs from "
                "min(first rank, second rank)."
            )

        counts: dict[
            str, int
        ] = {}

        for signal in (
            "all",
            "first",
            "second",
            "joint",
        ):
            rows = intervals.loc[
                intervals[
                    "signal"
                ].eq(signal)
                & intervals[
                    "stage_lower_ft"
                ].le(height)
                & intervals[
                    "stage_upper_ft"
                ].gt(height)
            ]

            counts[signal] = int(
                rows[
                    "event_id"
                ].nunique()
            )

        if not (
            count
            == counts["joint"]
            <= counts["first"]
            <= counts["all"]
            and count
            <= counts["second"]
            <= counts["all"]
            <= events_with_windows
            <= eligible_events
        ):
            raise ValueError(
                "Pointwise support/exposure "
                "counts are inconsistent."
            )

        record = {
            key: concentration[key]
            for key in (
                CONCENTRATION_COLUMNS
            )
        }

        record.update({
            "events_exposed_at_height": (
                counts["all"]
            ),
            "events_high_first_at_height": (
                counts["first"]
            ),
            "events_high_second_at_height": (
                counts["second"]
            ),
            "joint_fraction_of_exposed": (
                count
                / counts["all"]
            ),
            "eligible_events": int(
                eligible_events
            ),
            "events_with_windows": int(
                events_with_windows
            ),
        })

        for field in (
            "first_value_ft_hr",
            "second_value_ft_hr",
            "first_rank",
            "second_rank",
            "joint_intensity_at_stage",
        ):
            values = support[
                field
            ].to_numpy(float)

            for label, quantile in (
                ("min", 0.0),
                ("p25", 0.25),
                ("median", 0.50),
                ("p75", 0.75),
                ("max", 1.0),
            ):
                record[
                    f"{field}_{label}"
                ] = float(
                    np.quantile(
                        values,
                        quantile,
                    )
                )

        summaries.append(
            record
        )

    return pd.DataFrame(
        summaries
    )


def analyze_recurrence(
    peak_candidates_path,
    filtered_stage_path,
    *,
    state: str,
    site_id: str,
) -> dict[str, Any]:
    """Run the complete reference-free p50/P50 recurrence analysis."""
    events = load_events(
        peak_candidates_path
    )

    if events.empty:
        return {
            "status": "no_eligible_events",
            "state": state,
            "site_id": site_id,
            "eligible_events": 0,
            "events_with_windows": 0,
            "windows": 0,
            "regions": 0,
            "concentrations": 0,
            "window_width_ft": np.nan,
            "thresholds": {},
            "candidates": pd.DataFrame(),
            "coverage": pd.DataFrame(),
        }

    events = events.copy()

    events["event_id"] = [
        (
            f"{site_id}|"
            f"{event.segment_id}|"
            f"{event.date_start.isoformat()}|"
            f"{event.date_peak.isoformat()}"
        )
        for event in events.itertuples(
            index=False
        )
    ]

    segments = load_segments(
        filtered_stage_path
    )

    # Preserve the dtype coercion used by the frozen V13 experiment.
    for group in segments.values():
        group["datetime"] = (
            group["datetime"].astype(
                "datetime64[ns, UTC]"
            )
        )

    width_ft = adaptive_p50_width(
        events
    )

    windows, coverage = (
        build_station_windows(
            events,
            segments,
            state,
            site_id,
            width_ft,
        )
    )

    events_with_windows = int(
        coverage["status"].eq(
            "complete"
        ).sum()
    ) if not coverage.empty else 0

    if (
        not coverage.empty
        and coverage[
            "status"
        ].eq("failed").any()
    ):
        return {
            "status": (
                "event_processing_failed"
            ),
            "state": state,
            "site_id": site_id,
            "eligible_events": len(events),
            "events_with_windows": (
                events_with_windows
            ),
            "windows": len(windows),
            "regions": 0,
            "concentrations": 0,
            "window_width_ft": (
                width_ft
            ),
            "thresholds": {},
            "candidates": pd.DataFrame(),
            "coverage": coverage,
        }

    if windows.empty:
        return {
            "status": "no_valid_windows",
            "state": state,
            "site_id": site_id,
            "eligible_events": len(events),
            "events_with_windows": (
                events_with_windows
            ),
            "windows": 0,
            "regions": 0,
            "concentrations": 0,
            "window_width_ft": (
                width_ft
            ),
            "thresholds": {},
            "candidates": pd.DataFrame(),
            "coverage": coverage,
        }

    flagged, thresholds = (
        apply_strict_p50(
            windows
        )
    )

    intervals = event_regions(
        flagged
    )

    ranking = recurrence_by_overlap(
        intervals
    )

    concentrations = (
        recurrence_concentrations(
            ranking
        )
    )

    if concentrations.empty:
        return {
            "status": "no_concentrations",
            "state": state,
            "site_id": site_id,
            "eligible_events": len(events),
            "events_with_windows": (
                events_with_windows
            ),
            "windows": len(windows),
            "regions": len(ranking),
            "concentrations": 0,
            "window_width_ft": (
                width_ft
            ),
            "thresholds": thresholds,
            "candidates": pd.DataFrame(),
            "coverage": coverage,
        }

    candidates = (
        summarize_concentration_evidence(
            concentrations,
            intervals,
            flagged,
            eligible_events=len(events),
            events_with_windows=(
                events_with_windows
            ),
        )
    )

    return {
        "status": "candidate",
        "state": state,
        "site_id": site_id,
        "eligible_events": len(events),
        "events_with_windows": (
            events_with_windows
        ),
        "windows": len(windows),
        "regions": len(ranking),
        "concentrations": len(
            concentrations
        ),
        "window_width_ft": width_ft,
        "thresholds": thresholds,
        "candidates": candidates,
        "coverage": coverage,
    }
