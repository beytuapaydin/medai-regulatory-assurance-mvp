# MedAI MVP v1.1 — Risk Management vs CAPA Case Study

## Objective
Demonstrate the distinction between document retrieval,
evidence relevance, evidence sufficiency, and regulatory conformity.

## Dataset
- Regulation: EU MDR Article 10(9)
- Requirements: 13
- Synthetic documents: 7
- Evaluation pairs: 91
- Provisional annotations: 15
- Unlabeled pairs: 76
- Expert-validated annotations: 0

## Case 1 — Risk Management

Requirement: MDR-10-9-E

Risk management as set out in Section 3 of Annex I.

Primary relevant document: CA-RM-004

The synthetic draft contains preliminary ECG hazard brainstorming.
Risk acceptability, residual risks, Annex I alignment and approval
remain open.

Provisional assessment:
- Relevance: DIRECTLY_RELEVANT
- Evidence polarity: PARTIAL
- Sufficiency: INSUFFICIENT

## Case 2 — Corrective and Preventive Actions

Requirement: MDR-10-9-L

Management of corrective and preventive actions and verification
of their effectiveness.

Primary relevant document: CA-CAPA-007

The synthetic draft outlines corrective action workflow stages.
No effectiveness verification records are attached.

Provisional assessment:
- Relevance: DIRECTLY_RELEVANT
- Evidence polarity: PARTIAL
- Sufficiency: INSUFFICIENT

## Evaluation Status

Retrieval performance: NOT_MEASURED

All 15 annotations are AI-assisted provisional judgments.
No requirement has a fully expert-validated document pool.

Recall@k, Precision@k and False Negative Rate must not be
presented as empirically validated performance results.

## Assurance Interpretation

A directly relevant document does not necessarily provide
sufficient evidence.

Insufficient documentary evidence is not automatically proof
of regulatory nonconformity.

Human review and evidence-based justification remain necessary.

## Limitations

- Entirely synthetic document corpus
- Limited regulatory coverage
- No independent expert validation
- No clinical validation
- No production deployment
- Regulatory source transcription requires verification

## Conclusion

The MedAI prototype demonstrates a controlled workflow for
identifying potentially relevant regulatory evidence while
preserving uncertainty and preventing unsupported compliance claims.

This case study illustrates the evaluation methodology,
not validated retrieval accuracy or MDR conformity.
