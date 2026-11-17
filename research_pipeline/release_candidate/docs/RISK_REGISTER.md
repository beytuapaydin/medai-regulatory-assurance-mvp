# Risk register — open at RC1

| ID | Risk | Impact | Current mitigation / next action | Status |
| --- | --- | --- | --- | --- |
| R01 | Development OOF used for threshold selection and point-performance evaluation | Optimistic estimates | Disclose conditioning; evaluate independently only after approved gate | OPEN |
| R02 | OOF sensitivity near 38.55% | High false-negative burden if used clinically | Research-only intended use, no clinical deployment or automated decision | OPEN / CLINICAL NO_GO |
| R03 | Only one WFDB-16 reader used for feature extraction and synthetic integration | Shared implementation defect could escape tests | Independent second-reader comparison and code review | OPEN |
| R04 | Fold 9 was previously inspected | Fold 9 cannot be called an independent holdout | Treat Fold 9 as development; Fold 10 remains unopened | CONTROLLED |
| R05 | No independently approved statistical analysis plan | Analysis bias / incomplete prespecification | Independent reviewer signs review record | OPEN |
| R06 | No reviewed real Fold 10 evaluator or authorization | Unreviewed access may invalidate evaluation | Explicit NO_GO; separate gated executor and approval | OPEN |
| R07 | Local SHA-256 anchors provide integrity but not trusted timestamp or attestation | Provenance spoofing/collusion | Optional external signed release/timestamp and source control tags | OPEN |
| R08 | Patient contributes positive and negative ECGs | CI distortion if sampled independently | Whole-patient cluster bootstrap; both estimands retained | CONTROLLED |
| R09 | Subgroup sample sizes may be inadequate | Unreliable subgroup conclusions | 30 positive + 30 negative patient minimum per subgroup; insufficient otherwise | OPEN |
| R10 | Full source code not yet consolidated into a public reproducible repository | Documentation-only package not a complete application | Perform source license, secrets, dependency, and E2E install review before GitHub release | OPEN |

Release decision: **NO_GO for holdout and NO_GO for clinical use**. A documentation-only Research RC may be published with these disclosures.
