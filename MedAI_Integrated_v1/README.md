# MedAI Integrated v1 — Local Regulatory Evidence Review Pilot

This is **a working local pilot, not a production compliance engine**. It reads a folder of documents, extracts source passages, ranks candidate documents for the 13 extracted MDR Article 10(9)(a)–(m) clauses, and generates a single HTML dashboard, JSON evidence register, and CSV reviewer worklist.

## What changed vs the earlier CardioAhead dashboard

- **No manually authored `illustrative_links` are used in matching.** The application retrieves candidates from the document *contents*.
- Each displayed passage is an **exact character span** from an input document, with a file SHA-256, passage SHA-256 and character offset.
- The requirement record preserves its original extracted text and source hash.
- Review status is always `PENDING`; evidence sufficiency and legal applicability remain `NOT_ASSESSED`.
- A missing match is a *retrieval outcome* only, **not** a finding that the manufacturer lacks compliance evidence.
- `DOCX`, `PDF`, `TXT`, `MD` local files can be used; PDF needs `pypdf` and DOCX needs `python-docx` installed in your virtual environment. Scanned documents without an extractable text layer are not supported.

## Windows PowerShell (from your current MedAI project root)

1. Extract `MedAI_Integrated_v1.zip` into the current project folder.
2. Run: `.\.venv\Scripts\python.exe .\MedAI_Integrated_v1\run.py`
3. Open: `Start-Process .\MedAI_Integrated_v1\output\dashboard.html`
4. Tests: `.\.venv\Scripts\python.exe -m unittest discover -s .\MedAI_Integrated_v1\tests -v`

## Your own local files

Create a folder with TXT, MD, PDF or DOCX documents. **Use public or de-identified files for demonstrations; don't put patient or confidential data in this pilot.** For example, if a folder `my_test_documents` exists in the project root:

`.\.venv\Scripts\python.exe .\MedAI_Integrated_v1\run.py --documents .\my_test_documents --output .\MedAI_Integrated_v1\my_output`

Open `my_output\dashboard.html` and `my_output\review_queue.csv` afterwards. The script does not modify source documents or the existing MedAI code/ChromaDB; it writes only to its chosen output folder.

## Technical and regulatory limitations

- The seven included CardioAhead documents are **synthetic one-paragraph excerpts**, not authentic controlled QMS documents. Example product classification (IIb) is a hypothesis, not a determination.
- The included MDR excerpt was extracted from a PDF identified as the 2026-07-19 consolidation, with SHA-256 `a8cca6f45159c678e2562ad5ad9140f4d1caad9b074ed97d78bc2b2347f912d0`. Automatic extraction has outstanding warnings (PDF page header contamination, soft hyphens in (b)/(j), duplicate word in (e)). A reviewer must verify these against the authoritative text.
- Candidate retrieval uses **transparent lexical/concept heuristic**, not a semantic entailment model and not a verified MDR gap assessment. `retrieval_score` is not a probability/confidence score and is not calibrated. The short concept hints are keyword aids, not assertions of regulatory equivalence.
- A retrieved excerpt does not establish that a requirement is met; approval, execution records, applicability, completeness and effectiveness need separate domain expert review.
- Inputs are limited to up to 250 files of at most 5 MB each, read from a single folder (not recursive). Some PDF/DOCX layouts, tables and complex formatting may not extract faithfully.
- In any subsequent use with actual company documents, implement authentication/access control, document revision management, confidential-data governance, redaction, audit log, validated source update process, expert review workflow, secure operations and real-world evaluation before deployment.

`RELEASE GATE: NOT_PRODUCTION`.
