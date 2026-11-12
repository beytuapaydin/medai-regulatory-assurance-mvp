# MedAI — Five-Minute English Demo

**Audience:** MedTech, HealthTech and AI assurance hiring managers / technical reviewers  
**Format:** Live localhost application or screen recording.  
**Goal:** Show a traceable *candidate evidence → reviewer assessment → gap report* workflow, not a compliance determination.

## 00:00–00:40 — The problem

**Screen:** Title / project folder, then open the Workbench at `http://127.0.0.1:8766/`.

**Say:**

“Medical device regulatory review is not just about finding a document. The challenge is connecting each requirement to the correct evidence, checking whether that evidence is actually sufficient, and documenting the review decision in a traceable way. I built MedAI as a local, human-in-the-loop demonstration of that workflow for a synthetic SaMD case called CardioAhead.”

## 00:40–01:25 — Requirement-to-evidence matching

**Screen:** Workbench overview; point to the total of **13** requirements, then to candidate document excerpts.

**Say:**

“The pilot covers thirteen extracted clauses of EU MDR Article 10(9) and seven synthetic CardioAhead documents. The integrated matching stage uses transparent, content-based heuristics to propose candidate passages. It preserves verbatim document excerpts and SHA-256 identifiers. The system does not claim that a match proves regulatory conformity. A requirement with no candidate is simply a retrieval result, not evidence of non-compliance.”

## 01:25–02:30 — A concrete CAPA case

**Screen:** Find `MDR-10-9-L` in the Workbench; show `CA-CAPA-007`.

**Say:**

“Let me show one completed example: Article 10(9)(l), which addresses corrective and preventive actions and verification of their effectiveness. The tool retrieves a draft CAPA workflow. It is relevant to the topic, but the passage explicitly says that effectiveness-verification records are not attached. In the synthetic pilot, the reviewer therefore recorded the evidence as *relevant but insufficient*. Importantly, this is a passage-level reviewer opinion, not a legal compliance finding.”

**Action:** Do **not** create another review event during the demo. Show the already recorded `Latest review` entry and rationale. The unrelated rationale on `MDR-10-9-A` is a known pilot-data defect; do not demonstrate it as an accurate decision.

## 02:30–03:40 — Assurance Gap Report

**Screen:** Open exact address `http://127.0.0.1:8766/gap-report`, locate `MDR-10-9-L`.

**Say:**

“The assessment now appears in the assurance report with the selected evidence, reviewer attribution, source excerpt, gap description and SHA-256 fingerprints. The requested next step is to obtain an approved CAPA procedure and documented effectiveness-verification records. Here the action is explicitly labeled `SYSTEM_TRIAGE_SUGGESTION_NOT_REVIEWED`, so the software does not silently turn a system recommendation into a human-approved corrective action.”

**Action:** Show `Finding (observed passage)`, `Evidence gap / review status`, `Required action / follow-up`, `Action attribution` and review timestamp.

## 03:40–04:25 — Integrity, boundaries and exports

**Screen:** Show `Review event SHA-256`, `Decision scope` and the CSV/JSON export links. Optionally display a saved terminal result `SOURCE: 13 requirements; AUDIT EVENTS: 2; INTEGRITY: OK`.

**Say:**

“The local review history uses append-only JSONL records and hash-chain checks, which help detect accidental changes. This is not equivalent to a secure digital signature. The report is available as HTML, CSV and JSON. The explicit decision scope is `EVIDENCE_TRIAGE_ONLY_NOT_LEGAL_COMPLIANCE`, and the demonstration is not production-ready.”

## 04:25–05:00 — Engineering choices and next steps

**Screen:** Show README/architecture diagram in GitHub.

**Say:**

“The value of this MVP is its conservative architecture: evidence remains inspectable, human judgments are separated from retrieval results, and uncertainty is visible. The tests cover matching invariants, report safety rules and selected integration paths. A real deployment would require verified regulatory sources, qualified reviewer validation, benchmarked retrieval performance, access controls and a quality-managed audit process. My next focus would be turning this pilot into a validated assurance workflow, not an autonomous compliance decision-maker.”

## Before recording: setup checklist

- Start the server and confirm `http://127.0.0.1:8766/` and `/gap-report` work. Use the **exact URLs** in the browser address bar (not PowerShell).
- Run `python .\MedAI_Integrated_v1\review_workflow.py check` and retain the result.
- Do not modify or regenerate `assessment.json` before capturing the demo; current audit events are bound to its hash.
- Zoom the browser to readable size; avoid showing local usernames, full Windows paths, private tabs or unrelated desktop content.
- Do not record `MDR-10-9-A` as an accurate finding: its stored rationale mistakenly references CAPA.
- Rehearse this script once; aim for five minutes and show **no** extra user actions that create a new audit event.

## One-sentence portfolio pitch

“MedAI is a local, human-in-the-loop SaMD regulatory evidence-triage prototype that connects MDR requirements to traceable source passages, reviewer opinions and conservatively attributed gap reports.”
