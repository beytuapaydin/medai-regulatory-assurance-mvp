# MedAI Evaluation Annotation Protocol v0.1

## Purpose
Define reproducible annotation rules for synthetic MDR
requirement-document pairs.

## Dataset
- 13 MDR Article 10(9) requirements
- 7 synthetic CardioAhead documents
- 91 requirement-document pairs

## Relevance
- IRRELEVANT
- TOPICALLY_RELATED
- DIRECTLY_RELEVANT

## Evidence Polarity
- SUPPORTS
- PARTIAL
- CONTRADICTS
- INSUFFICIENT_CONTEXT

## Sufficiency
- SUFFICIENT
- PARTIAL
- INSUFFICIENT
- NOT_ASSESSABLE

## Annotation Status
- UNLABELED: No assessment performed.
- PROVISIONAL: Draft assessment, not independently validated.
- EXPERT_VALIDATED: Independently reviewed by a qualified human expert.

## Governance Rules
1. Review the original requirement and source document.
2. Do not derive ground-truth labels from retrieval scores.
3. Do not automatically classify unreviewed documents as irrelevant.
4. Record annotator identity and evidence-based rationale.
5. Preserve provisional and expert-validated status separately.
6. Do not equate evidence relevance with MDR compliance.
7. Do not calculate performance metrics on incomplete or unvalidated requirement pools.
8. Do not alter retrieval rankings by removing unlabeled candidates.
9. Report NOT_MEASURED when validation coverage is insufficient.
10. Synthetic benchmark results do not constitute regulatory validation.

## Current State
- Total pairs: 91
- Provisional annotations: 1
- Unlabeled: 90
- Expert validated: 0

Status: ANNOTATION_PROTOCOL_DRAFT
