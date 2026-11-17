"""Clean E03 recurrent dynamic-stage estimator.

The active production selector is the frozen V15 configuration:

    p50 traversal width
    strict station-wide P50 dynamics
    top-3 highest-stage recurrence concentrations
    maximize recurrence-intensity = R * I

where

    R = joint_events / max_joint_events
    I = median across supporting independent events of
        min(first_percentile_rank, second_percentile_rank)

NOAA/NWS Action Stage is not an input and is not imported.

Scientific status
-----------------
V15 remains the recommended recurrent-stage method because the later genuinely
prospective validation did not reproduce V22's development gain for the primary
signed-error objective ``-5 <= estimate - ActionStage < 0``.

Historical V22 experiments remain research provenance and are not part of this
first cleaned production selector.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .e03_recurrence import (
    analyze_recurrence,
)


METHODOLOGY_VERSION = (
    "E03-RS-V15-p50-d50-top3-RI-v1"
)

WIDTH_RULE = "p50"
DERIVATIVE_QUANTILE = 0.50
HEIGHT_GATE = "top3"
SCORE_RULE = "recurrence_intensity"


def prepare_scores(
    candidates: pd.DataFrame,
) -> pd.DataFrame:
    """Create the allowlisted V15 scoring features.

    No reference-stage or error column is retained or accepted.
    """
    columns = [
        "concentration_rank",
        "height_ft",
        "joint_events",
        "events_exposed_at_height",
        "joint_intensity_at_stage_median",
        "first_value_ft_hr_median",
        "second_value_ft_hr_median",
    ]

    if candidates.empty:
        return pd.DataFrame(
            columns=(
                columns
                + [
                    "R",
                    "I",
                    "F",
                    "recurrence_intensity",
                ]
            )
        )

    missing = (
        set(columns)
        - set(candidates.columns)
    )

    if missing:
        raise ValueError(
            "Incomplete V15 candidate schema: "
            f"{sorted(missing)}"
        )

    frame = candidates[
        columns
    ].copy()

    frame["R"] = (
        frame["joint_events"]
        / frame[
            "joint_events"
        ].max()
    )

    frame["I"] = frame[
        "joint_intensity_at_stage_median"
    ]

    frame["F"] = (
        frame["joint_events"]
        / frame[
            "events_exposed_at_height"
        ]
    )

    frame[
        "recurrence_intensity"
    ] = (
        frame["R"]
        * frame["I"]
    )

    return frame.sort_values(
        [
            "height_ft",
            "concentration_rank",
        ],
        kind="stable",
    )


def select_v15_candidate(
    candidates: pd.DataFrame,
) -> tuple[pd.Series | None, int]:
    """Select the frozen V15 top-3 recurrence-intensity candidate."""
    prepared = prepare_scores(
        candidates
    )

    if prepared.empty:
        return None, 0

    considered = prepared.tail(
        3
    )

    winner = considered.sort_values(
        [
            "recurrence_intensity",
            "joint_events",
            "height_ft",
            "concentration_rank",
        ],
        ascending=[
            False,
            False,
            False,
            True,
        ],
        kind="stable",
    ).iloc[0]

    return winner, len(considered)


def estimate_recurrent_stage(
    peak_candidates_path,
    filtered_stage_path,
    *,
    state: str,
    site_id: str,
) -> dict[str, Any]:
    """Estimate one reference-free recurrent dynamic stage.

    Parameters
    ----------
    peak_candidates_path
        P00 ``peak_candidates.parquet``.
    filtered_stage_path
        P00 ``filtered_stage.parquet``.
    state, site_id
        Stable station identifiers used for evidence/provenance.

    Returns
    -------
    dict
        JSON-serializable station result. ``estimated_stage_ft`` is NaN when
        evidence is insufficient or station processing is invalid.
    """
    base = {
        "methodology_version": (
            METHODOLOGY_VERSION
        ),
        "state": str(state),
        "site_id": str(site_id),
        "width_rule": WIDTH_RULE,
        "derivative_quantile": (
            DERIVATIVE_QUANTILE
        ),
        "height_gate": HEIGHT_GATE,
        "score_rule": SCORE_RULE,
        "status": "",
        "estimated_stage_ft": np.nan,
        "selected_rank": np.nan,
        "joint_events": 0,
        "events_exposed_at_height": 0,
        "eligible_events": 0,
        "events_with_windows": 0,
        "window_width_ft": np.nan,
        "windows": 0,
        "regions": 0,
        "concentrations": 0,
        "considered": 0,
        "R": np.nan,
        "I": np.nan,
        "F": np.nan,
        "selection_score": np.nan,
        "first_value_ft_hr_median": np.nan,
        "second_value_ft_hr_median": np.nan,
        "first_threshold_ft_hr": np.nan,
        "second_threshold_ft_hr": np.nan,
    }

    try:
        analysis = analyze_recurrence(
            peak_candidates_path,
            filtered_stage_path,
            state=str(state),
            site_id=str(site_id),
        )
    except Exception as exc:
        result = base.copy()
        result["status"] = (
            "invalid_input"
        )
        result["error_type"] = (
            type(exc).__name__
        )
        result["message"] = str(
            exc
        )
        return result

    result = base.copy()

    for key in (
        "eligible_events",
        "events_with_windows",
        "window_width_ft",
        "windows",
        "regions",
        "concentrations",
    ):
        result[key] = analysis[
            key
        ]

    thresholds = analysis.get(
        "thresholds", {}
    )

    result[
        "first_threshold_ft_hr"
    ] = thresholds.get(
        "first_threshold",
        np.nan,
    )

    result[
        "second_threshold_ft_hr"
    ] = thresholds.get(
        "second_threshold",
        np.nan,
    )

    if analysis[
        "status"
    ] != "candidate":
        result["status"] = analysis[
            "status"
        ]
        return result

    winner, considered = (
        select_v15_candidate(
            analysis[
                "candidates"
            ]
        )
    )

    if winner is None:
        result["status"] = (
            "no_candidate"
        )
        return result

    result.update({
        "status": "candidate",
        "estimated_stage_ft": float(
            winner[
                "height_ft"
            ]
        ),
        "selected_rank": int(
            winner[
                "concentration_rank"
            ]
        ),
        "joint_events": int(
            winner[
                "joint_events"
            ]
        ),
        "events_exposed_at_height": int(
            winner[
                "events_exposed_at_height"
            ]
        ),
        "considered": int(
            considered
        ),
        "R": float(
            winner["R"]
        ),
        "I": float(
            winner["I"]
        ),
        "F": float(
            winner["F"]
        ),
        "selection_score": float(
            winner[
                "recurrence_intensity"
            ]
        ),
        "first_value_ft_hr_median": float(
            winner[
                "first_value_ft_hr_median"
            ]
        ),
        "second_value_ft_hr_median": float(
            winner[
                "second_value_ft_hr_median"
            ]
        ),
    })

    return result
