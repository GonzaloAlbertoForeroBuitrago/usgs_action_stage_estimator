# Recurrent dynamic-stage methodology

## Release method

The package release method is:

`E03-RS-V15-p50-d50-top3-RI-v1`

It estimates a recurrent dynamic stage from USGS stage-time-series behavior
without reading NOAA/NWS Action Stage.

Action Stage is used only in separate evaluation/reference workflows.

## Input products

The recurrent estimator consumes the existing P00 station products:

- `peak_candidates.parquet`
- `filtered_stage.parquet`

## Event population

Only `detected_event` rising events are eligible, with:

`rise_ft > 1 ft`

The same flood remains one independent event throughout recurrence counting.

## Adaptive traversal width

For each station:

`width_ft = max(1 ft, median eligible-event rise)`

## Complete rising-limb traversals

For each eligible event, the method finds complete stage traversals from
`H` to `H + width_ft` using actual UTC observations and linearly interpolated
level crossings.

A traversal is rejected if any contributing observation interval exceeds
60 minutes.

## Dynamic metrics

### Stage-rise rate

`mean_first_ft_hr = width_ft / traversal_duration_hr`

Units: ft/h.

This is water-level rise rate, not stream-water velocity.

### Cumulative positive change in stage-rise rate

`cumulative_positive_second_ft_hr`

This is the cumulative positive change in interval stage-rise rates across the
traversal. Its validated traversal quantity is expressed in ft/h.

It is distinct from the historical `e03_dynamics.py` second derivative, which
is instantaneous stage acceleration in ft/h^2.

## Significant windows

The method calculates station-wide P50 thresholds for both traversal metrics.
A window is high only when it is strictly greater than the corresponding P50.

## Independent-event recurrence

Within each event, overlapping high-window intervals are unioned before
recurrence is counted. The first- and second-metric unions are intersected
within the same event to form joint dynamic-support intervals.

All event interval boundaries are swept exactly. At any stage, an event
contributes at most one count.

A recurrent joint region requires at least two independent supporting events.

## Concentrations

Connected recurrence regions are examined for local recurrence maxima or
plateaus. Each local maximum/plateau becomes a concentration candidate whose
height is the plateau midpoint.

## V15 evidence and score

For candidate `j`:

`R_j = joint_events_j / max_joint_events`

For each supporting event:

`joint_intensity = min(first_percentile_rank, second_percentile_rank)`

Then:

`I_j = median(joint_intensity)`

and:

`S_j = R_j * I_j`

## Final selection

Candidates are ordered by stage. Only the three highest-stage concentrations
are considered. The selected stage maximizes `R * I`.

Ties are broken deterministically by:

1. larger `joint_events`;
2. higher stage;
3. lower concentration rank.

## Output evidence

The result includes the estimated stage plus recurrence strength, event
support, score components, traversal width, event/window/concentration counts,
and P50 thresholds.

Insufficient-evidence stations remain explicit missing predictions and are
never replaced by a reference-informed estimate.

## Validation status

The clean package implementation reproduces the frozen V15 result on all
3,717 development stations with zero regression failures.

The later prospective validation did not reproduce V22's development advantage
for the primary `[-5, 0)` signed-error target. V15 therefore remains the
package release estimator.

## Reference-scale QC

Official Action Stage and observed P00 stage may occasionally use incompatible
stage/reference scales.

`assess_stage_reference_scale(...)` is evaluation-only. It must not alter the
recurrent-stage estimate or silently remove stations from primary validation.

## Detailed results

The complete numerical development and independent-validation record is maintained in [`V15_RESULTS.md`](V15_RESULTS.md).
