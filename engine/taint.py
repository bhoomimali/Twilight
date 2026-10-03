# engine/taint.py
# Owner: M2   (Phase 4-5)
# Purpose: "dirty data" tracking (differentiator #1).
# Anything that comes from OUTSIDE (a customer ticket, an email, a web page) is untrusted.
# If an agent has just read untrusted text, its risky actions get stricter limits or a HOLD.
#
# PRD example: after reading an untrusted ticket, a 400 refund is HELD and a 50 refund is allowed.
#
# HOW we decide an action is "tainted" (either is enough):
#   1. The event itself says context.input_taint == "untrusted" (D7: field exists from day one).
#      A missing or weird value is treated as untrusted (fail safe).
#   2. The agent read from an untrusted source tool recently (default: read_ticket) inside the
#      taint window. We do not rely only on (1) because the agent could lie about it, or an LLM
#      could forget to set it.
#
# Contract keys (inside constraints.<tool>):
#   untrusted_max_amount: 100       above this, a tainted action is HELD
#   untrusted_requires_approval: true   any tainted use of this tool is HELD
#
# "unless: human_approved" in the PRD YAML is implemented BY the HOLD itself: HOLD means a human
# approves, then M1 runs the action once. We do NOT read a "human_approved" flag from the event,
# because an agent could simply set it to true.
from typing import Optional

from engine._util import get, history_in_window, parse_ts, to_amount
from engine.findings import Finding
from engine.settings import M2Settings, get_settings

DEFAULT_UNTRUSTED_SOURCES = ("read_ticket",)


def effective_taint(event, policy: dict, history, settings: Optional[M2Settings] = None) -> bool:
    s = settings or get_settings()
    flag = get(get(event, "context"), "input_taint")
    if flag != "trusted":          # "untrusted", missing, or anything unknown -> treat as untrusted
        return True
    sources = tuple((policy or {}).get("untrusted_sources") or DEFAULT_UNTRUSTED_SOURCES)
    now = parse_ts(get(event, "ts"))
    for h, _ts in history_in_window(history, now, s.taint_window_seconds):
        if get(h, "tool") in sources:
            return True
    return False


def apply_taint_rules(event, policy: dict, history, settings: Optional[M2Settings] = None) -> Optional[Finding]:
    s = settings or get_settings()
    tool = get(event, "tool")
    constraint = ((policy or {}).get("constraints") or {}).get(tool) or {}
    limit = constraint.get("untrusted_max_amount")
    needs_approval = bool(constraint.get("untrusted_requires_approval"))
    if limit is None and not needs_approval:
        return None                      # this tool has no dirty-data rule
    if not effective_taint(event, policy, history, s):
        return None
    amount = to_amount((get(event, "args") or {}).get("amount"))
    if needs_approval:
        over, why = True, f"{tool} was built from untrusted input and needs human approval"
    elif amount is None:
        over, why = True, f"{tool} was built from untrusted input and its amount could not be read"
    else:
        over = amount > float(limit)
        why = f"{tool} amount {amount:g} is above the {float(limit):g} limit for actions built from untrusted input"
    if not over:
        return None
    return Finding(
        "HOLD", f"taint.{tool}.untrusted_over_limit", why + ". Held for a human to approve.",
        "MEDIUM", penalty_key=None,       # no penalty: the agent may have been tricked, a human decides
        evidence={"amount": amount, "untrusted_limit": limit, "tool": tool},
    )
