# Research governance: independent Go/No-Go

## Current machine-readable state

- Technical evidence precheck: `PASS`
- Independent statistical/clinical methodology review: `PENDING`
- Independent actual holdout reader/executor code review: `PENDING`
- Separate one-time Fold 10 access approval: `NOT_AUTHORIZED`
- Current decision: **NO_GO**

Source: `MedAI-Holdout-GoNoGo-Decision-v1/go_nogo_decision.json`, with locally reported manifest SHA-256 `75398F2834A0952FC5B063F17660CC2BF05409FB990E18AD0AEF3CAB979A225C`.

## External reviewer checklist (must not be self-completed by scripts)

1. Validate actual labels against PTB-XL SCP MI superclass and preserve all 14 codes; inspect dataset license and intended use.
2. Independently review patient-weighted estimands, mixed-label patients, OOF threshold selection, fixed-threshold bootstrap, low-sensitivity risk, and age=300 sentinel handling.
3. Review real signal reader versus an independent implementation, model preprocessing, schema checks, artifact hash locks, inadvertent label/signal access paths and data leakage checks.
4. Sign a review record with reviewer identity, date, scope, findings, amendments, residual risks, and outcome (approve/reject/conditional).
5. Separately record authorization for **one** locked Fold 10 research run, including exact code/model/protocol hashes, fixed threshold, abort rules, and immutable results retention.

No review signatures or authorization are present in this package. The `NO_GO` state is intentional, not a failed technical test. If Fold 10 is eventually evaluated, unfavorable outcomes must be retained and never used for iterative retuning while still described as independent holdout.

## Release variants

- **RC1 documentation:** can be published now, clearly labeled *documentation-only, research, holdout no-go*.
- **Research MVP v1.0 Final:** requires actual source packaging and external review; if holdout validation is part of the release claim, it additionally requires one approved evaluation with transparently reported results.
- **Clinical product:** out of scope; requires distinct intended use, substantial clinical evidence, quality-system processes and applicable regulatory compliance.
