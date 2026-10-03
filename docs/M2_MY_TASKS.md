# Member 2: Policy & Trust Lead ("The Rulebook")

**One line:** You write the job descriptions for the agents and the consequences when they break them. Your code is plain Python, so an AI can never talk its way past it.

## Your files
`engine/policy.py`, `taint.py`, `leak_filter.py`, `honeytokens.py`, `trust.py`, `enforcer.py`, `incidents.py`, `peer_trust.py` [W2], `policies/*.yaml`
Tests: `test_policy.py`, `test_trust.py`, `test_leak.py`, `test_honeytoken.py`
Docs: comments in `policies/`, response side of `docs/threat_model.md`

## Functions you hand to M1 (frozen in Phase 1)
- `policy.check_policy(event, policy, history) -> Decision`
- `enforcer.decide(results, mode, status) -> Decision`
- `trust.apply_penalty(score, reason, policy)`, `trust.recover_clean_agent()`
- `incidents.create(decision)`

## What you need from others
- M1: `ActionEvent` and `Decision` types in `schemas.py`
- M3: the config-hash mismatch signal (triggers your critical override in `trust.py`)
- M4: attack scripts D2, D4, D9 to tune against

## Tasks by phase
| Phase | Task |
|---|---|
| 1 | Draft the 3 YAML contracts + rule ID list (drafts are already in `policies/` and `docs/m2_rule_ids.md`). Agree penalties/thresholds for `.env.example` with M1 |
| 2 | `check_policy` for tool allow-list + argument limits (first blocking demo) |
| 3 | Rate limit, recipient, `can_talk_to`, sequence rules. `trust.py` with all 5 states. `enforcer.py` with ladder + modes. Unit tests |
| 4-5 | `taint.py`, `leak_filter.py`, `honeytokens.py`. Reason + rule on every decision. `incidents.py` |
| 6 | Tune rules against M4's D2, D4, D9. Recovery + probation logic |
| 7 | `peer_trust.py` for D5. Tune thresholds after the first clean-traffic run (with M3) |
| 9 | Final false-alarm tuning. Threat-model response column |

## "Done" means
- Repeated violations walk an agent HEALTHY -> FLAGGED -> THROTTLED -> QUARANTINED in order
- A 400 refund after an untrusted ticket is HELD, a 50 refund passes
- Every Decision has a non-empty `reason` and `rule`
- False-alarm rate on clean traffic is measured

## Watch out
- No LLM calls inside your modules. Every rule deterministic and explainable.
- Check agent status first in `enforcer.py`. Unknown verdict values must be rejected.
- Hysteresis: different thresholds going down vs up, or agents flip-flop at a boundary.

## Your demo moment
At 1:15-2:15 you explain the rule that fired (e.g. `constraints.issue_refund.max_amount`) while M1 drives the hacker console.

## Open item that's yours
#7: decide N (clean actions to leave probation) and final thresholds after the first clean-traffic run.

## Review ring
You review **M3's** code. **M1** reviews yours.

## Buffer help (Phase 6+)
Once you hit "Done", help M4 with YAML contract tests and pitch Q&A on rules.

## Status of the code in this zip
| Phase | Done in code | Where |
|---|---|---|
| 1 | contracts, rule ids, numbers | `policies/`, `docs/m2_rule_ids.md`, `engine/settings.py`, `.env.example` |
| 2 | allow-list + argument limits | `engine/policy.py` |
| 3 | rate, recipient, sequence rules, trust, enforcer, modes | `policy.py`, `trust.py`, `enforcer.py` |
| 4-5 | taint, leak filter, honeytokens, reasons, incidents | `taint.py`, `leak_filter.py`, `honeytokens.py`, `incidents.py` |
| 6 | recovery + probation, tuning against D2/D4/D9 | `trust.py`, `scripts/m2_sim.py`, `tests/test_m2_scenarios.py` |
| 7 | peer trust, blast radius | `peer_trust.py` |
| 9 | threat-model response side, false-alarm measurement | `docs/threat_model.md`, `scripts/m2_sim.py` |

Still needs OTHER people: M1 wires it into `pipeline.py` (copy `SimGateway.submit`), M3 sends the config-mismatch signal,
M4's real attack scripts and `scenarios.py` re-measure false alarms. Read `docs/M2_CODE_GUIDE.md` first.
