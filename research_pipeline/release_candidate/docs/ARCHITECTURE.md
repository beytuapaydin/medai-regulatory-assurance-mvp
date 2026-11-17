# Research architecture and provenance boundaries

```text
PTB-XL records100 (100 Hz; source SHA-256 verification)
    |
    v
WFDB-16 parsing / 12 leads × 1000 samples
    |
    v
72 engineered signal features (12 leads × 6)
    |
    +--> PTB-XL diagnostic_class=MI from scp_statements.csv
    |      (MI superclass label; NOT clinical acute MI diagnosis)
    v
Folds 1–8, patient-disjoint 8-fold out-of-fold development
    |
    +--> Baseline L2=1.0, candidate L2=0.1
    +--> patient-weighted sensitivity and specificity
    +--> threshold selection specificity >= 0.90, development only
    +--> 2000 paired patient-cluster bootstrap, fixed thresholds
    v
Frozen protocol + SHA-256 evidence registry
    |
    v
Final candidate trained on all Fold 1–8 (one fitted model)
    |
    v
Model replay / inference parity / synthetic WFDB integration
    |
    v
Go/No-Go: NO_GO until independent human review and approval
    X  Fold 10 execution not included or authorized
```

## Reproducibility and assurance design

- **Fail-closed:** reject missing files, unexpected source hashes, duplicate ECG IDs, invalid labels, patient-fold leakage, tampered synthetic WFDB.
- **Data split:** Fold 9 is previously inspected development data; Fold 10 is the intended locked holdout and was not read by the reported research workflow.
- **Scaling:** fit scaler exclusively on the training partition in each OOF fold; final scaler fit on all Fold 1–8 data.
- **Artifacts:** OOF CSV, statistical report, frozen protocol, final model, independent replay reports, plan and Go/No-Go outputs with SHA-256 integrity references.
- **Model limitations:** a handcrafted-feature logistic regression is a research benchmark, not clinical ECG decision support.
- **Interpretation:** Code and replay verification demonstrate deterministic repetition with the same implementation, not independently established correctness or transportability.
