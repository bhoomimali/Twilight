# engine/incidents.py
# Owner: M2   (Phase 4-5)
# Purpose: turn a notable Decision into an incident ticket and send it to the right owner (FR20).
# Plain ALLOWs create nothing. Everything else does, because "what the guard did" is the story.
#
# Interface for M1: create(decision, event=None) -> incident dict (or None for a plain ALLOW).
# M1 saves it in the incidents table and publishes it on the WebSocket.
from typing import Optional

from engine._util import get

OWNERS = ("finance", "security", "developer", "reviewer")
# first matching prefix wins
_ROUTES = (
    ("honeytoken", "security"), ("leak_filter", "security"), ("attestation", "security"),
    ("deny_if", "security"), ("can_talk_to", "security"), ("peer_trust", "security"),
    ("allow_tools", "security"), ("status.", "security"),
    ("constraints.issue_refund", "finance"), ("taint.issue_refund", "finance"),
    ("rate", "developer"), ("drift", "developer"), ("enforcer.internal_error", "developer"),
)


def route_owner(rule: str, verdict: str) -> str:
    if verdict == "HOLD" and rule.startswith(("taint", "status", "deny_if")):
        return "reviewer"                       # a human has to approve or deny
    for prefix, owner in _ROUTES:
        if rule.startswith(prefix):
            return owner
    return "security" if verdict in ("BLOCK", "QUARANTINE", "HALT") else "reviewer"


def create(decision, event=None) -> Optional[dict]:
    verdict, evidence = decision.verdict, dict(decision.evidence or {})
    would = evidence.get("would_verdict")
    if verdict == "ALLOW" and not would:
        return None
    shown = would or verdict
    severity = decision.severity if shown != "FLAG" else "LOW"
    return {
        "agent_id": decision.agent_id, "event_id": decision.event_id,
        "severity": severity, "rule": decision.rule, "reason": decision.reason,
        "owner": route_owner(decision.rule, shown), "resolved": False,
        "evidence": evidence, "verdict": shown, "dry_run": bool(would),
        "created_at": get(event, "ts"),
    }
