"""USGS Action Stage Estimator.

Reference-free recurrent dynamic-stage estimation, hydrological analysis,
and NOAA/NWPS Action Stage reference comparison.
"""

from .e03_recurrent_stage import (
    METHODOLOGY_VERSION as RECURRENT_STAGE_METHODOLOGY_VERSION,
    estimate_recurrent_stage,
)
from .reference_lookup import get_action_stage
from .reference_validation import assess_stage_reference_scale

__all__ = [
    "RECURRENT_STAGE_METHODOLOGY_VERSION",
    "assess_stage_reference_scale",
    "estimate_recurrent_stage",
    "get_action_stage",
]
