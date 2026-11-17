# Changelog

All notable package changes are documented here.

## 0.2.0

### Added

- Reference-free recurrent dynamic-stage estimation through
  `estimate_recurrent_stage(...)`.
- Clean independent-event recurrence mechanics in `e03_recurrence.py`.
- Frozen V15 recurrent-stage selector in `e03_recurrent_stage.py`.
- Reference-free national recurrent-stage runner:
  `scripts/run_national_e03_recurrent_stage.py`.
- Regression checker against the frozen V15 national research result.
- Evaluation-only stage-reference scale diagnostic:
  `assess_stage_reference_scale(...)`.
- Public exports for the recurrent-stage methodology version and estimator.
- Tests covering recurrence, V15 selection, public API, and reference-scale QC.

### Validation

A complete release results record is included in `docs/V15_RESULTS.md`, separating development results, code reproducibility, independent prospective validation, and the stage-reference compatibility audit.

The cleaned recurrent-stage implementation was regression-checked against the
frozen V15 national result on all 3,717 development stations:

- passes: 3,717
- failures: 0

A prospective validation registry was frozen before acquiring new NOAA/NWPS
Action Stage labels:

- prospective registry: 4,833 stations
- official finite Action Stage labels: 737
- evaluable stations with finite frozen V15/V22 predictions: 691

For the primary signed-error target `-5 <= estimate - ActionStage < 0`:

- V15: 362 stations
- V22 research sensitivity: 360 stations

V15 therefore remains the active package estimator. V22 is retained as
research provenance/sensitivity evidence rather than the default package
selection path.

### Reference compatibility finding

The prospective audit identified a separate stage/reference-scale issue. All
39 evaluable stations with absolute V22 signed error greater than 100 ft had
official Action Stage outside the raw observed P00 `Stage_ft` minimum/maximum
expanded by +/-10 ft. These stations remain part of the primary validation;
the finding is exposed only as evaluation/reference QC.

### Changed

- README expanded to distinguish:
  - historical E03 derivative/window analysis;
  - validated reference-free recurrent-stage estimation;
  - NOAA/NWPS reference evaluation.
- Package description updated to include recurrent-stage estimation.
- Historical v0.1.0 E03 modules remain available for reproducibility.

### Repository cleanup

The V5-V22 exploratory/audit script tree was archived outside the active
package repository with SHA256 provenance before this release. The research
history remains reproducible without shipping obsolete experiment scripts in
the active package tree.

## 0.1.0

Initial published research package containing national stage processing,
NOAA/NWPS Action Stage reference handling, peak distributions, and the
historical E03 derivative/window workflow.
