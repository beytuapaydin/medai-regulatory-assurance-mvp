# MedAI Regulatory Intelligence & Assurance — MVP v1.0

**Release classification:** Synthetic Demonstration / Portfolio MVP. **NOT PRODUCTION**. No MDR conformity decision, product certification, clinical validation, or independent regulatory assurance is provided.

## What is included

- `run.py`: local, heuristic, content-based matching of seven synthetic CardioAhead text documents to 13 extracted MDR Article 10(9)(a–m) requirements; generated source passages are traceable to input files.
- `review_workflow.py`: local Human Review Workbench; human reviewer can record relevance, sufficiency opinion, rationale, and follow-up. Uses append-only JSONL events with a SHA-256 hash chain (tamper-evident for accidental changes, **not** a digital signature).
- `gap_report.py`: reviewer-grounded Assurance Gap Report, including Finding, Evidence Gap, Required Action and action attribution. Export to CSV/JSON.
- `data/`, `docs_demo/`: synthetic pilot inputs and the extracted MDR clause inventory.
- `output/assessment.json`, `output/human_review/review_events.jsonl`: fixed pilot snapshot and **two original reviewer events**, preserved without alteration.
- `tests/test_integrated.py`: eight tests for document inventory and extraction/matching invariants.

## Run on Windows

Open PowerShell in the folder **containing `MedAI_Integrated_v1`** and use a Python 3.12 environment. These commands assume your existing project virtual environment is at `.venv`:

```powershell
.\.venv\Scripts\python.exe .\MedAI_Integrated_v1\review_workflow.py check
.\.venv\Scripts\python.exe -m unittest discover -s .\MedAI_Integrated_v1\tests -p "test_*.py" -v
.\.venv\Scripts\python.exe .\MedAI_Integrated_v1\review_workflow.py serve --port 8766
```

While the last command remains running, enter `http://127.0.0.1:8766/` or `http://127.0.0.1:8766/gap-report` directly in the **browser address bar**. Stop with Ctrl+C. Use the *exact URL*, without query parameters. `/gap-report?utm_source=...` can return 404 although `/gap-report` succeeds.

Optional: Rebuild assessment output using `run.py`, but **do not overwrite this snapshot before preserving it**: saved review events are bound to the SHA-256 of the assessment file. An updated assessment may make prior events stale and exclude them from the current report.

## Release acceptance evidence

- Report upgrade test suite: **7/7 passed** in user's Windows environment (from the separate Assurance Report v1.1 patch, not bundled here).
- `MedAI_Integrated_v1/tests`: **8/8 passed** in user's Windows environment.
- `review_workflow.py check`: **13 requirements; 2 audit events; INTEGRITY: OK** in user's Windows environment.
- Manual synthetic CAPA use case (MDR-10-9-L): candidate `CA-CAPA-007`, reviewer opinion `RELEVANT / INSUFFICIENT`, report shows source passage, SHA-256, reviewer timestamp, gap and unreviewed system follow-up suggestion.
- **Not demonstrated:** clean-room Windows installation, complete functional regression of all browser workflows, regulatory/legal accuracy, real-world model evaluation, security assessment, cross-platform compatibility.

## Known limitations and data quality findings

1. **Incorrect pilot audit event #1:** `MDR-10-9-A` / `CA-QMS-001` contains a CAPA-related reviewer rationale (and an unintended copied UI word `Kopyala`). It is a synthetic, invalidly contextualized review. Do **not** cite this event as a valid regulatory strategy assessment. It is retained unchanged so the append-only event hash chain remains verifiable. For demonstrations, treat this record as a documented data-quality exception; do not silently delete or edit it. Any replacement review must be an additional logged event and explicitly justified.
2. **CAPA event #2:** The reviewer entered `INSUFFICIENT`, but no separate `gap_or_follow_up` text. The report proposes a CAPA follow-up with `SYSTEM_TRIAGE_SUGGESTION_NOT_REVIEWED`; this is **not** an approved corrective action.
3. **MDR extraction fidelity:** extracted wording contains soft-hyphen/page and duplicated-word artifacts (e.g., `in in`). Authoritative MDR text has not been independently verified and must not be treated as certified source text.
4. **Matching:** transparent lexical/concept retrieval; no demonstrated semantic entailment, recall validation on real documents, or coverage of all required QMS evidence. Lack of a match does not establish non-compliance.
5. **Operations:** localhost demonstration, no user authentication, role-based access, change-control system, secure e-signature, validated audit log, confidential-data safeguards, real clinical data support, or production hardening.
6. **Dependencies:** the bundle is source + synthetic data, not a standalone executable or full Python environment. Optional PDF/DOCX ingestion requires additional packages (see `README.md`).
7. **Historical documentation:** `README.md` and `REVIEW_WORKFLOW_README.md` describe earlier phases and may reference port 8765. **This file is the release-specific entry point.**

## Delivery policy

Use only public, synthetic or anonymized test data. Never represent automated retrieval, reviewer opinion, or system-suggested actions as CE conformity, legal compliance, or a qualified medical regulatory sign-off. For a production release, validation, security, source verification, qualified review and quality management processes are mandatory.
