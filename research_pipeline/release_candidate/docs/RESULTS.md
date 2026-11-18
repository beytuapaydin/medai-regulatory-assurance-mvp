# PTB-XL development evidence — frozen observations

These values were reported from runs on the user's Windows machine. The RC package itself does not contain the underlying private/local files; use `verify_release_evidence.py` for local SHA-256 matching.

## OOF (folds 1–8)

| Measure | Baseline | Candidate |
| --- | ---: | ---: |
| Patient-weighted sensitivity | 0.3631405070118699 | 0.38547509888529646 |
| Patient-weighted specificity | 0.9000305040331364 | 0.9000818900217537 |
| OOF-selected threshold | 0.3090648316207752 | 0.3795860831201651 |
| Positive-class patients | 3,708 | 3,708 |
| Negative-class patients | 11,630 | 11,630 |

- Total: **17,418 records, 15,023 unique patients**.
- 315 patients have both MI-positive and MI-negative records; these patients form **one cluster each** for paired bootstrap.
- Candidate − baseline patient-weighted sensitivity difference: **0.02233459187342656** (~+2.23 percentage points).
- Fixed-threshold paired patient-cluster bootstrap 95% percentile CI, 2,000 replicates: **[0.013366212093866812, 0.030920907523036483]**.
- **Reproduction boundary:** The original generator script and local input/output artifacts for the reported 2,000-replicate paired OOF bootstrap were not bundled in the frozen RC1.1 public source tree. The recorded result is not independently recomputable from the released source package alone. The included `clinical_benchmark_v0_2/src/clinical_validation/paired_estimands_v1.py` and research holdout-math modules are not evidence that the exact reported full-OOF analysis was independently rerun. Recover and verify the original generator and locked inputs before claiming exact numerical reproduction.
- Specificity difference CI: **[-0.0030192824966140857, 0.0029435464603612344]**.
- Independent fixed-threshold metric recomputation: `PASS_INDEPENDENT_FIXED_THRESHOLD_METRIC_RECOMPUTE`.
- Full OOF replay: baseline and candidate max absolute probability delta **0**.
- Frozen final candidate replay: max model parameter delta **0.0**, max inference delta **0.0**, classification disagreements **0**.
- Synthetic end-to-end integration: **30 simulated ECGs / 24 simulated patients**, verified tamper detection.

## What is NOT established

- These are development OOF scores, **not independent holdout estimates**.
- Threshold and model selected on the same development OOF set: bootstrap CI is conditional on selected thresholds; model-selection effects are not covered.
- Clinical acceptability is **not supported**. Sensitivity ~38.55% is low for any intended patient-safety use.
- No evaluation of performance on Fold 10 has been carried out; no diagnosis of acute MI is established.
- No manufacturer QMS release, CE/MDR approval, prospective validation, site external validation, or regulatory acceptance.

**Status:** `RESEARCH_DEVELOPMENT_ONLY / HOLDOUT_NO_GO`.
