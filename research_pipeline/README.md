# MedAI Assurance
### From AI predictions to verifiable evidence.

**Research MVP v1.0 RC1.1 | Medical AI Safety · Validation · Evidence Engineering**

*Can a medical AI system demonstrate not only what it predicts, but also how its performance was measured, what evidence supports it, and when it must refuse to advance?*

That is the question behind **MedAI Assurance**.

This project develops an auditable, research-only assurance workflow around myocardial infarction (MI) classification using the PTB-XL ECG dataset.

The goal is not to create another medical AI accuracy leaderboard. It is to demonstrate how model development, evaluation methodology, reproducibility, evidence integrity, uncertainty, and human oversight can become explicit, testable components of an AI system.

**Current status: Development evidence frozen. Independent holdout evaluation not authorized. Clinical use prohibited.**

---

## 01 — The problem: A prediction is not sufficient evidence

A medical AI model can produce convincing predictions and report impressive performance metrics. But those numbers alone cannot establish whether the evaluation was appropriately designed or whether the results can be trusted.

A credible assurance process needs to answer questions such as:

- Were patients kept separate across development and evaluation partitions?
- Were repeated ECG records handled without unintentionally overrepresenting individual patients?
- Were model parameters and thresholds reproducible?
- Can the underlying source code and evaluation evidence be verified independently?
- What happens when a required artifact is missing or has changed?
- Who is authorized to advance a model toward independent evaluation or release?

**MedAI Assurance turns these questions into explicit engineering checks rather than relying on documentation alone.**

## 02 — What the system actually does

The research pipeline connects model development to a verifiable evidence and release-review workflow.

| Layer | Purpose | Assurance mechanism |
|---|---|---|
| Dataset and label preparation | Establish research inputs and MI label definitions | Documented mapping and dataset integrity checks |
| Patient-aware evaluation | Reduce patient-level weighting and partitioning errors | Patient-weighted out-of-fold assessment |
| Model comparison | Evaluate baseline and candidate methods | Fixed-threshold paired comparisons |
| Reproducibility | Verify the same computation can produce the same result | Independent training and prediction replay |
| Evidence integrity | Detect altered or inconsistent research artifacts | SHA-256 hashes and evidence registries |
| Synthetic integration | Exercise evaluation and processing workflows without independent holdout access | Synthetic data and tamper-detection tests |
| Release governance | Separate technical readiness from authorization | Fail-closed checks and explicit NO_GO decisions |

The guiding principle is simple:

**A technically functioning model is not automatically an authorized or clinically validated model.**

## 03 — Research dataset and evaluation design

This project uses the publicly available **PTB-XL ECG dataset**, version 1.0.3, for research.

The configured research task is binary myocardial infarction superclass classification, based on documented diagnostic label mapping.

The development protocol uses:

- **17,418 ECG records** from folds 1–8.
- **15,023 unique patients** represented in the development partition.
- Patient-weighted out-of-fold evaluation.
- Two candidate regularization configurations evaluated through logistic-regression-based research models.
- A fixed patient-weighted specificity development target of approximately 90%.

Fold 9 was previously inspected and is therefore not treated as a fully independent untouched evaluation set.

**Fold 10 remains outside the authorized evaluation scope.** No independent Fold 10 performance is reported.

The raw ECG data is not distributed in this repository.

## 04 — What the development results show

The completed development out-of-fold evaluation produced the following results:

| Metric | Baseline | Candidate |
|---|---:|---:|
| Selected decision threshold | 0.3091 | 0.3796 |
| Patient-weighted sensitivity | 36.31% | 38.55% |
| Patient-weighted specificity | 90.00% | 90.01% |

At the selected development thresholds, the candidate exhibited an approximately **+2.23 percentage-point difference in patient-weighted sensitivity** while maintaining the development specificity target.

An exploratory paired patient-cluster bootstrap with 2,000 replicates estimated a 95% interval of approximately **+1.34 to +3.09 percentage points** for the sensitivity difference at these fixed thresholds.

### What this result does not establish

These are **development results**, not independent holdout results.

The thresholds were selected using the same development evaluation data. Consequently, the reported performance and bootstrap interval do not eliminate threshold-selection optimism or establish independent generalization.

The candidate's sensitivity also remains insufficient to justify clinical deployment based on these results.

**The contribution of this project is the auditable evaluation process, not a claim that the classifier is ready for patient care.**

## 05 — Reproducibility: Can the evidence be regenerated?

A core objective is to distinguish an interesting result from a result that can be independently checked.

The research workflow includes:

**Full out-of-fold reproduction**

The development predictions were independently reproduced across the configured folds, with the recorded comparison reporting a maximum absolute prediction difference of zero under the verified execution conditions.

**Final candidate model reproduction**

The frozen candidate model was compared against an independent retraining and inference run, with matching recorded parameters and predictions under the evaluated conditions.

**Evidence freezing**

Research protocols, evidence manifests, verification reports, and model-related artifacts were connected through recorded cryptographic hashes.

These checks establish reproducibility within their documented environment and scope. They do not demonstrate universal reproducibility across all operating systems, numerical libraries, or hardware.

## 06 — Evidence integrity: Detect changes instead of assuming trust

The pipeline uses SHA-256 verification to detect unexpected changes in locked evidence and source artifacts.

When a required locked artifact fails verification, the relevant operation must not silently proceed.

A particularly important engineering issue was discovered during release preparation:

1. The original Python source matched its locked SHA-256 value.
2. A Git archive contained CRLF line endings instead of LF.
3. The archive copy consequently failed its locked source verification.
4. The discrepancy was traced to Git line-ending conversion.
5. The source line-ending policy was standardized.
6. A clean Git archive was regenerated and its integrity verified.

This is a concrete example of the system's assurance philosophy:

**A verification failure is actionable evidence, not an inconvenience to bypass.**

No locked hash needed to be weakened or replaced to obtain the verified result.

## 07 — Verification status

The consolidated research pipeline was tested from a separate Git archive snapshot.

| Verification | Recorded result |
|---|---|
| Research and release components | 11/11 successful pytest executions |
| Individual tests passed | 169 |
| Individual tests failed | 0 |
| Individual tests skipped | 1 |
| Source archive integrity | PASS |
| Synthetic integration tests | 12/12 PASS |
| Independent Fold 10 evaluation | NOT AUTHORIZED |

The skipped test belongs to the final-model package-build environment and is not counted as passed.

**These are software verification results, not measurements of clinical efficacy.**

The archive test reused the existing Python environment. A completely fresh-environment installation and dependency audit are not yet demonstrated.

## 08 — Repository structure

The research workflow is organized into distinct modules with independently executable tests.

```text
research_pipeline/
├── README.md
├── requirements-test.txt
├── .gitattributes
│
├── modules/
│   ├── MedAI-PTBXL-Real-Pilot-v1/
│   ├── MedAI-PTBXL-OOF-v2/
│   ├── MedAI-PTBXL-Full-OOF-v1/
│   ├── MedAI-Full-OOF-Repro-v2_1/
│   ├── MedAI-Final-Model-Freeze-v1/
│   ├── MedAI-Final-Model-Repro-Audit-v1/
│   ├── MedAI-Holdout-Readiness-v1/
│   ├── MedAI-Holdout-Plan-Executor-Validation-v1/
│   ├── MedAI-Holdout-Integration-Review-v1/
│   └── MedAI-Holdout-GoNoGo-v1/
│
└── release_candidate/
    ├── README.md
    ├── README_TR.md
    ├── SECURITY.md
    ├── docs/
    │   ├── ARCHITECTURE.md
    │   ├── RESULTS.md
    │   ├── REPRODUCIBILITY.md
    │   ├── RISK_REGISTER.md
    │   ├── REVIEW_AND_RELEASE_GATE.md
    │   └── evidence_registry.json
    ├── tools/
    │   └── verify_release_evidence.py
    └── tests/
        └── test_release_evidence.py
```

The `modules/` directory contains the implemented research components. The `release_candidate/` directory contains the release-oriented technical documentation and verification utilities.

## 09 — Getting started

### Step 1. Clone the repository

```powershell
git clone https://github.com/beytuapaydin/medai-regulatory-assurance-mvp.git
cd medai-regulatory-assurance-mvp
git switch release/research-mvp-v1
```

The release branch must first be published to GitHub for the final command to work.

### Step 2. Prepare Python

The consolidated tests were validated with Python 3.14.10 and pytest 9.2.0.

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r research_pipeline\requirements-test.txt
```

The test requirements file documents the observed test dependency. It is not yet a validated complete runtime dependency lockfile.

### Step 3. Run a research module's tests

For example, to verify the synthetic holdout integration workflow:

```powershell
cd research_pipeline\modules\MedAI-Holdout-Integration-Review-v1
..\..\..\.venv\Scripts\python.exe -m pytest -q -rs tests
```

The module tests should be run separately because some module directories contain tests with overlapping names.

### Step 4. Run release documentation tests

From the repository root:

```powershell
cd research_pipeline\release_candidate
..\..\.venv\Scripts\python.exe -m pytest -q -rs tests
```

### Step 5. Review the supporting evidence

Start with the release documentation:

- `release_candidate/docs/ARCHITECTURE.md`
- `release_candidate/docs/RESULTS.md`
- `release_candidate/docs/REPRODUCIBILITY.md`
- `release_candidate/docs/evidence_registry.json`
- `release_candidate/docs/REVIEW_AND_RELEASE_GATE.md`

The evidence registry describes locked artifacts. The registry's existence does not imply that every external evidence file is included with this Git repository.

### Step 6. Review limitations before running data-dependent workflows

Real ECG processing, model retraining, and certain evidence verification operations may require PTB-XL data and additional locally stored research artifacts.

These are not bundled with the source release. Consult the relevant module source and reproducibility documentation before running those workflows.

Do not access independent holdout labels or signals merely to demonstrate that a script works.

## 10 — Release gates and human oversight

The system distinguishes between technical prechecks and authorization.

A successful automated verification step may establish that expected files exist, hashes match, or synthetic tests pass. It cannot independently authorize clinical deployment, certify regulatory conformity, or replace accountable human judgment.

The current research gate remains:

**TECHNICAL_PRECHECK_PASS — INDEPENDENT_REVIEW_PENDING — NO_GO**

Independent Fold 10 evaluation is not authorized.

The release decision remains **NO_GO** until the required independent review and authorization conditions are satisfied.

## 11 — Intended use and limitations

This repository is intended for research, engineering demonstration, and discussion of Medical AI evaluation and assurance practices.

It is **not** intended to:

- Diagnose myocardial infarction or support patient-specific clinical decisions.
- Operate as a deployed medical device.
- Automatically approve medical AI under MDR or other regulatory frameworks.
- Replace clinical, quality, regulatory, or independent validation review.
- Claim independent holdout performance without an authorized evaluation.

The prototype demonstrates selected engineering controls. It is not a certified end-to-end medical device quality management system.

## 12 — Who this project is for

This repository may be useful to:

**ML engineers and researchers** who want examples of patient-aware evaluation, reproducibility checks, and evidence integrity.

**Medical device QA/RA professionals** interested in the technical evidence required to support model evaluation and review.

**AI Safety and Assurance engineers** exploring measurable controls, explicit failure states, and verifiable evidence chains.

**HealthTech product and engineering teams** investigating how model development evidence can be connected to release governance.

## 13 — Further development

Potential future work includes independently reviewed holdout execution, stronger environment reproducibility, evidence packaging automation, controlled change management, and broader assurance evaluation.

These are prospective activities, not capabilities claimed as complete in RC1.1.

## Final perspective

**A model prediction answers what the system believes.**

**An assurance system must also answer why that result should be trusted, what evidence exists, what remains uncertain, and who is accountable for the next decision.**

MedAI Assurance is an engineering exploration of that distinction.

---

*Research-only prototype. No clinical deployment authorization. No CE/MDR conformity claim. Independent Fold 10 evaluation remains NO_GO.*