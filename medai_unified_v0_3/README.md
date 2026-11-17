# MedAI Assurance — Unified Evidence Bridge v0.3

**Research prototype — not a clinical validation, not an MDR compliance determination, and not a manufacturer release approval.**

This is an **add-on**, not a replacement for your existing project. The original `MedAI_Integrated_v1/eval_engine.py`, `gap_report.py`, `review_workflow.py`, `run.py`, and `clinical_benchmark_v0_2` files remain unmodified.

## What the existing engines really do

- `eval_engine.py`: **retrieval quality evaluation** using fully expert-validated annotations. Its `NOT_MEASURED` is a retrieval-benchmark outcome, not proof of regulatory compliance or non-compliance.
- `run.py` + `gap_report.py` + `review_workflow.py`: MDR Article 10(9) **document candidate triage and human opinion recording**, with a local SHA-256-chained append log. A human `REVIEWER_CONSIDERS_SUFFICIENT` opinion is explicitly **not** a conformity finding.
- Clinical v0.2 engine: **research/demonstration** model v1/v2 checks, optionally paired patient-cluster bootstrap. Existing demonstration uses **synthetic model predictions**.

The v0.3 integration preserves both scopes in the same deterministic evidence snapshot. The original documentary engine does **not** contain validated Clinical Claim / Risk Control mappings to the clinical demonstrator. Therefore the new `cross_domain_traceability.state` is **`NOT_ESTABLISHED`**, not a fabricated link.

## One-folder installation (Windows PowerShell)

The ZIP contains exactly one new top-level folder: `medai_unified_v0_3`.

```powershell
cd "$env:USERPROFILE\Documents\MedAI-GitHub"
if (Test-Path '.\medai_unified_v0_3') { throw 'Folder exists: inspect it before installing' }
Expand-Archive -Path "$env:USERPROFILE\Downloads\medai-unified-evidence-v0.3-addon.zip" -DestinationPath '.'
```

The repository should have these **sibling folders**:

```
MedAI-GitHub/
├── MedAI_Integrated_v1/        # already in your repo
├── clinical_benchmark_v0_2/   # 29 previously passing clinical tests
└── medai_unified_v0_3/        # this add-on
```

## 1) Run the new integration tests

From the repository root:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest -q .\medai_unified_v0_3\tests
```

Run the older suites independently from their own folders, as before. **Do not** interpret independent unit tests as validation of a clinical model or a QMS tool.

## 2) Run a fully synthetic integration demo

All commands below run from `MedAI-GitHub` unless `cd` appears.

```powershell
cd .\clinical_benchmark_v0_2
python -m src.clinical_validation.demo_runner --scenario fail --output reports/fail
cd ..

python -m medai_unified_v0_3.make_fixture --output .\unified_demo_inputs

python -m medai_unified_v0_3.cli build `
  --assessment .\unified_demo_inputs\regulatory_assessment_SYNTHETIC.json `
  --clinical .\clinical_benchmark_v0_2\reports\fail\evidence_package.json `
  --output .\unified_demo_outputs\unified_evidence_SYNTHETIC_FAIL.json

python -m medai_unified_v0_3.cli verify `
  --package .\unified_demo_outputs\unified_evidence_SYNTHETIC_FAIL.json
```

Expected: `CLINICAL_GATE: FAIL`, `REGULATORY_CONFORMITY: NOT_ASSESSED`, `cross_domain_traceability.state: NOT_ESTABLISHED`.

This uses **two synthetic, unrelated datasets** and must never be presented as a real clinical-regulatory end-to-end case study.

## 3) Build from the actual local documentary assessment

If you have previously run `MedAI_Integrated_v1/run.py` and there is a real local source file, you can replace the synthetic assessment input with:

`--assessment .\MedAI_Integrated_v1\output\assessment.json`

If your regulatory reviewer has saved review events, also add:

`--reg-events .\MedAI_Integrated_v1\output\human_review\review_events.jsonl`

The existing review events are **verified and projected** (not modified or re-authored). Events from older source assessments are counted as stale and excluded from current-status summaries.

Optionally, to include the separate retrieval-quality benchmark, supply `--retrieval-eval path\to\eval_report.json`.

## 4) Separate human review on the unified snapshot

```powershell
python -m medai_unified_v0_3.cli review `
  --package .\unified_demo_outputs\unified_evidence_SYNTHETIC_FAIL.json `
  --review-log .\unified_demo_outputs\human_review_events.jsonl `
  --reviewer "DEMO_REVIEWER" `
  --disposition "FOLLOW_UP_REQUIRED" `
  --rationale "This is a synthetic demonstration; additional genuine model evidence is needed."

python -m medai_unified_v0_3.cli verify `
  --package .\unified_demo_outputs\unified_evidence_SYNTHETIC_FAIL.json `
  --review-log .\unified_demo_outputs\human_review_events.jsonl
```

A reviewer event records an **opinion about a fixed evidence snapshot**, not a technical override. `FAIL` stays `FAIL`; manufacturer release decisions remain outside the tool. Local reviewer IDs are **not authenticated electronic signatures**.

## Known limitations and next gate

- SHA-256 supports **integrity checks**, not immutability, identity authentication, or reliable legal timestamps.
- Current unified snapshots do **not** contain a clinically reviewed cross-domain Claim → Regulatory Requirement mapping; it remains `NOT_ESTABLISHED`.
- This add-on checks that imported source hashes match and rejects altered, mismatched or unrecognized clinical packages; it does **not** verify underlying ground truth or the real-world integrity of model predictions.
- Bootstrap/acceptance thresholds in clinical v0.2 are illustrative and have not been prospectively clinically qualified.
- Build is deterministic given fixed input bytes. The human review event log is stored separately, so a record's addition does not silently rewrite the original evidence package.
- The tool runs locally and does not upload patient data. **Do not include actual patient data in synthetic demo inputs or test logs.**
- In this session the user-uploaded core review ZIP had six source/test files but **not** the original `data/` and `docs_demo/` resources. We verified the independently runnable original `eval_engine` unit tests and newly added integration tests in a reconstruction; your existing full repo tests must be run on your Windows machine.
- Next scientific step: authentic held-out PTB-XL model predictions, predeclared statistical plan, expert review, and QA/RA usability testing. None are supplied or validated here.
