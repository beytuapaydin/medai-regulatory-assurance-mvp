# MedAI Assurance — Protocol-to-Evidence Benchmark v0.2

**Research / engineering demonstration only.** Does not produce clinical approval, regulatory conformity, medical-device release authorization, validated results from PTB-XL, or evidence that the product meets MDR or ISO 13485. The included records and model predictions are **entirely synthetic**. This is a demonstrator for the *evidence workflow*, not a clinical effectiveness claim.

## Why this repo exists

Demonstrate a single claim-to-risk-control trace: `DEMO-CLM-ECG-01` → `DEMO-RC-SW-04` → locked demo policy → paired regression / subgroup checks → evidence JSON + HTML. Existing v0.1 `clinical_eval_runner.py` and its 15 tests are carried forward **unchanged**. The user's full `eval_engine.py` is **not present here**, and is not claimed to be integrated.

## Quick start (Windows PowerShell, at package root)

```powershell
python -m pip install pytest
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest -q
python -m src.clinical_validation.demo_runner --scenario pass --output reports/pass
python -m src.clinical_validation.demo_runner --scenario fail --output reports/fail
python -m src.clinical_validation.demo_runner --scenario insufficient --output reports/insufficient
python -m src.clinical_validation.demo_runner --scenario not_measured --output reports/not_measured
```

Every run emits `evidence_package.json` and `report.html` under the specified output directory. These files are local. Neither patient data nor model weights are sent anywhere by this example.

## Run with your own paired prediction rows

```powershell
python -m src.clinical_validation.demo_runner `
  --records-json path\to\paired_predictions.json `
  --train-manifest-json path\to\complete_training_ids.json `
  --output reports/my-run
```

Input JSON is a list of rows with keys: `ecg_id`, `patient_id` (string), `strat_fold` (=10), `age` (number), `subgroups` (`["ALL"]` plus `"AGE75_PLUS"` when age >=75), binary `y_true`, `y_pred_v1`, and `y_pred_v2`. One row per ECG, aligned across v1/v2 by ECG ID. The training manifest is a JSON list of all distinct training patient IDs used for **both** models. It must be complete and trustworthy to support the overlap check; this code does not establish that. A validation manifest, metadata lineage, data-use authority, source data labels and model artifacts require separate checks before any genuine PTB-XL study.

`USER_SUPPLIED_UNVERIFIED` remains the status for own data: merely supplying input files does not prove use of real PTB-XL models or establish validity. The illustrative protocol contains demonstration-only thresholds. Train/test contamination through hidden pretraining sources cannot be ruled out.

## Scope and hard limitations

- A `PASS` represents **only demo-policy satisfaction** on the supplied inputs. It is not clinical non-inferiority, safety, effectiveness, regulatory compliance, or a release decision.
- The gate checks point estimates and uses **exploratory paired patient-cluster percentile bootstrap confidence intervals**. Clinical-grade non-inferiority requires justified hypotheses and margins, appropriate one-/two-sided interval conventions, reference standard, power, multipletesting plan, and statistician review.
- If uncertainty prevents establishing the stated margin, the evidence is `INSUFFICIENT_EVIDENCE`, not a presumed success. A clear threshold `FAIL` is never hidden by another cohort's missing evidence.
- The age-based subgroup is derived and cross-checked from an input `age` field; input metadata are **not verified** by the software. There is no pacemaker cohort because its metadata definition is not established.
- There is no QMS tool validation, electronic signature, tamper-resistant audit trail, independent reviewer assessment, real clinical dataset ingestion, or completed PTB-XL model benchmark.
- SHA-256 verifies canonical JSON integrity, not trustworthiness, authentication, immutability or dataset ownership. The report has no patient identifiers or raw predictions, but handling source files still requires applicable security and data protection.

## Contents

- `src/clinical_validation/clinical_eval_runner.py` — original v0.1 core (untouched)
- `src/clinical_validation/protocol_loader.py` — rejects unsupported executable subgroup expressions and invalid policies
- `src/clinical_validation/paired_statistics.py` — illustrative paired patient-cluster bootstrap
- `src/clinical_validation/evidence_package_writer.py` — minimal evidence + HTML export; review remains pending
- `src/clinical_validation/demo_runner.py` — deterministic synthetic fixture CLI and optional user-supplied rows
- `protocols/ptbxl_mi_demo_protocol.json` — predeclared *demo-only* claim/risk/thresholds
- `tests/` — original 15 tests plus new protocol/evidence safety tests
- `WORKFLOW_BENCHMARK.md` — interview instrument and time/effort benchmark definition
- `QA_BLIND_REVIEW.md` — QA/RA review worksheet; not a signed result

## Connection to the existing project

Copy the new `src/clinical_validation/` files, `protocols/`, and new tests into the repository after reviewing existing namespaces. Do not overwrite an existing `eval_engine.py`. Run the entire repository test suite and separately inspect its import paths. No such integrated run has been performed here, because the complete repository has not been provided.
