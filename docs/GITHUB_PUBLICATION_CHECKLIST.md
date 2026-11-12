# GitHub publishing checklist — MedAI MVP v1.0

## Recommended repository name

`medai-regulatory-assurance-mvp`

## Publish these

- The clean release folder `MedAI_Integrated_v1/`.
- Replace the repository-root `README.md` with `README_GITHUB.md` from this kit.
- Add `DEMO_SCRIPT_5_MIN_EN.md` under `docs/` (optional, but useful for recruiters).
- Preserve `MedAI_Integrated_v1/START_HERE_MVP_RELEASE.md` for accurate runtime instructions.
- Keep the synthetic sample files and the associated documented data-quality limitation visible.

## Do not publish

- `.venv/`, `.local/`, `__pycache__/`, Python `.pyc` files, local temporary backups, `.env` files, credentials, patient records, proprietary documents or unrelated project histories.
- Do not use local Windows screenshots showing personal data or full user-directory paths.

## Suggested .gitignore

```gitignore
.venv/
.local/
__pycache__/
*.py[cod]
.env
.env.*
!.env.example
*.log
.DS_Store
Thumbs.db
```

## Short GitHub description

Human-in-the-loop SaMD regulatory evidence triage: MDR Article 10(9), traceable document passages, reviewer decisions and assurance gap reporting. Synthetic demo; not a compliance engine.

## Tags / topics

`medical-device` · `samd` · `regulatory-affairs` · `eu-mdr` · `human-in-the-loop` · `evidence-traceability` · `ai-governance` · `quality-assurance`

## Example repository commands

Run only after arranging the folder and checking for sensitive data. From the folder you want to publish:

```powershell
git init
git add README.md MedAI_Integrated_v1 docs .gitignore
git status
git commit -m "Publish MedAI synthetic assurance MVP v1.0"
```

Create a new empty repository in GitHub first, then follow the **exact remote URL shown by GitHub**. Do not paste a placeholder as a real remote URL. Publishing is an intentional manual step; no remote repository has been created by this kit.

## Honesty checklist before posting

- No CE marking, MDR conformity determination, real clinical validation or production readiness is claimed.
- The integrated matcher is described as **heuristic**, not a validated AI language model.
- Source hashes are not presented as authentication or qualified e-signatures.
- Reviewer opinion and unreviewed system follow-up suggestion are distinguished.
- Mention the incorrect `MDR-10-9-A` pilot review rationale as an acknowledged data-quality exception.
- State separately which test sets were run (8 integrated tests; 7 upgrade tests external to clean release ZIP).
