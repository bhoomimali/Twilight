# M2 Code Guide: what we built, why, and how it fits

Written for Ace (Member 2, Policy & Trust Lead). Plain English on purpose.
All of this is tested: run `python -m pytest -q` (96 tests) and `python scripts/m2_sim.py` (prints a demo-style report).

---------------------------------------------------------------------
## 0. The big picture (what are we doing?)

TWILIGHT is a checkpoint. Every action an agent wants to do goes through the gateway first. The gateway runs 12 steps.
**Your part is the "brain" of the middle steps**: it answers three questions about each action.

1. **Is this action allowed?** (policy.py, taint.py, leak_filter.py, honeytokens.py, peer_trust.py)
2. **So what do we do about it?** (enforcer.py: allow / flag / hold / throttle / block / quarantine / halt)
3. **How much do we trust this agent now?** (trust.py: the score and the ladder)

And one extra: **tell a human** (incidents.py).

The flow inside your code, for one action:

```
event ---> policy.evaluate()  ---> [Finding, Finding, ...]   (what looked wrong, each with a rule id + reason)
                                        |
                                        v
                          enforcer.decide(findings, mode, status)  ---> ONE Decision
                                        |  (uses trust.py to change the score)
                                        v
                          incidents.create(decision)  ---> ticket for finance / security / developer / reviewer
```

Why plain code and no AI? Because of the golden rule: *the AI can raise alarms, but never switch them off.*
If an LLM judged actions, an attacker could just talk to that LLM. Our rules are `if` statements, so there is nobody to sweet-talk.

---------------------------------------------------------------------
## 1. Files, in the order we built them

### Phase 1: Contract (settings, findings, contracts)

**`engine/settings.py`**: every number in one place (thresholds, penalties, windows).
- Why: the PRD says nothing is hard-coded. Reads the same names as `.env.example`, with PRD defaults, so our tests run without waiting for M1's `config.py`.
- New .env names you added (M1 must copy them into `.env.example`, already done in the zip): `TRUST_HYSTERESIS`, `PENALTY_HONEYTOKEN`, `TRUST_RESUME`, `TRUST_PROBATION_EXIT`, `PROBATION_LIMIT_FACTOR`, `SEQUENCE_WINDOW_SECONDS`, `TAINT_WINDOW_SECONDS`, `SUSTAINED_THROTTLE_LIMIT`, `PEER_MIN_TRUST`, `ALLOWED_EMAIL_DOMAINS`, `HONEYTOKEN_IDS`.

**`engine/findings.py`**: the `Finding` object + the allowed values (verdicts, severities, modes).
- A Finding = "I saw X, I suggest verdict Y, here is the rule id and the reason".
- Why not return a full Decision from policy? A Decision needs `trust_before/after` and `status`, which policy doesn't know yet. So policy returns Findings and `enforcer.decide()` builds the one real Decision.
- Unknown verdicts/severities raise an error (decision rule: never invent synonyms).
- Verdict strength order: ALLOW < FLAG < THROTTLE < HOLD < BLOCK < QUARANTINE < HALT. When several checks fire, the strongest wins.

**`policies/*.yaml`**: the three job descriptions. SupportBot follows the PRD. DataBot and Coordinator values are marked PROPOSED.
- `allow_tools` is default-deny: anything not listed is blocked.
- `unless: human_approved` means "HOLD" (a human approves), not "BLOCK".

### Phase 2: first blocking demo (policy.py: allow-list + argument limits)

- **Tool allow-list**: tool not in contract -> BLOCK, rule `allow_tools.tool_not_allowed`, penalty 40.
- **Amount limit**: `issue_refund amount 9000 exceeds limit 500` (same sentence as the PRD example), rule `constraints.issue_refund.max_amount`, penalty 25.
- **Bad amounts are blocked, not ignored**: `None`, text like "abc", 0, negatives, `True`, and especially **NaN / infinity**. In Python `NaN > 500` is False, so a naive check would let NaN sail through. We reject any amount that isn't a real finite positive number. The amount "9000" as text is understood (LLMs do that).
- Why we use the event's own timestamp as "now": tests and demo replays then give identical answers every time.

### Phase 3: Control (rates, recipients, sequences, trust, enforcer)

**Speed limits (policy.py)**
- Agent-wide `max_per_minute`, per-tool `max_per_minute`, per-tool `max_per_hour`.
- Over the limit -> THROTTLE, penalty 15 (`rate_exceeded`).
- "Sustained" -> HALT: if the agent keeps going after being throttled `SUSTAINED_THROTTLE_LIMIT` (3) times in a minute, it's a runaway loop -> HALT. This is the PRD's D4: "THROTTLE, then HALT if sustained".
- The per-hour cap counts only refunds that really ran (or are held), so blocked attempts don't unfairly count.
- We made the per-hour cap a THROTTLE (rate) instead of BLOCK (constraint) so that a burst of refunds ALSO tells the "throttle then halt" story, whichever tool M4's spike script uses.

**can_talk_to**: a message to anyone not in the list is BLOCKED. A missing recipient is blocked too (default-deny), because we can't verify it.

**Sequence rules (`deny_if`)**: "read customer data, THEN send outside" is blocked. Each step alone looks fine; the order is the attack. Uses a time window (`SEQUENCE_WINDOW_SECONDS`, 10 min).

**`engine/trust.py`: the score**
- 70-100 HEALTHY, 40-70 FLAGGED, 20-40 THROTTLED, below 20 QUARANTINED, HALTED manual.
- Penalties: 40 / 40 / 25 / 15 / 10 as in the PRD.
- **Hysteresis**: going down is instant, going back up needs +5 extra points. Why: an agent sitting at 69-71 would otherwise flip HEALTHY<->FLAGGED every few seconds and the dashboard would flicker.
- **QUARANTINED and HALTED are sticky**: no amount of waiting releases them. Only an admin restore/resume does. Why: a quarantined agent can't act, so it can't "earn" trust back; and for a compromised agent, waiting is not proof of being fixed.
- **Critical override**: config mismatch -> QUARANTINE immediately, whatever the score.
- Pure functions (no database), so they're easy to unit test and M1 stores the results.

**`engine/enforcer.py`: the one place that decides**
1. Checks agent status FIRST (cheapest check). Quarantined -> BLOCK, halted -> HALT.
2. Takes the strongest finding.
3. The status ladder makes clean actions stricter when the agent is already in trouble: FLAGGED -> verdict FLAG (watched), THROTTLED -> risky tools need HOLD.
4. Applies each different penalty once per action (no double punishing for one mistake).
5. If the penalty pushes the agent below 20, the verdict is upgraded to QUARANTINE.
6. **Modes**: `off` = no checks. `dry-run` = we compute everything and say "DRY-RUN: would BLOCK", but return ALLOW and change no trust. `on` = full.
7. **Fail closed**: any crash or unknown value inside the enforcer returns BLOCK with `rule=enforcer.internal_error`.
- Why dry-run returns ALLOW: so M1's code can never accidentally block in dry-run. The real answer is kept in `evidence.would_verdict` and still creates an incident, so the OFF/dry-run/ON demo (FR11) works.

### Phase 4-5: the differentiators

**`taint.py`: dirty-data tracking (differentiator #1)**
- Anything from outside (a customer ticket) is untrusted. After reading one, risky actions get stricter limits.
- PRD example works: after an untrusted ticket, a **400 refund is HELD, a 50 refund is allowed** (limit `untrusted_max_amount: 100`).
- Two ways an action counts as tainted: the event says `input_taint: untrusted` (a missing/weird value counts as untrusted), OR the agent read from an untrusted tool (default `read_ticket`) in the last 15 minutes. We don't rely only on the flag because an agent could lie or forget.
- HOLD gives **no penalty**: the agent may just have been tricked, so a human decides.
- An agent **cannot** approve itself: we ignore any `human_approved` field in the event. HOLD itself is the approval step.

**`leak_filter.py`: stop data leaving**
- Card numbers (digits + Luhn check), outside emails, secret keys (sk-, AKIA, ghp_, private-key headers, long high-entropy tokens).
- Only scans **outbound** tools (messaging, or tools with `scan:` in the contract). Scanning every argument of every tool would cause false alarms (e.g. a 13-digit order number that passes Luhn by luck).
- **Privacy**: the leaked value is never put in evidence. Cards are masked (last 4), emails keep only the domain, secrets keep a 4-char prefix + length. Otherwise the proof log would itself contain the leak (PRD coding rule 4).
- Look-alike domain `evilnovabank.test` is NOT treated as ours (we match the domain exactly or as a real subdomain).

**`honeytokens.py`: bait (differentiator #2)**
- Fake records/keys no real task needs, listed in `HONEYTOKEN_IDS`. Touching one -> BLOCK, CRITICAL, penalty 70 in one step (100 -> 30).
- Matches case-insensitively, inside sentences, and in nested args.
- It runs FIRST, even if the tool is forbidden, so a critical event is never hidden behind an ordinary block.
- Why it's great: no fuzzy thinking. Nothing legitimate touches bait, so near-zero false alarms.

**`incidents.py`**: every non-ALLOW decision (and every dry-run "would block") becomes a ticket with severity, evidence and an owner:
- refund rules -> finance; honeytoken / leak / attestation / sequence / forbidden tool / peers -> security; speed / drift / internal error -> developer; HOLDs -> reviewer.

### Phase 6: recovery + probation (D8) in trust.py
- Restore/resume does NOT give 100. It starts at 50 (FLAGGED), on **probation**.
- On probation: refund limits are halved (500 -> 250), score can't pass 69 by waiting.
- After N clean actions (default 20, open item #7) probation ends and trust is lifted to 80 (HEALTHY).
- Speed limits are NOT tightened on probation. We tried it: a recovering agent made normal-speed calls, got throttled, and fell straight back into quarantine. That would make the recovery demo fail.
- Clean-time recovery: +1 per whole clean minute (the caller keeps the leftover seconds).

### Phase 7: peer_trust.py [W2], D5
- Peers refuse messages from a QUARANTINED/HALTED sender or a sender with trust below 30, and nobody can message a quarantined peer.
- `blast_radius()` lists everyone an agent talked to, so the dashboard can put them on watch.

### Phase 9: tuning tools
- `scripts/m2_sim.py` runs the whole chain with a fake clock. It is also the **reference wiring for M1** (copy the order of calls from `SimGateway.submit`).
- It prints false-alarm rate on clean traffic, how D2/D3/D4/D8/D9 behave, and M2's own decision time.
- Current numbers (from the sim, your part only): **0% false alarms over 300 clean actions; median 0.03 ms, worst ~0.1 ms per decision.** These are simulator numbers on a laptop, not the full gateway. Only quote them as "M2's rule engine", never as the whole gateway overhead.

---------------------------------------------------------------------
## 2. Things you MUST tell your teammates (interface changes)

1. **To M1:** `check_policy` / `evaluate` return **Finding** objects (Decision-shaped), not a full Decision. The full Decision comes from `enforcer.decide()`. Update `docs/api.md` section 21.8 accordingly.
2. **To M1:** run the tool only when `decision.response == "allow"`. (Dry-run returns ALLOW with `evidence.would_verdict`.)
3. **To M1:** history entries need these fields: `ts, agent_id, tool, args, response, context`. Pass only the last hour for this agent (index on agent_id + ts) to keep it fast. `response` values: allow / held / throttled / blocked / halted.
4. **To M1:** store probation state per agent (e.g. `probation_required`, `probation_clean` columns in `agents`), and call `trust.record_clean_action` after each clean executed action while probation is active. Call `trust.recover_clean_agent` with whole minutes.
5. **To M1 + M4:** agree the honeytoken ids. We used `cust_honey_001`, `cust_honey_002` and a bait key. Mock customer data must contain them, and **no normal scenario may ever read them**.
6. **To M3:** when `verify_config_hash` fails, call `findings.from_config_mismatch(expected, actual)` and add it to the results. That is the critical override.
7. **To M4:** `read_ticket` events are untrusted sources by default. In your clean scenarios keep refunds at or below 100 after tickets, or tell me and we raise `untrusted_max_amount`. For D4, either tool works: a burst of refunds or ticket reads both lead to THROTTLE then HALT.
8. **To everyone:** new rule ids use the format in `docs/m2_rule_ids.md`.

---------------------------------------------------------------------
## 3. Honest limits of the M2 layer (say them if asked)

- Rules only see the action, not the AI's intent. An allowed action with bad content (an approved address getting a bad message) can slip past. Sequence rules, taint and HOLD reduce this; they don't remove it.
- Taint is per agent and time-based, not per message. It can HOLD a refund that had nothing to do with the ticket. We chose "too careful" over "too loose"; tune the window if it annoys the demo.
- Luhn can still flag a random long number once in ~10. We only scan outbound tools to keep this rare. We measured 0% false alarms on our simulated clean traffic, but that traffic is ours. Re-measure with M4's `scenarios.py`.
- Regex leak checks miss obfuscation ("4 1 1 1 ..." in words, base64). We say so.
- Penalty numbers, windows and the 100-refund untrusted limit are sensible starting points, not scientific. Open item #7 is yours: after M4's first clean run, pick N and thresholds, and write the final numbers into `.env.example`.
- Hash/signature checks are M3's job; we only react to their result.
