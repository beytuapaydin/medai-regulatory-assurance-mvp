# RC1.3 — Independent development OOF numerical recomputation

**Status:** Independent fixed-threshold metric recomputation **PASS**; exploratory whole-patient bootstrap interval **close but not bitwise/numerically identical to historical audit**; historical original generator **not recovered**.

This is a **local, read-only, development-only** external rerun reported by the project operator on 18 November 2026. The investigator's aggregate console output is reproduced in summary; original input datasets, local generated aggregate JSON and the independent script were not deposited in this Git branch. Accordingly, this report is an **operator-reported verification record**, not a reproducible fresh CI result. The frozen RC1.1 tag remains immutable.

## Locked inputs and test scope

| Item | Evidence |
|---|---|
| Full OOF prediction CSV | `training_oof_predictions.csv` SHA-256 `ED83A106581E43275803D2E343F513D5BFC2B80A50E33584651816AE88A71E38` — independent script reported PASS |
| Historical paired audit JSON | SHA-256 `52C9197D1E827E0367A15871AA6F4500456B8126D34144CEB12A29BA7F081141` — independent script reported PASS |
| Historical OOF report | SHA-256 `E6F4C9AEB01ED3C8469181A36CE97BA22328BA2E09845BA909077B390FDC0E6D` — recorded in locked audit, not separately hashed by this run |
| PTB-XL metadata | Historical audit records SHA-256 `7600DE9C1B27D181D850B3C6038A35D7C3DDB6BB33B702E3A20252A6859D216B`. The independent script computed and stored the metadata digest in its local output but **did not compare that value to this expected hash**; verify it separately before claiming the metadata identity check PASS |
| Scope | Folds 1–8, ECG metadata join via `ecg_id`, fixed historical model thresholds; no waveforms opened, independent Fold 10 **NO_GO** |

The full-OOF CSV contains `ecg_id,strat_fold,y_true,baseline_probability,candidate_probability`, **not** `patient_id`. The independent script performed an explicit ECG-to-patient metadata join, checked unique IDs, checked all 17,418 development ECGs were represented, required patient-fold consistency, and used paired baseline/candidate decisions with fixed thresholds.

## Reproduced sample structure

| Statistic | Result |
|---|---:|
| Development ECG records | 17,418 |
| Unique development patients | 15,023 |
| Patients with ≥1 positive-class ECG | 3,708 |
| Patients with ≥1 negative-class ECG | 11,630 |
| Patients contributing to both classes | 315 |
| Positive-only patients | 3,393 |
| Negative-only patients | 11,315 |

## Fixed-threshold patient-weighted point estimates

Thresholds: baseline `0.3090648316207752`; candidate `0.3795860831201651`.

| Estimate | Independent recomputation |
|---|---:|
| Baseline sensitivity | 0.363140507011866 |
| Candidate sensitivity | 0.385475098885293 |
| Baseline specificity | 0.900030504033084 |
| Candidate specificity | 0.900081890021701 |
| Sensitivity difference (candidate − baseline) | 0.022334591873427 |
| Specificity difference (candidate − baseline) | 0.000051385988617 |

The independent script compared all six reference metrics / class-denominators against the historical audit with tolerance `1e-10` and reported `FIXED THRESHOLD METRICS VS LOCKED AUDIT: PASS`.

## Exploratory paired whole-patient bootstrap

Parameters: `seed=20261117`, `replicates=2000`, percentile 95% CI, fixed development-selected thresholds. Each bootstrap draw sampled from all **15,023 unique patients** with replacement; each mixed-label patient retained its positive- and negative-class contributions in the same draw. Baseline and candidate used the identical patient sample per replication.

| Candidate-minus-baseline 95% CI | Historical locked audit | Independent implementation |
|---|---|---|
| Sensitivity | [0.013366212093866812, 0.030920907523036483] | [0.013581438865823029, 0.0311456581380925] |
| Specificity | [-0.0030192824966140857, 0.0029435464603612344] | [-0.002846676805841064, 0.002993201486548817] |

Sensitivity interval endpoint maximum absolute difference: `0.000224750615056` (about **0.0225 percentage points**). Specificity interval endpoint maximum absolute difference: `0.000172605690773` (about **0.0173 percentage points**).

**Interpretation:** Interval estimates are close, but **not identical**. Differences may result from bootstrap random-number stream, patient ordering, sample construction or aggregation implementation; without the historical generator and precisely pinned execution environment, the cause is **not established**. Do not promote this test to an exact interval reproduction PASS and do not claim a formal equivalence test was performed.

## Remaining evidence requirements before closing FND-02 completely

1. Independently compare the local PTB-XL metadata SHA-256 against `7600DE9C1B27D181D850B3C6038A35D7C3DDB6BB33B702E3A20252A6859D216B`.
2. Preserve the independent verifier source with source SHA-256, version, Python/platform information, deterministic input schema and regression tests; add a non-sensitive synthetic fixture to CI.
3. Preserve a manifest containing SHA-256 digests for the actual local OOF CSV, metadata, historical audit JSON and generated aggregate-only report, while avoiding upload of patient-level records.
4. Locate and independently inspect the original historical generator if exact bootstrap interval reproduction remains a release claim; otherwise explicitly label the exact CI as *historical, not independently reproduced*.
5. A separate statistical reviewer should assess the conditional fixed-threshold CI, OOF model-selection bias, multiplicity and external validity.

## Safety/interpretation

Development-fold OOF metrics are **not** independent holdout performance estimates. Thresholds were optimized on this same OOF dataset. A fixed-threshold bootstrap interval does not correct for threshold selection/model selection, nor justify clinical use. This work does **not** imply clinical validation, CE/MDR conformity, manufacturer release authorization, or Fold 10 access.

**Release gate: FOLD 10 NO_GO.**
