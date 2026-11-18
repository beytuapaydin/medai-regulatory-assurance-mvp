# RC1.2 post-audit engineering review (draft PR #11)

**Status:** post-audit hardening branch, **not** a new validated medical device release. The frozen `v1.0.0-rc.1` tag and its recorded local evidence remain unchanged.

## Verification evidence

The Ubuntu 24.04 / Python 3.12 GitHub Actions workflow completed successfully for commit `7f879b7de0554bcbd90ff963d4e9a2b263eedd15`, run `44271356834`. Five independent offline suites passed:

| Suite | Passed |
|---|---:|
| MedAI Integrated | 23 |
| Clinical Benchmark | 103 |
| MedAI Unified | 53 |
| Research Pipeline modules | 160 |
| Release Evidence | 12 |
| **Total** | **351** |

The observed clean CI run does not reproduce the numeric OOF research results, process original patient ECG waveforms, establish cross-platform mathematical equivalence, validate clinical efficacy, or authorize Fold 10. Subsequent documentation-only changes must receive their own CI confirmation before claiming a fully green final PR head.

## Independent audit disposition

| Finding | Classification / disposition | Evidence and remaining boundary |
|---|---|---|
| FND-01 duplicated holdout metrics | **MITIGATED** | Both frozen RC1.1 sources had an identical Git blob. Added an offline equality regression check preventing future byte-level divergence. Independent modules still have separate local imports; this is a maintenance constraint rather than proof of divergent behavior. |
| FND-02 OOF paired audit generator | **DISCLOSED, NOT REPRODUCED** | The original generator for the 2,000-replicate paired OOF difference and its local locked input artifacts are not in the public Git package. `RESULTS.md` now states this limitation. Neither an alternate statistics implementation nor a recorded JSON hash is evidence of exact independent reproduction. |
| FND-03 final model schema | **FIXED, TESTED** | Freeze/scoring path rejects missing and permuted `features_per_lead` and `lead_order`. Unused empty runner hash declaration removed. Model-performance numbers unchanged. |
| FND-04 current human-review views / CSV | **FIXED, TESTED** | Current assessment hash, requirement hash and candidate identity now scope visible review state; CSV formula prefixes are neutralized; stale forms are rejected. Historical hash-chained events are retained. |
| FND-05 localhost threat model | **NOT PRODUCTION-SECURE — DOCUMENTED** | The local demo is neither an authenticated multi-user application nor protected from a malicious local process; `127.0.0.1` binding and CSRF alone do not give such guarantees. Do not expose the port or enter sensitive material. Production authentication/authorization remains future work. |
| FND-06 bootstrap and mixed-label patients | **METHODOLOGICAL LIMITATION** | Holdout planning samples whole patients once across endpoints; optional `paired_estimands_v1.py` makes separate class-conditional endpoint resamples. These are different interval constructions and should not be interchanged or used to claim exact independent reproduction of the unbundled OOF paired audit. Degenerate small-sample whole-patient bootstrap currently fails closed rather than silently fabricating an interval. Re-design requires a predeclared statistical review, not a silent post-hoc algorithm change. |
| FND-07 ECG identity and age tags | **HARDENED, COMPATIBILITY EXCEPTION** | Evidence-writer exploratory estimates now require explicit ECG IDs and validate age/AGE75_PLUS consistency, including PTB-XL age 300 sentinel. The public, research-only legacy standalone function retains `require_ecg_id=False` by default for existing synthetic callers; supply `require_ecg_id=True` for strict source uniqueness. Standalone permissive mode must not be represented as provenance authentication. |
| FND-08 CI coverage | **FIXED, CI VERIFIED** | CI runs five suites including release verifier, using Ubuntu 24.04, Node 24-compatible checkout/setup-python and explicit Python import paths. |
| FND-09 threshold-selection optimism | **ACCEPTED / DISCLOSED** | Development thresholds were selected on the same OOF partition as the development performance estimate. The fixed-threshold bootstrap is conditional; neither this nor the confidence interval proves independent generalization. |
| FND-10 skipped source path | **FIXED, TESTED** | Final-model training-interface test locates committed sibling pilot source in a clean checkout and runs rather than skipping. |

## Release, safety and scope guardrails

- Clinical use, medical-device certification, regulatory conformity approvals and autonomous release authorization are **out of scope**.
- Fold 10 remains **NO_GO**; no authorized independent holdout execution or clinical performance estimate exists.
- Original research artifacts and the frozen RC1.1 source/hash record are **not rewritten** by this branch.
- All reported OOF metrics are **recorded local development outcomes**, not independently recomputed by this PR.
- Final merge or release requires reviewer approval; a green CI checks software tests, not clinical validity.

## Follow-up outside this scope

Exact OOF statistical reproduction requires the original generator source, frozen model predictions, manifest-linked raw/local artifacts, specified environment and an independent rerun. Any future change to the whole-patient bootstrap estimator, reviewer authentication, original-data use or holdout authorization requires its own predeclared review and separate evidence package.
