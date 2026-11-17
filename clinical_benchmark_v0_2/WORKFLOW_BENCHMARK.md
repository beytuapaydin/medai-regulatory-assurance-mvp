# Workflow Benchmark — 15-minute customer discovery (unvalidated template)

**Purpose:** Determine whether the costly step is (A) ML metric calculation, (B) statistical/clinical evidence interpretation, or (C) transfer into QA/RA change control. Do not pitch solutions before recording actual past behavior.

Company (internal code): ____   Role: ____   Interview date: ____   Interviewer: ____

1. **Most recent change (2 min):** Tell me about the most recent change to model weights, threshold, preprocessing, input data, or intended-use scope. What triggered it? When did it happen? Was it deployed, deferred or rejected?
2. **Elapsed vs working time (3 min):** From "ML candidate ready" to completed QA/RA change assessment, how many calendar days and how many person-hours were spent? Who performed each step? If uncertain, mark **unknown**, not zero.
3. **Bottleneck (3 min):** Which stage caused the most rework: testing/metrics, determining evidence sufficiency, linking to clinical claims and risk controls, or preparing the final QMS file? Ask for concrete documents and examples, not just a preference.
4. **Existing stack (2 min):** Which tools or templates were used? Which fields were copied manually? How many QA/RA↔ML revision loops were needed? What evidence was requested again during review?
5. **Acceptance and purchasing (3 min):** What would a locally executed tool need to demonstrate before its output could be entered into your QMS? Who must validate the tool? Which security requirements apply? Who holds the budget and when is the next actual change project?
6. **Follow-up (2 min):** Could we observe your existing process on an approved non-sensitive example? Is a paid pilot with scope and budget possible? Who would decide? Record next action and date.

## Structured capture

| Field | Value | Evidence strength |
|---|---|---|
| Last change type / date | | stated / document-verified / unknown |
| Major + minor changes / year | | stated / verified / unknown |
| Calendar days ML-ready → QMS completion | | stated / measured / unknown |
| Active ML effort (hours) | | stated / measured / unknown |
| Active QA/RA effort (hours) | | stated / measured / unknown |
| Manual copy/paste steps | | stated / measured / unknown |
| QA↔ML rework cycles | | stated / measured / unknown |
| Evidence gaps raised in review | | stated / document-verified / unknown |
| Current tools/vendors | | stated / observed / unknown |
| QA tool validation needs | | stated / approved checklist / unknown |
| Economic buyer + actual budget | | confirmed / speculative / unknown |
| Agreed paid pilot next step | | signed / scheduled / absent |

## Controlled workflow experiment

Use the *same* locked model predictions, claim, risk-control reference, acceptance criteria and QA task for both arms:

- **Baseline:** customer's existing Python/MLflow + Excel/Word + QMS process.
- **Candidate:** MedAI research demo + approved handoff to existing QMS.
- Measure hands-on person-hours, calendar time, rework cycles, evidence omissions, reproducibility, reviewer correctness and number of mandatory QMS fields transferable without editing.
- Record participants' prior familiarity and order effects. Do not assume automated runtime = end-to-end process time. State study N and limitations; do not publish ROI claims from simulated or single-user results.
