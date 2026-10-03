# Merge status

## Done in this revision
- Native M2 Finding / TrustResult / decide (no broken shims)
- Pipeline calls M2 directly
- NovaBank cutover: supportbot / databot / coordinator agents, configs, keys, manifests, policies, tools
- reset_db registers NovaBank first
- Duplicate FastAPI routes removed
- conftest seeds schema + agents (self-seeding tests)
- Mode `off` = no checks, action executes (PRD)
- Light drift + peer registry wiring
- README + api.md updated
- Private keys generated locally; strip before public share if needed

## Still open
- Full launcher supervisor (M3) — stub only
- React dashboard (M4)
- docs/threat_model.md, docs/results.md polish
- Peer trust needs richer registry for D5 live demo
- Drift module is still a stub until M3 fills check_drift
