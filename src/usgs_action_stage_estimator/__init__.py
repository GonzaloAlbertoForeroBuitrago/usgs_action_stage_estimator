"""USGS Action Stage Estimator.

Independent hydrological analysis and NOAA reference comparison.
"""

from .reference_lookup import get_action_stage

__all__ = ["get_action_stage"]
