# USGS Action Stage Estimator

**Research software | reference-free recurrent-stage estimation + NOAA/NWPS reference evaluation**

`usgs-action-stage-estimator` is a Python research package for analyzing USGS
water-stage observations, estimating a recurrent dynamic stage from rising-limb
behavior without using Action Stage as an estimator input, and evaluating
official NOAA National Water Prediction Service (NWPS) Action Stage references.

The package is research software. A recurrent dynamic-stage estimate is **not**
a validated bankfull level, an official NOAA Action Stage, or an operational
flood-warning threshold.

## Main modules

| Module | Purpose |
| --- | --- |
| `national_stage_processing.py` | Supports national-scale P00 stage/peak processing. |
| `identifiers.py` | Validates and preserves USGS station identifiers. |
| `station_inventory.py` | Builds a station inventory from processing outputs and NOAA reference metadata. |
| `noaa_api.py` | Retrieves and normalizes NOAA NWPS gauge information. |
| `reference_validation.py` | Validates/harmonizes historical Action Stage references and provides evaluation-only stage-reference scale diagnostics. |
| `reference_lookup.py` | Retrieves NOAA Action Stage information and checks compatibility with historical references. |
| `flood_reference_export.py` | Exports NOAA flood-reference information. |
| `peak_distributions.py` | Computes peak-stage distribution statistics. |
| `peak_distribution_export.py` | Exports peak-stage distribution results. |
| `e03_dynamics.py` | Historical E03 first/second derivative calculations using actual observation intervals. |
| `e03_station_windows.py` | Historical E03 moving 1 ft derivative-window analysis. |
| `e03_recurrence.py` | Reference-free independent-event recurrence mechanics for the validated recurrent-stage method. |
| `e03_recurrent_stage.py` | Recommended reference-free V15 recurrent dynamic-stage selector. |
| `pipeline.py` | Reserved for future higher-level orchestration; current workflows use explicit runners. |

Modules live under `src/usgs_action_stage_estimator/`.

## Recommended recurrent-stage estimator

The package's recommended recurrent-stage method is the frozen and fully
regression-checked V15 configuration:

`E03-RS-V15-p50-d50-top3-RI-v1`

It does **not** read NOAA/NWS Action Stage.

### Method

1. Read detected rising events and retain events with total rise strictly greater than 1 ft.
2. Set traversal width to `max(1 ft, median eligible-event rise)`.
3. Build complete event-local rising-limb stage traversals from original UTC observations.
4. Calculate `mean_first_ft_hr` (mean stage-rise rate, ft/h) and
   `cumulative_positive_second_ft_hr` (cumulative positive change in stage-rise rate, ft/h).
5. Apply strict station-wide P50 thresholds independently to both metrics.
6. Union high-metric intervals within each independent event and calculate exact first/second overlap.
7. Sweep all event interval boundaries to calculate exact independent-event joint recurrence.
8. Require at least two independent jointly supporting events.
9. Identify local recurrence maxima/plateaus ("concentrations").
10. Calculate `R = joint_events / max_joint_events`,
    `I = median(min(first_percentile_rank, second_percentile_rank))`,
    and score `R * I`.
11. Restrict selection to the three highest-stage concentrations.
12. Select maximum `R * I`, with deterministic tie-breaking by joint-event support,
    higher stage, and concentration rank.

The returned `estimated_stage_ft` is selected entirely from stage-time-series
dynamics and recurrence.

### Important terminology

The first recurrence metric is **stage-rise rate**, not streamflow velocity.

The second recurrence metric is cumulative positive change in stage-rise rate,
with implemented traversal units of **ft/h**. It is distinct from the
instantaneous second derivative in `e03_dynamics.py`, which is stage
acceleration in **ft/h²**.

## Public API

```python
from usgs_action_stage_estimator import estimate_recurrent_stage

result = estimate_recurrent_stage(
    "peak_candidates.parquet",
    "filtered_stage.parquet",
    state="IOWA",
    site_id="05485640",
)

print(result["status"])
print(result["estimated_stage_ft"])
print(result["joint_events"])
print(result["selection_score"])
```

NOAA Action Stage lookup remains separate:

```python
from usgs_action_stage_estimator import get_action_stage

reference = get_action_stage("08165500")
```

## Processing scripts

| Script | Purpose |
| --- | --- |
| `scripts/run_national_stage_processing.py` | Runs national P00 stage/peak processing. |
| `scripts/run_national_e03.py` | Runs the historical derivative/window E03 workflow for stations with validated Action Stage references. |
| `scripts/run_national_e03_recurrent_stage.py` | Runs the recommended V15 recurrent-stage estimator nationally without reading NOAA/Action Stage references. |
| `scripts/check_e03_recurrent_stage_regression.py` | Regression-checks the clean implementation against the frozen V15 research result. |

Historical V5-V22 exploratory scripts are no longer part of the active package
tree; they are preserved separately as research provenance.

## Historical derivative/window E03 workflow

The v0.1.0 derivative/window workflow remains available for reproducibility.
Its second derivative is stage acceleration in ft/h². That is not the same
quantity as the recurrent method's `cumulative_positive_second_ft_hr`.

## Stage-reference compatibility diagnostics

`assess_stage_reference_scale(...)` compares official Action Stage with the raw
observed USGS/P00 `Stage_ft` distribution. This is evaluation/QC only; it never
changes or selects the recurrent-stage estimate.

The default diagnostic margin is +/-10 ft around the raw observed stage range.
That reproduces the post-validation reference-scale audit; it is not an
estimator tolerance and does not prove datum equivalence.

## Results record

The complete V15 development, reproducibility, prospective-validation, V15-vs-V22, and stage-reference compatibility results are recorded in [`docs/V15_RESULTS.md`](docs/V15_RESULTS.md).

## Validation and reproducibility

### Clean implementation regression

The cleaned package implementation reproduced the frozen national V15
reference-free research output on **3,717 / 3,717 stations**, with zero failures.
The regression checks selected stage, independent-event support, concentration
rank, `R`, `I`, `F`, selection score, and supporting metric summaries.

### Prospective validation

A label-blind prospective registry was frozen before NOAA/NWPS Action Stage
labels were acquired.

- prospective registry: **4,833**
- official finite Action Stage labels acquired: **737**
- stations with official label and finite frozen prediction: **691**

For the primary objective `-5 ft <= estimate - Action Stage < 0 ft`:

| Metric | V15 | V22 research sensitivity |
| --- | ---: | ---: |
| target `[-5, 0)` | **362** | 360 |
| below -5 ft | 196 | **194** |
| above +5 ft | 29 | 29 |
| within +/-5 ft | 466 | **468** |
| median signed error | -2.770 ft | **-2.665 ft** |

V22 modestly improved negative-tail and +/-5-ft behavior, but its development
strict-target gain did not reproduce prospectively. V15 therefore remains the
active package estimator.

### Reference-scale audit

All **39** evaluable stations with absolute V22 signed error greater than
100 ft also had official Action Stage outside the raw P00 `Stage_ft`
minimum/maximum expanded by +/-10 ft. There were zero >100-ft errors where that
observed-range diagnostic passed.

Those stations remained in the primary validation. This finding motivates
reference-scale QC; it does not define an error-based exclusion rule.

## Installation and development

Requires Python 3.11 or later.

```bash
python -m pip install -e '.[dev]'
python -m pytest -q tests/
```

Reference-free national recurrent-stage run:

```bash
python -u scripts/run_national_e03_recurrent_stage.py --limit 10 --resume
python -u scripts/run_national_e03_recurrent_stage.py --resume
```

Historical Action-Stage-referenced E03 run:

```bash
python -u scripts/run_national_e03.py --controls --fail-fast
python -u scripts/run_national_e03.py --limit 10 --resume
python -u scripts/run_national_e03.py --resume
```

## Research status

The recurrent-stage method supports reproducible hydrological research and
continued methodological improvement. It should not be represented as an
official flood-warning threshold or replacement for NOAA/NWS products.

**Author:** Gonzalo Forero Buitrago
**License declared in project metadata:** Apache-2.0
