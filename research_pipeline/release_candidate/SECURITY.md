# Research release security and data handling

- Do not commit PTB-XL waveform files (`*.dat`, `*.hea`), original patient metadata, per-record OOF predictions or trained model artifacts without review of data license and privacy conditions.
- Do not publish locally generated `*_Audit*.json`, evidence outputs containing personal Windows paths, credentials, `.env` files or API secrets.
- This ZIP includes only text documentation, a registry of **hash values**, a read-only verifier and synthetic tests; it contains no patient-level files or deployed clinical inference service.
- SHA-256 values are not secrets, but do not substitute for an attested timestamp or authorization.
- Report potential integrity issues without editing the frozen source evidence to make hashes pass.
