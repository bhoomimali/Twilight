# engine/peer_trust.py
# Owner: M2   [W2: second wave, after the core is stable]   (Phase 7, scenario D5)
# Purpose: blast-radius containment. Agents refuse to deal with a compromised peer.
#
# WHY: quarantine stops ONE agent. But a hijacked agent can still try to push bad "instructions"
# through its neighbours. If peers refuse messages from a quarantined or low-trust sender, one
# bad agent cannot spread. We also list who it talked to so the dashboard can put them on watch.
#
# `registry` is a dict the gateway builds from the agents table:
#     {"supportbot": {"status": "HEALTHY", "trust": 100}, "databot": {...}}
from typing import Dict, List, Optional

from engine._util import get, history_in_window, parse_ts
from engine.findings import MESSAGE_TOOLS, Finding
from engine.settings import M2Settings, get_settings

BAD_STATUSES = ("QUARANTINED", "HALTED")


def peer_allowed(sender_status: str, sender_trust: Optional[int] = None, settings: Optional[M2Settings] = None) -> bool:
    s = settings or get_settings()
    if sender_status in BAD_STATUSES:
        return False
    return sender_trust is None or sender_trust >= s.peer_min_trust


def check_peer(event, registry: Dict[str, dict], settings: Optional[M2Settings] = None) -> Optional[Finding]:
    s = settings or get_settings()
    if get(event, "tool") not in MESSAGE_TOOLS:
        return None
    sender = get(event, "agent_id")
    args = get(event, "args") or {}
    recipient = args.get("to") or args.get("recipient")
    me = registry.get(sender) or {}
    if not peer_allowed(me.get("status", "HEALTHY"), me.get("trust"), s):
        return Finding(
            "BLOCK", "peer_trust.sender_untrusted",
            f"Peers refuse messages from {sender}: it is {me.get('status')} (trust {me.get('trust')}).",
            "HIGH", penalty_key="constraint_violated", evidence={"sender": sender, "status": me.get("status")})
    peer = registry.get(recipient) or {}
    if peer.get("status") in BAD_STATUSES:
        return Finding(
            "BLOCK", "peer_trust.recipient_quarantined",
            f"{recipient} is {peer.get('status')} and cannot receive messages.",
            "MEDIUM", evidence={"recipient": recipient, "status": peer.get("status")})
    return None


def blast_radius(agent_id: str, history, now, window_seconds: int = 3600) -> List[str]:
    """Everyone this agent messaged recently (these peers go 'on watch' on the dashboard)."""
    now_dt = parse_ts(now)
    seen: List[str] = []
    for h, _ in history_in_window(history, now_dt, window_seconds):
        if get(h, "agent_id", agent_id) == agent_id and get(h, "tool") in MESSAGE_TOOLS:
            a = get(h, "args") or {}
            r = a.get("to") or a.get("recipient")
            if r and r not in seen:
                seen.append(r)
    return seen
