# 0.2.0 release review

This release integrates the strongest validated recurrent-stage method into the
existing `usgs-action-stage-estimator` architecture.

## Included

- all existing v0.1.0 national processing/reference functionality;
- historical E03 derivative/window workflow;
- cleaned V15 independent-event recurrence estimator;
- reference-free national recurrent-stage runner;
- frozen V15 regression checker;
- stage-reference scale QC for evaluation;
- expanded public API and documentation.

## Frozen scientific decision

V15 is the active recurrent-stage estimator.

V22 is not shipped as the primary estimator because the prospective validation
did not reproduce its development gain for the primary `[-5,0)` objective.

## Required pre-publication gates

Before commit/tag/publish:

1. complete pytest suite passes;
2. 30-station V15 regression passes after metadata/docs changes;
3. package builds sdist and wheel;
4. wheel installs into a clean temporary virtual environment;
5. installed package exposes the new public API;
6. installed distribution reports version `0.2.0`;
7. temporary/research artifacts are absent from the wheel;
8. Git diff/status is reviewed;
9. final 3,717-station regression is rerun before the release tag.
