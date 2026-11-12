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
