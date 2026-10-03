"""
tests/test_e2e_demo.py — D2-style path: large refund under policy; mode off via pipeline.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from engine.policy import check_policy
from engine.findings import Finding
from tests.m2_helpers import pol


def _ts():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _event(tool: str, args: dict, agent_id: str = "supportbot"):
    return {
        "event_id": str(uuid.uuid4()),
        "ts": _ts(),
        "agent_id": agent_id,
        "type": "tool_call",
        "tool": tool,
        "args": args,
        "context": {},
        "nonce": str(uuid.uuid4()),
        "signature": "e2e-unsigned",
    }


def test_d2_refund_9000_blocked_by_policy():
    """SupportBot YAML max_amount 500 → 9000 is not ALLOW."""
    policy = pol("supportbot")
    finding = check_policy(
        _event("issue_refund", {"amount": 9000, "ticket_id": "T-9000"}),
        policy,
        history=[],
    )
    assert isinstance(finding, Finding)
    assert finding.verdict != "ALLOW"
    assert finding.verdict in ("BLOCK", "HOLD", "QUARANTINE", "HALT", "THROTTLE", "FLAG")


def test_d2_refund_50_allowed_by_policy():
    policy = pol("supportbot")
    finding = check_policy(
        _event("issue_refund", {"amount": 50, "ticket_id": "T-50"}),
        policy,
        history=[],
    )
    assert finding.verdict in ("ALLOW", "FLAG")


def test_mode_off_skips_checks_in_pipeline():
    """PRD: off = no checks, action still runs — implemented in pipeline (not main)."""
    import pytest
    try:
        from gateway.pipeline import run_pipeline
    except Exception as exc:
        pytest.skip(f"pipeline import requires full deps: {exc}")

    event = _event("issue_refund", {"amount": 9000})
    try:
        from gateway.config import settings
        api_key = getattr(settings, "gateway_api_key", "") or ""
    except Exception:
        api_key = ""
    decision = run_pipeline(event, api_key, "off")
    v = decision.verdict
    vstr = v.value if hasattr(v, "value") else str(v)
    assert vstr.upper() == "ALLOW" or decision.response == "allow"
    assert "off" in (decision.rule or "").lower() or "off" in (decision.reason or "").lower()


def test_poisoner_and_talker_shapes():
    from attackers.poisoner import poison_ticket
    from attackers.talker import craft_refund_plea

    p = poison_ticket(amount=9000)
    assert p["requested_amount"] == 9000
    t = craft_refund_plea(9000)
    assert t["requested_amount"] == 9000
