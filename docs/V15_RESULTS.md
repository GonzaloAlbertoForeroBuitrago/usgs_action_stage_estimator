# V15 results and validation record

This document records the results supporting the recurrent-stage method shipped
with `usgs-action-stage-estimator` 0.2.0.

The active package estimator is:

`E03-RS-V15-p50-d50-top3-RI-v1`

The estimator is reference-free: NOAA/NWS Action Stage is not used to select
the recurrent stage.

## 1. Development benchmark

The frozen V15 configuration is:

`v15__p50__d50__top3__recurrence_intensity`

Development population:

- stations scheduled: **3,717**
- stations evaluated against the available Action Stage reference: **3,529**
- stations without an evaluable reference/result pair: **188**

Signed error is defined as:

`estimated_stage_ft - action_stage_ft`

Development results:

| Metric | V15 |
| --- | ---: |
| target `[-5, 0)` | **2,099** |
| target fraction of evaluated stations | **59.48%** |
| below -5 ft | 769 |
| nonnegative | 661 |
| above +5 ft | 90 |
| within +/-5 ft | **2,670** |
| within +/-5 fraction | **75.66%** |
| outside +/-5 ft | 859 |
| minimum signed error | -29.995 ft |
| maximum signed error | 17.415 ft |
| mean signed error | -2.75191 ft |
| median signed error | -2.275 ft |
| MAE | 3.650805 ft |

These are development results. They were used to select and understand the
method and must not be described as independent validation.

## 2. Development comparison with the earlier transparent V13 rule

The earlier transparent V13 configuration
`p50__d50__top3` produced:

| Metric | V13 | V15 |
| --- | ---: | ---: |
| target `[-5, 0)` | 2,089 | **2,099** |
| below -5 ft | **745** | 769 |
| nonnegative | 695 | **661** |
| above +5 ft | 104 | **90** |

V15 therefore produced a modest net improvement in the strict target count and
reduced the positive tail, while increasing the negative tail. This trade-off
was one reason later V16-V22 experiments focused on representation and
left-tail behavior.

## 3. Clean implementation reproducibility

The research implementation was extracted into the package modules:

- `e03_recurrence.py`
- `e03_recurrent_stage.py`

The clean implementation was regression-checked against the frozen V15
reference-free output.

Final release regression:

- stations: **3,717**
- passes: **3,717**
- failures: **0**

The regression checks the selected stage and the supporting V15 selection
fields, including:

- independent-event joint support;
- selected concentration rank;
- `R`;
- `I`;
- `F`;
- `R * I` selection score;
- median supporting first metric;
- median supporting second metric.

This is a code-reproducibility result, not an accuracy-validation result.

## 4. Prospective validation design

A prospective validation population was created only after the method was
frozen.

Sequence:

1. freeze the V22-era reference-free prediction implementation;
2. generate predictions for stations outside the 3,717-station development
   cohort;
3. hash and freeze the prediction file;
4. create a label-blind registry containing only station identifiers;
5. only then acquire new NOAA/NWPS Action Stage labels;
6. evaluate the previously frozen V15 and V22 predictions.

Prospective registry:

- registry stations: **4,833**
- finite frozen recurrent-stage predictions: **4,249**
- official finite NOAA/NWPS Action Stage labels acquired: **737**
- stations with both an official label and finite frozen V15/V22 prediction:
  **691**

This 691-station population is the primary independent comparison reported
below.

## 5. Independent prospective V15 result

On the 691 evaluable prospective stations:

| Metric | Frozen V15 |
| --- | ---: |
| target `[-5, 0)` | **362** |
| target fraction | **52.39%** |
| below -5 ft | 196 |
| `0 to +5` ft | 104 |
| above +5 ft | 29 |
| within +/-5 ft | **466** |
| within +/-5 fraction | **67.44%** |
| outside +/-5 ft | 225 |
| median signed error | -2.770 ft |
| minimum signed error | -1643.1125 ft |
| maximum signed error | 603.3450 ft |
| raw MAE | 39.253064 ft |

The extreme minimum/maximum and raw MAE are strongly affected by the separate
stage-reference compatibility problem described below. They are retained in the
primary validation rather than silently excluded.

## 6. Independent V15 vs V22 comparison

V22 was developed as a conservative upward representation adjustment to V15.
It improved several development metrics, but the strict target improvement did
not reproduce prospectively.

| Metric | V15 | V22 |
| --- | ---: | ---: |
| target `[-5, 0)` | **362** | 360 |
| below -5 ft | 196 | **194** |
| `0 to +5` ft | 104 | 108 |
| above +5 ft | 29 | 29 |
| within +/-5 ft | 466 | **468** |
| median signed error | -2.770 ft | **-2.665 ft** |
| raw MAE | 39.253064 ft | **39.168888 ft** |

Paired transitions from V15 to V22:

- gained target: **2**
- lost target: **4**
- net target change: **-2**
- below -5 to target: **2**
- target to nonnegative: **4**
- target to below -5: **0**
- above +5 to target: **0**

State-cluster bootstrap from the prospective comparison:

- probability V22 improves the strict target count: **9.29%**
- probability V22 reduces the below--5 tail: **87.08%**
- probability V22 improves within +/-5 coverage: **87.08%**
- probability V22 reduces paired MAE: **100%** in the bootstrap replicates

Release interpretation:

- **V15 remains the active package estimator** because the project primary
  objective is the strictly negative `[-5, 0)` signed-error band.
- V22 remains useful research evidence for reducing the negative tail and
  absolute error, but is not the primary release selector.

## 7. Stage-reference compatibility audit

The prospective validation revealed a separate interoperability issue between
official Action Stage and the raw observed P00 `Stage_ft` scale at some
stations.

Official labels inspected: **737**

Raw reference diagnostics:

| Diagnostic | Stations |
| --- | ---: |
| readable P00 stage series | 737 |
| Action Stage inside observed min/max | 578 |
| inside observed min/max +/-5 ft | 654 |
| inside observed min/max +/-10 ft | 668 |
| abs(Action Stage - stage median) >20 ft | 85 |
| abs(Action Stage - stage median) >100 ft | 41 |

Among the 691 stations with finite frozen predictions:

- stations with `|V22 signed error| > 100 ft`: **39**
- of those 39, Action Stage outside observed Stage_ft min/max +/-10 ft:
  **39**
- `|V22 error| >100 ft` while the +/-10-ft range diagnostic passed:
  **0**

This strongly indicates a stage/reference-scale compatibility problem for the
largest apparent errors.

Important interpretation:

- these stations remain in the primary prospective validation;
- the compatibility diagnostic is not used to select or modify the predicted
  recurrent stage;
- the diagnostic does not by itself prove which datum/reference convention is
  correct;
- package code exposes this only as evaluation/reference QC.

## 8. Current release conclusion

The evidence available through the 0.2.0 release supports the following
package decision:

1. **V15 is the recommended recurrent-stage estimator.**
2. V15 uses no Action Stage information in selection.
3. The clean V15 implementation exactly reproduces the frozen national research
   result on all 3,717 development stations.
4. The independent prospective sample does not support replacing V15 with V22
   for the primary `[-5, 0)` objective.
5. Stage-reference compatibility must be reviewed separately when official
   Action Stage and observed P00 stage are on visibly incompatible scales.

## 9. Frozen/reproducibility artifacts

The research archive outside the active package repository retains the
intermediate V5-V22 experiment scripts and national outputs.

Key release-era artifacts include:

- frozen V15 national selection output;
- full clean V15 3,717-station regression result;
- prospective prediction freeze and SHA256;
- label-blind validation registry and SHA256;
- NOAA/NWPS acquired-label freeze and SHA256;
- independent V15-vs-V22 validation outputs;
- stage-reference compatibility audit.

Large research products are intentionally not bundled inside the Python wheel.
