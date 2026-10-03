# Security & Feasibility (M1+M2+M3)

## Critical fix applied
`/action` no longer short-circuits mode `off` with BLOCK. Pipeline owns modes:
- **off** — no checks, tool still runs
- **dry-run** — checks, no tool execute
- **on** — full enforcement

## Controls
Attestation, policy Findings, leak/taint/honeytoken, peer trust, drift FLAG, audit chain, fail-closed.

## Demo risks
- Private PEMs in tree — regenerate before public share
- Default `GATEWAY_API_KEY=change-me` — local bind only
- SQLite single-node — hackathon OK

## Feasibility
High for laptop demo; pure Python; no LLM in gate path.
