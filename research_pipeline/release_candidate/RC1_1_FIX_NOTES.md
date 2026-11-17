# RC1.1 — Windows path-validation correction

This release corrects the cross-platform lexical path validation in `tools/verify_release_evidence.py`.

- Rejects Unix-rooted paths on Windows, Windows drive paths, UNC paths, traversal segments, and noncanonical path separators.
- Uses `PurePosixPath` for stable relative evidence-path semantics and preserves all fifteen locked evidence entries without changing their expected SHA-256 digests.
- Adds an expanded negative-path regression test and a nested-path regression test.
- Does not authorize Fold 10 access. No research evidence or model weights are modified.

Run: `python -m pytest -q tests/test_release_evidence.py`. The resulting evidence verification report must be written to a NEW filename.
