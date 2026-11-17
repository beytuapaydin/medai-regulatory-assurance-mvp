# Verification status — 2026-11-16

- Unit and negative acceptance suite: **29 passed** (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`).
- Four synthetic example runs produced under `reports/pass`, `reports/fail`, `reports/insufficient`, and `reports/not_measured`.
- Confirmed statuses respectively: `PASS`, `FAIL`, `INSUFFICIENT_EVIDENCE`, `NOT_MEASURED`.
- This confirms software exercise behavior only. **No actual PTB-XL ECGs, trained-model predictions, customer datasets, model training/test provenance verification, QMS tool validation, human sign-off, or clinical validation has been performed.**
- Existing standalone v0.1 `clinical_eval_runner.py` and 15 original tests carried forward without alteration. `eval_engine.py` was not supplied, so repository integration was not performed.
- PTB-XL MI superclass is **not** a claim to detect acute MI or triage emergency cases. All acceptance margins and sample criteria are illustrative and have no clinical justification.
