# Member 3 — Identity, Audit & Analytics

## Owns
- `engine/attestation.py` — signature, nonce, timestamp, config hash
- `engine/drift.py` — [W2] `check_drift(event, history) -> Finding | None`
- `engine/sandbox.py` — [S] offline dataset replay
- `audit/chain.py`, `audit/verify.py` — hash chain
- `gateway/launcher.py` — config-hash supervise / kill
- tests: `test_attestation`, `test_chain`, `test_drift`, `test_sandbox`

## Pipeline hook
Step 5 already calls `drift.check_drift` (see `gateway/pipeline.py`).
