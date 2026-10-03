# M2 cheat sheet: rule IDs, penalties, thresholds

Every Decision has a non-empty `rule` (id) and `reason` (plain sentence). Tests and the dashboard match on these ids.

| Rule ID | Fires when | Verdict | Penalty |
|---|---|---|---|
| `honeytoken.touched` | bait record/key touched | BLOCK (CRITICAL) | 70, one step |
| `allow_tools.tool_not_allowed` | tool not in contract | BLOCK | 40 |
| `constraints.<tool>.max_amount` | amount above limit (500 for refunds, x0.5 on probation) | BLOCK | 25 |
| `constraints.<tool>.amount_invalid` | amount missing, not a number, <= 0, NaN/inf | BLOCK | 25 |
| `rate.<tool>.max_per_minute` / `rate.<tool>.max_per_hour` / `rate.agent.max_per_minute` | speed limit passed | THROTTLE | 15 |
| `rate.sustained_runaway` | 3 throttled answers in the last minute | HALT (CRITICAL) | 15 |
| `can_talk_to.recipient_not_allowed` | recipient not in `can_talk_to` (or missing) | BLOCK | 25 |
| `deny_if.<after>__<then>` | forbidden order, e.g. `read_customer_record__send_outside` | BLOCK, or HOLD if `unless: human_approved` | 40 (BLOCK only) |
| `taint.<tool>.untrusted_over_limit` | risky action after untrusted input, over `untrusted_max_amount` | HOLD | none |
| `leak_filter.card_number` / `.secret_key` / `.outside_email` | outgoing message has a leak | BLOCK | 25 |
| `peer_trust.sender_untrusted` | sender QUARANTINED/HALTED or trust < 30 | BLOCK | 25 |
| `peer_trust.recipient_quarantined` | message to a quarantined peer | BLOCK | none |
| `attestation.config_mismatch` (from M3) | config hash differs from manifest | QUARANTINE (CRITICAL) | critical override |
| `drift.anomaly` (M3, W2) | weird-but-allowed behaviour | FLAG or HOLD only | 10 |
| `status.quarantined` / `status.halted` | agent already QUARANTINED / HALTED | BLOCK / HALT | none |
| `status.flagged` / `status.throttled_requires_approval` | clean action from a FLAGGED / THROTTLED agent | FLAG / HOLD | none |
| `trust.fell_below_quarantine` | this penalty pushed score under 20 | QUARANTINE | n/a |
| `mode.off` | guard is OFF | ALLOW | none |
| `enforcer.internal_error` | anything crashed inside the enforcer (fail closed) | BLOCK | none |
| `allow.clean` | nothing matched | ALLOW | none |

## Trust ladder
70-100 HEALTHY | 40-70 FLAGGED | 20-40 THROTTLED | below 20 QUARANTINED | HALTED manual/critical only.
Going down: instant. Going up: +5 extra points (hysteresis). QUARANTINED/HALTED: only an admin can release.
Recovery: +1 per whole clean minute. Resume/restore: starts at 50 on probation, refund limits x0.5, N=20 clean actions to finish, then 80.

## Same-action-twice rule
If one action breaks two rules with the same penalty key (e.g. two `constraint_violated`), the penalty is applied once.
