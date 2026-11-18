# AUD-05 — Research API subgroup contract boundaries

**Status:** contract clarification and synthetic regression tests. **Research only. Fold 10 NO_GO.**

## Two intentionally different entry points

| API | Intended scope | Required data | Meaning of `PASS` |
| --- | --- | --- | --- |
| `evaluate_model_regression` | Generic synthetic/offline regression engine; supports legacy tags, including `F_65_PLUS` | `ALL` plus policy-declared tags; valid age required when `age` is supplied, `AGE75_PLUS` tagged, or AGE75_PLUS required | Only declared generic engine demo policy passed on supplied rows |
| `build_evidence_package` | PTB-XL protocol-bound **research-format** EvidencePackage | Valid age on every row; exact age-derived tags: `ALL`, and `AGE75_PLUS` when age policy indicates membership. No other subgroup tags. | Only supplied research-format demo criteria passed; **not** real validation or release approval |

**No cross-profile promotion:** a generic evaluation report `gate_status=PASS` is not a PTB-XL EvidencePackage `overall_gate_status=PASS`. These statuses are context-specific, and there is no validated conversion or sign-off mechanism between them. All downstream consumers must use the protocol-bound EvidencePackage itself if claiming its demo gate status.

## Regression evidence

`clinical_benchmark_v0_2/tests/test_aud05_subgroup_contract.py` exercises three fully fabricated cases:

1. Legacy `F_65_PLUS` with missing age: generic demo API **PASS**, PTB-XL package **INSUFFICIENT_EVIDENCE**.
2. Legacy `F_65_PLUS` with valid age but prohibited extra tag: generic demo API **PASS**, PTB-XL package **INSUFFICIENT_EVIDENCE**.
3. Correct `ALL` + `AGE75_PLUS` with age 80: both synthetic demo paths **PASS**, no clinical use or real PTB-XL validation implied.

Existing age-300 sentinel, invalid-age and subgroup integrity tests remain in `test_age300_regression.py` and `test_protocol_to_evidence.py`.

## Residual limitations

- This clarifies and tests existing behavior; it does **not** unify the schemas or replace legacy callers.
- No standalone runtime enforcement prevents an unrelated application from misinterpreting a generic `PASS`. Consumer integration must be reviewed and the trust boundary preserved.
- Synthetic fixtures may use `strat_fold=10` solely to exercise a policy expecting fold 10; **no actual fold-10 patient, label, prediction, signal or dataset is read**.
- Does not establish external validation, clinical non-inferiority, CE/MDR compliance, or manufacturer/QMS release.

**Reviewer disposition remains pending; do not merge without independent review.**
