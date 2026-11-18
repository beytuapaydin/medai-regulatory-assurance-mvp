# MedAI Human Review Workbench — CardioAhead pilot

This patch **adds only** `review_workflow.py` and this README into the existing `MedAI_Integrated_v1` folder. It leaves the existing MedAI CLI, source assessment, model, source PDF, and ChromaDB unchanged.

From the MedAI project root run:

```powershell
.\.venv\Scripts\python.exe .\MedAI_Integrated_v1\review_workflow.py check
.\.venv\Scripts\python.exe .\MedAI_Integrated_v1\review_workflow.py serve
```

Open `http://127.0.0.1:8765` in a browser. Keep the PowerShell window open while using the UI. Use Ctrl+C to stop. If `assessment.json` is missing, run `MedAI_Integrated_v1/run.py` first.

For each of 13 MDR Article 10(9) clauses, a human reviewer can mark candidate relevance, evidence sufficiency assessment, rationale and next action. Review records are **append-only** in `MedAI_Integrated_v1/output/human_review/review_events.jsonl`. A SHA-256 hash chain detects accidental alteration, but **does not provide cryptographic authentication, non-repudiation or protection against a malicious file editor**. The initial data is wholly synthetic. Never enter credentials or sensitive patient data.

Export CSV through the browser or via:

```powershell
.\.venv\Scripts\python.exe .\MedAI_Integrated_v1\review_workflow.py export
```

**Reviewer label `REVIEWER_CONSIDERS_SUFFICIENT` is solely a reviewer opinion about an evidence passage**, not MDR compliance or release approval. No regulatory legal decision is made. No label is provided or presumed by the software. Do not represent this demonstration as validated or production-ready.

## RC1.2 security boundary (post-audit)

The reviewer UI is a **single-user, localhost-only research demonstration**, not an authenticated multi-user review service. Binding to `127.0.0.1` and requiring a per-process CSRF form token do **not** authenticate other local applications or processes. The landing page exposes the CSRF token to any local process that can read the HTTP response; the origin guard also permits absent `Origin` headers. Do not run this server on a shared/untrusted computer, tunnel or expose port 8765, or store protected clinical or regulated evidence in it.

CSV exports neutralize spreadsheet-formula-looking cells; the append-only hash chain detects accidental modification but does not provide trusted provenance, non-repudiation, or a malicious-local-process security guarantee. Production use requires explicit authentication/authorization, an approved threat model and security assessment, data access controls, and independently verified review-event provenance.

Assessment-scoped filtering in RC1.2 ensures that historical events remain in the log but are not counted as current reviews when their source assessment, requirement hash or selected candidate no longer matches.
