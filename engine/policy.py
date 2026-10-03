# engine/policy.py
# Owner: M2   (Phases 2 and 3, then calls the Phase 4-5 modules)
# Purpose: the "job description" check. Does this action fit the agent's contract?
# Plain Python, deterministic, NO LLM. Every Finding has a rule id and a plain-language reason.
#
# Interface for M1 (pipeline step 4):
#     check_policy(event, policy, history, **options) -> Finding    (the strongest result)
#     evaluate(event, policy, history, **options)     -> [Finding]  (all results, for the enforcer)
#
# `history` = this agent's recent events (last hour is enough), oldest or newest first, each with:
#     ts, tool, args, response ("allow"/"held"/"throttled"/"blocked"/"halted"), context
# We use the EVENT's own timestamp as "now", not the wall clock. That makes every test and every
# demo replay give the same answer. (The signature step already rejected stale timestamps.)
#
# Order of checks inside evaluate():
#   1 honeytoken   (cheap and critical, run it even if the tool is forbidden)
#   2 tool allow-list (default-deny)   -> if it fails we skip the rest (limits are meaningless)
#   3 argument limits (amount)
#   4 speed limits (per minute, per hour, sustained -> HALT)
#   5 can_talk_to  (who it may message)
#   6 sequence rules (deny_if)
#   7 dirty-data rule (taint.py)
#   8 leak filter  (leak_filter.py)
#   9 peer trust   (peer_trust.py, optional, needs a registry)
import yaml
from typing import List, Optional

from engine import honeytokens, leak_filter, peer_trust, taint
from engine._util import get, history_in_window, parse_ts, to_amount
from engine.findings import MESSAGE_TOOLS, Finding, worst
from engine.settings import M2Settings, get_settings

TAINT_TOKEN = "read_ticket_from_untrusted_source"   # handled by taint.py, skipped here


def load_policy(path: str) -> dict:
    """Read one YAML contract. safe_load only: a contract must never be able to run code."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if "agent" not in data:
        raise ValueError(f"{path}: contract has no 'agent' key")
    return data


# ---------- helpers ----------
def _recipient(args) -> Optional[str]:
    if not isinstance(args, dict):
        return None
    return args.get("to") or args.get("recipient")


def _is_outside_send(event, policy, s: M2Settings) -> bool:
    """Is this a message going outside the company? (used by the sequence token 'send_outside')"""
    if get(event, "tool") not in MESSAGE_TOOLS:
        return False
    args = get(event, "args") or {}
    allowed = tuple(s.allowed_email_domains) + tuple((policy or {}).get("allowed_email_domains") or ())
    rcpt = _recipient(args)
    if isinstance(rcpt, str) and "@" in rcpt:
        domain = rcpt.rsplit("@", 1)[-1]
        if not leak_filter._domain_allowed(domain, allowed):
            return True
    return bool(leak_filter.find_outside_emails(args, allowed))


def _count(history, now, window, tool=None, responses=None) -> int:
    n = 0
    for h, _ts in history_in_window(history, now, window):
        if tool is not None and get(h, "tool") != tool:
            continue
        if responses is not None and get(h, "response") not in responses:
            continue
        n += 1
    return n


# ---------- individual checks ----------
def _check_allow_list(tool, policy) -> Optional[Finding]:
    if tool not in (policy.get("allow_tools") or []):
        return Finding(
            "BLOCK", "allow_tools.tool_not_allowed",
            f"{policy.get('agent')} is not allowed to use '{tool}' (it is not in its contract).",
            "HIGH", penalty_key="tool_not_allowed", evidence={"tool": tool},
        )
    return None


def _check_amount(event, tool, policy, factor: float) -> Optional[Finding]:
    c = (policy.get("constraints") or {}).get(tool) or {}
    if "max_amount" not in c:
        return None
    raw = (get(event, "args") or {}).get("amount")
    amount = to_amount(raw)
    if amount is None or amount <= 0:
        return Finding(
            "BLOCK", f"constraints.{tool}.amount_invalid",
            f"{tool} needs a positive numeric amount, but got {raw!r}.",
            "HIGH", penalty_key="constraint_violated", evidence={"amount": repr(raw)},
        )
    limit = float(c["max_amount"]) * factor
    if amount > limit:
        return Finding(
            "BLOCK", f"constraints.{tool}.max_amount",
            f"{tool} amount {amount:g} exceeds limit {limit:g}.",
            "HIGH", penalty_key="constraint_violated",
            evidence={"amount": amount, "limit": limit, "amount_factor": factor},
        )
    return None


def _check_rates(event, tool, policy, history, now, s: M2Settings) -> List[Finding]:
    out: List[Finding] = []
    c = (policy.get("constraints") or {}).get(tool) or {}
    checks = []  # (rule, human text, used so far, limit)
    if "max_per_minute" in c:
        checks.append((f"rate.{tool}.max_per_minute", f"{tool} calls per minute",
                       _count(history, now, 60, tool=tool), float(c["max_per_minute"])))
    if "max_per_hour" in c:
        # per-hour caps count only actions that really ran (or are waiting for a human)
        checks.append((f"rate.{tool}.max_per_hour", f"{tool} calls per hour",
                       _count(history, now, 3600, tool=tool, responses=("allow", "held")), float(c["max_per_hour"])))
    if "max_per_minute" in policy:
        checks.append(("rate.agent.max_per_minute", "actions per minute (whole agent)",
                       _count(history, now, 60), float(policy["max_per_minute"])))
    for rule, text, used, limit in checks:
        if used + 1 > limit:                      # +1 = this action
            out.append(Finding(
                "THROTTLE", rule, f"Too many {text}: limit is {limit:g}.", "MEDIUM",
                penalty_key="rate_exceeded", evidence={"used": used + 1, "limit": limit}))
    if out:
        # "THROTTLE, then HALT if sustained": several recent throttled answers means a runaway loop
        recent = _count(history, now, 60, responses=("throttled",))
        if recent >= s.sustained_throttle_limit:
            out.append(Finding(
                "HALT", "rate.sustained_runaway",
                f"The agent kept going after being throttled ({recent} times in the last minute), so it was halted.",
                "CRITICAL", penalty_key="rate_exceeded", critical=True, evidence={"recent_throttled": recent}))
    return out


def _check_can_talk_to(event, tool, policy) -> Optional[Finding]:
    if tool not in MESSAGE_TOOLS:
        return None
    rcpt = _recipient(get(event, "args"))
    allowed = policy.get("can_talk_to") or []        # missing list = nobody (default-deny)
    if rcpt not in allowed:
        return Finding(
            "BLOCK", "can_talk_to.recipient_not_allowed",
            f"{policy.get('agent')} may not message {rcpt!r}. Allowed: {', '.join(allowed) or 'nobody'}.",
            "HIGH", penalty_key="constraint_violated", evidence={"recipient": str(rcpt)[:80], "allowed": list(allowed)},
        )
    return None


def _check_sequences(event, tool, policy, history, now, s: M2Settings) -> List[Finding]:
    out: List[Finding] = []
    seen = {get(h, "tool") for h, _ in history_in_window(history, now, s.sequence_window_seconds)}
    for rule in policy.get("deny_if") or []:
        after, then = rule.get("after"), rule.get("then")
        if not after or not then or after == TAINT_TOKEN:
            continue                                  # dirty-data rules live in taint.py
        then_hit = _is_outside_send(event, policy, s) if then == "send_outside" else tool == then
        if after in seen and then_hit:
            hold = rule.get("unless") == "human_approved"   # 'unless human approves' = HOLD instead of BLOCK
            out.append(Finding(
                "HOLD" if hold else "BLOCK", f"deny_if.{after}__{then}",
                f"Forbidden order: '{then}' after '{after}'. Each step alone looks fine, the sequence is the attack.",
                "HIGH", penalty_key=None if hold else "sequence_violation",
                evidence={"after": after, "then": then}))
    return out


# ---------- public API ----------
def evaluate(event, policy: dict, history=(), *, registry=None, amount_factor: float = 1.0,
             settings: Optional[M2Settings] = None) -> List[Finding]:
    """Run every check and return ALL findings (empty list = nothing wrong).
    amount_factor < 1.0 tightens max_amount limits (used during probation). Speed limits are NOT tightened,
    because that would push a recovering agent straight back into trouble."""
    s = settings or get_settings()
    tool = get(event, "tool")
    now = parse_ts(get(event, "ts"))
    findings: List[Finding] = []

    f = honeytokens.check_honeytokens(event, s)
    if f:
        findings.append(f)

    f = _check_allow_list(tool, policy)
    if f:
        findings.append(f)
        return findings

    for f in (_check_amount(event, tool, policy, amount_factor),):
        if f:
            findings.append(f)
    findings += _check_rates(event, tool, policy, history, now, s)
    f = _check_can_talk_to(event, tool, policy)
    if f:
        findings.append(f)
    findings += _check_sequences(event, tool, policy, history, now, s)
    f = taint.apply_taint_rules(event, policy, history, s)
    if f:
        findings.append(f)
    f = leak_filter.check_leak(event, policy, s)
    if f:
        findings.append(f)
    if registry is not None:
        f = peer_trust.check_peer(event, registry, s)
        if f:
            findings.append(f)
    return findings


def check_policy(event, policy: dict, history=(), **options) -> Finding:
    """The strongest single result (ALLOW finding if everything is fine).
    NOTE for the interface freeze: this returns a Finding (Decision-shaped), not a full Decision,
    because trust_before/after and status are only known later, inside enforcer.decide()."""
    return worst(evaluate(event, policy, history, **options))

def get_recent_history(agent_id: str, limit: int = 100):
    """History for pipeline step 4 (sequence/rate). Uses gateway DB when available."""
    try:
        from gateway.db import db
        return db.get_agent_history(agent_id, limit=limit) or []
    except Exception:
        return []
