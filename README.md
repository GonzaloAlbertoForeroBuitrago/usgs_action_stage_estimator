# USGS Action Stage Estimator

**Research software | Initial release draft**

`usgs-action-stage-estimator` is a Python research package for analyzing USGS water-stage observations, evaluating NOAA National Water Prediction Service (NWPS) Action Stage references, and exploring stage-dependent changes in rising-limb dynamics. Its goal is to support reproducible research toward estimating useful flood-warning stage indicators.

 The derivative-based Action Stage estimation approach is experimental. A winning stage window is a research diagnostic, **not** a validated bankfull level, NOAA Action Stage estimate, or operational flood warning.

## Main modules

| Module | Purpose |
| --- | --- |
| `pipeline.py` | Coordinates package processing workflows. |
| `national_stage_processing.py` | Supports national-scale P00 stage/peak processing. |
| `identifiers.py` | Validates and preserves USGS station identifiers. |
| `station_inventory.py` | Builds a station inventory from processing outputs and NOAA reference metadata. |
| `noaa_api.py` | Retrieves and normalizes NOAA NWPS gauge information. |
| `reference_validation.py` | Validates and harmonizes historical Action Stage reference records. |
| `reference_lookup.py` | Retrieves NOAA Action Stage information and checks compatibility with historical references. |
| `flood_reference_export.py` | Exports NOAA flood-reference information. |
| `peak_distributions.py` | Computes peak-stage distribution statistics. |
| `peak_distribution_export.py` | Exports peak-stage distribution results. |
| `e03_dynamics.py` | Calculates first and second stage derivatives using actual observation intervals; ranks events by derivative statistics. |
| `e03_station_windows.py` | Scores moving 1 ft stage windows with equal event weighting and compares winning windows with Action Stage. |

Modules live under `src/usgs_action_stage_estimator/`.

## Processing scripts

| Script | Purpose |
| --- | --- |
| `scripts/run_national_stage_processing.py` | Runs the existing national P00 processing workflow. |
| `scripts/run_national_e03.py` | Runs the resumable national E03 analysis for stations with validated Action Stage references. |

The `scripts/explore_e03_*.py` files are exploratory research scripts used to develop and validate the E03 method; they are not the primary public API.

## E03 research workflow

1. Read previously processed USGS stage observations and detected rising events.
2. Validate each event's start and peak against its original observations and UTC timestamps.
3. Calculate average start-to-peak rise rate and event-level P90 positive acceleration.
4. Independently select the upper half of valid events for each metric; analyze their intersection.
5. Calculate interval-level derivatives on the selected rising limbs, using actual elapsed time without resampling.
6. Move 1 ft stage windows at 0.25 ft center increments. Calculate one mean derivative per event per window, then average equally across contributing events.
7. Select the highest-scoring supported window for each derivative (baseline minimum: five contributing events), and compare its stage range with validated NOAA Action Stage.

The first derivative is the **rate of stage change (ft/h)**, not streamflow velocity. The second derivative is **stage acceleration (ft/h²)**. Both are sensitive to sampling interval, observation quality, and event selection.

## Installation and development

Requires Python 3.11 or later.

```bash
python -m pip install -e '.[dev]'
python -m pytest -q tests/
```

For the current national research workflow, the runner expects existing P00 outputs and the package's validated NOAA reference table; it does **not** download or construct the full national dataset automatically.

```bash
python -u scripts/run_national_e03.py --controls --fail-fast
python -u scripts/run_national_e03.py --limit 10 --resume
python -u scripts/run_national_e03.py --resume
```

Results are written under `~/Documents/usgs_mrms_research/outputs/action_stage_estimator/E03/national/` in the current research setup. The runner uses a methodology version to support resuming compatible completed results.

## Validation and reproducibility

The initial E03 implementation reproduced the previously established first- and second-derivative winning windows for four control stations (Texas, Wisconsin, Georgia, and Maryland). The repository test suite passed **66 tests** at the last reported checkpoint. The national-scale evaluation is ongoing; the four-station results should not be generalized to all USGS stations without additional validation.



**Author:** Gonzalo Forero Buitrago  
**License declared in project metadata:** Apache-2.0
