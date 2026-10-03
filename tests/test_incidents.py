# tests/test_incidents.py (Owner: M2)  FR20: each attack type makes a ticket with evidence + severity + owner.
from engine import enforcer, incidents
from engine.findings import Finding
from tests.m2_helpers import ev, pol


def inc_for(finding, mode="on"):
    e = ev("issue_refund", {"amount": 1})
    return incidents.create(enforcer.decide([finding], mode, "HEALTHY", trust_score=100, event=e, policy=pol()), e)


def test_plain_allow_creates_no_incident():
    e = ev("read_ticket")
    assert incidents.create(enforcer.decide([], "on", "HEALTHY", trust_score=100, event=e, policy=pol()), e) is None


def test_routing():
    assert inc_for(Finding("BLOCK", "constraints.issue_refund.max_amount", "x", "HIGH", "constraint_violated"))["owner"] == "finance"
    assert inc_for(Finding("BLOCK", "honeytoken.touched", "x", "CRITICAL", "honeytoken", True))["owner"] == "security"
    assert inc_for(Finding("BLOCK", "leak_filter.card_number", "x", "HIGH", "constraint_violated"))["owner"] == "security"
    assert inc_for(Finding("HOLD", "taint.issue_refund.untrusted_over_limit", "x"))["owner"] == "reviewer"
    assert inc_for(Finding("THROTTLE", "rate.agent.max_per_minute", "x", "MEDIUM", "rate_exceeded"))["owner"] == "developer"


def test_incident_has_the_required_fields():
    i = inc_for(Finding("BLOCK", "allow_tools.tool_not_allowed", "no", "HIGH", "tool_not_allowed"))
    for key in ("agent_id", "event_id", "severity", "rule", "reason", "owner", "resolved", "evidence"):
        assert key in i
    assert i["resolved"] is False and i["owner"] in incidents.OWNERS


def test_dry_run_would_block_still_makes_a_ticket():
    i = inc_for(Finding("BLOCK", "constraints.issue_refund.max_amount", "x", "HIGH", "constraint_violated"), mode="dry-run")
    assert i["dry_run"] is True and i["verdict"] == "BLOCK"
