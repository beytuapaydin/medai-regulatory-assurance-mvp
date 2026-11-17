# Reproducibility and evidence verification

## Local evidence registry

`docs/evidence_registry.json` records **15** SHA-256 values previously reported by the Windows environment (not packaged in the RC). It includes full OOF, statistical audit, development protocol, final candidate model, replay, integration checks, and Go/No-Go manifest.

The CLI:

```powershell
python .\tools\verify_release_evidence.py --docs "$env:USERPROFILE\Documents" --output "$env:USERPROFILE\Documents\MedAI-RC1-Evidence-Verification.json"
```

- Opens only 15 explicitly named files.
- Compares each SHA-256 with the RC registry; mismatches fail closed.
- Verifies key expected states and threshold values from the locked protocol/model and the Go/No-Go decision when available.
- Does **not** recalculate model performance or inspect patient-level records; prior dedicated tools handled those checks.
- Does not read ECG source data or Fold 9/10 signals and labels.
- Does not authorize holdout.
- Creates an audit JSON using exclusive-create (no overwrite).

## Independent reproduction scope

The earlier OOF and final model replay used the *same* original modeling implementation and data. Exact matching implies determinism for that tested environment; it does not rule out a shared bug or confirm independent clinical generalization.

## Windows source workspace

The model and evidence live in several `Documents/MedAI-*` directories. The RC1 ZIP is not a replacement for them, and includes neither raw PTB-XL records nor model weights. Keep existing folders unchanged and refer to `README_TR.md` for safe extraction and verification.
