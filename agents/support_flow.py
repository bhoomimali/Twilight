"""
SupportBot decision flow for demos: read attacker text → propose issue_refund.
Does not execute money movement; gateway / policy decides.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def extract_amount(text: str, default: float = 9000.0) -> float:
    m = re.search(r"(?:amount\s*=\s*|₹|\$)\s*([0-9]+(?:\.[0-9]+)?)", text, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"refund of (?:₹|\$)?([0-9]+(?:\.[0-9]+)?)", text, re.I)
    if m:
        return float(m.group(1))
    return default


def decide_from_message(message: Dict[str, Any], agent_id: str = "supportbot") -> Dict[str, Any]:
    """
    Naive agent: if the message asks for a refund, propose issue_refund.
    This is intentional — Twilight is what should stop the bad call.
    """
    body = str(message.get("body", ""))
    amount = float(message.get("requested_amount") or extract_amount(body))
    customer_id = message.get("customer_id") or "TB-4471"
    ticket_id = message.get("ticket_id") or "T-UNKNOWN"
    taint = message.get("taint") or (
        "untrusted" if message.get("attack_type") not in (None, "benign") else "trusted"
    )

    tool = "issue_refund"
    args = {
        "amount": amount,
        "ticket_id": ticket_id,
        "customer_id": customer_id,
    }
    context = {
        "input_taint": taint,
        "source": message.get("attack_type") or message.get("channel") or "unknown",
        "ticket_body_preview": body[:160],
    }

    event = {
        "event_id": str(uuid.uuid4()),
        "ts": _ts(),
        "agent_id": agent_id,
        "type": "tool_call",
        "tool": tool,
        "args": args,
        "context": context,
        "nonce": str(uuid.uuid4()),
        "signature": "demo-unsigned",  # real signing optional via BaseAgent
    }
    return event


def say_reading(message: Dict[str, Any]) -> str:
    return f"[supportbot] reading {message.get('channel', 'message')} {message.get('ticket_id')}…"


def say_action(event: Dict[str, Any]) -> str:
    return f"[supportbot] → {event['tool']}({event['args']})"
