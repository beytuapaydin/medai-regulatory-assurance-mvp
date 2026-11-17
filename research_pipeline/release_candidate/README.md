# MedAI Assurance — Research MVP v1.0 (Release Candidate 1)

> **RESEARCH ONLY · NOT FOR CLINICAL DECISIONS · HOLDOUT NO-GO**

This repository-ready **documentation and evidence-verification package** describes the research prototype developed under **MEDAI-PTBXL-MI-001**. It does **not** contain raw PTB-XL records, trained model weights, patient-level OOF predictions, or an authorized Fold 10 runner. Do **not** present it as a complete deployed application or independently clinically validated medical device.

**Scope:** Medical-AI assurance workflow with deterministic evidence integrity checks, patient-aware evaluation, model training reproducibility, frozen development protocol, and explicit holdout governance. This release candidate documents verified *development* evidence, and links to local artifacts using SHA-256.

## Research snapshot (17 November 2026)

| Item | Research status |
| --- | --- |
| Dataset | PTB-XL v1.0.3, 100 Hz records100 |
| Development | Folds 1–8: 17,418 ECGs, 15,023 patients |
| Label | PTB-XL MI diagnostic superclass, 14 SCP diagnostic codes |
| Features | 72 handcrafted signal features (12 leads × 6) |
| Candidate | L2-regularized logistic regression, L2=0.1, 200 epochs, LR=0.25 |
| Threshold | 0.3795860831201651; selected on development OOF |
| OOF patient-weighted sensitivity | 0.38547509888529646 |
| OOF patient-weighted specificity | 0.9000818900217537 |
| Candidate minus baseline OOF sensitivity | +0.022334592 (95% fixed-threshold paired cluster bootstrap CI 0.01337–0.03092) |
| Final candidate replay | Reproduced with zero model/inference delta in the reported environment |
| Synthetic integration | Passed synthetic WFDB end-to-end checks; no independent second reader cross-check |
| Holdout | **NO_GO — independent review pending, Fold 10 not accessed** |

**Statistical limitation:** the same OOF development data was used to choose thresholds and report outcomes. The fixed-threshold confidence interval does not account for threshold-selection uncertainty. The observed ~38.55% sensitivity is inadequate to support a clinical safety claim. MI superclass identification is not acute MI diagnosis.

## Package contents

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — evidence and scoring pipeline
- [`docs/RESULTS.md`](docs/RESULTS.md) — development results and limitations
- [`docs/RISK_REGISTER.md`](docs/RISK_REGISTER.md) — risks, mitigations, outstanding work
- [`docs/REVIEW_AND_RELEASE_GATE.md`](docs/REVIEW_AND_RELEASE_GATE.md) — explicit NO-GO decision and independent review workflow
- [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) — local paths and artifact verification
- [`docs/evidence_registry.json`](docs/evidence_registry.json) — locally reported hash references, not bundled evidence
- [`tools/verify_release_evidence.py`](tools/verify_release_evidence.py) — read-only verification against user's existing Windows artifacts
- [`tests/test_release_evidence.py`](tests/test_release_evidence.py) — tests with synthetic temporary evidence files

## Quick start (Windows PowerShell)

```powershell
$docs = "$env:USERPROFILE\Documents"
python -m pytest -q "$docs\MedAI-Assurance-Research-MVP-v1.0-RC1\tests\test_release_evidence.py"
python "$docs\MedAI-Assurance-Research-MVP-v1.0-RC1\tools\verify_release_evidence.py" --docs "$docs" --output "$docs\MedAI-RC1-Evidence-Verification.json"
```

The verification writes a **new** report only if all registered files match. It never alters evidence, does not read WFDB, and refuses to overwrite an output file. **No holdout execution is included.**

To publish to GitHub, publish *this documentation package only*, and keep model JSON, original EKG files, detailed per-record predictions, and user-specific directories out of the repository. See `SECURITY.md` and `.gitignore`.

## Project status

`RELEASE_CANDIDATE_DOCUMENTATION_ONLY / HOLDOUT_NOT_AUTHORIZED / NOT_CLINICALLY_VALIDATED`
