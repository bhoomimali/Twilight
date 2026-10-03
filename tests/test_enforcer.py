# tests/test_enforcer.py (Owner: M2)
# FR9 fail-closed, FR10 reason+rule, FR11 modes, status ladder, verdict precedence.
import pytest

from engine import enforcer, findings
from engine.findings import Finding
from engine.policy import evaluate
from tests.m2_helpers import ev, hist, pol


def decide(results, mode="on", status="HEALTHY", score=100, tool="issue_refund", **kw):
    return enforcer.decide(results, mode, status, trust_score=score, event=ev(tool, kw.pop("args", {"amount": 5})), policy=pol())


def test_clean_action_is_allowed_with_reason_and_rule():
    d = decide([])
    assert (d.verdict, d.response, d.trust_after) == ("ALLOW", "allow", 100) and d.reason and d.rule


def test_block_beats_hold_and_throttle():
    d = decide([Finding("HOLD", "a.hold", "h"), Finding("BLOCK", "b.block", "b", "HIGH", "constraint_violated"), Finding("THROTTLE", "c", "t")])
    assert d.verdict == "BLOCK" and d.rule == "b.block" and d.trust_after == 75


def test_fail_closed_on_internal_error():
    class Boom:
        verdict = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
    d = decide([Boom()])
    assert d.verdict == "BLOCK" and d.rule == "enforcer.internal_error" and d.evidence["error_type"] == "RuntimeError"


def test_unknown_mode_fails_closed():
    assert decide([], mode="yolo").verdict == "BLOCK"


def test_unknown_verdict_is_rejected_at_creation():
    with pytest.raises(ValueError):
        Finding("DENY", "x", "y")


def test_modes_same_attack_three_outcomes_FR11():
    attack = evaluate(ev("issue_refund", {"amount": 9000}), pol(), [])
    off, dry, on = decide(attack, "off"), decide(attack, "dry-run"), decide(attack, "on")
    assert off.verdict == "ALLOW" and off.rule == "mode.off"
    assert dry.response == "allow" and dry.evidence["would_verdict"] == "BLOCK" and dry.trust_after == 100 and "DRY-RUN" in dry.reason
    assert on.verdict == "BLOCK" and on.trust_after < 100


def test_quarantined_and_halted_agents_are_rejected_first():
    q = decide([], status="QUARANTINED", score=10)
    h = decide([], status="HALTED", score=10)
    assert (q.verdict, q.response, q.status) == ("BLOCK", "blocked", "QUARANTINED")
    assert (h.verdict, h.response, h.status) == ("HALT", "halted", "HALTED")
    assert decide([], mode="off", status="HALTED").verdict == "ALLOW"        # off means off


def test_status_ladder_makes_clean_actions_stricter():
    assert decide([], status="FLAGGED", score=60).verdict == "FLAG"
    assert decide([], status="THROTTLED", score=30).verdict == "HOLD"                   # risky tool (has constraints)
    assert decide([], status="THROTTLED", score=30, tool="read_ticket", args={}).verdict == "ALLOW"   # not risky


def test_penalty_that_crosses_the_edge_becomes_quarantine():
    d = decide([Finding("BLOCK", "allow_tools.tool_not_allowed", "no", "HIGH", "tool_not_allowed")], status="THROTTLED", score=30)
    assert d.verdict == "QUARANTINE" and d.status == "QUARANTINED" and d.response == "blocked"


def test_config_mismatch_quarantines_at_once():
    d = decide([findings.from_config_mismatch("aaa", "bbb")])
    assert d.verdict == "QUARANTINE" and d.status == "QUARANTINED" and d.severity == "CRITICAL"


def test_halt_verdict_sets_halted():
    assert decide([Finding("HALT", "rate.sustained_runaway", "x", "CRITICAL", "rate_exceeded", True)]).status == "HALTED"


def test_same_penalty_is_applied_once_per_action():
    two = [Finding("BLOCK", "r1", "x", "HIGH", "constraint_violated"), Finding("BLOCK", "r2", "y", "HIGH", "constraint_violated")]
    assert decide(two).trust_after == 75


def test_every_decision_has_reason_and_rule():
    for results, kw in (([], {}), ([Finding("HOLD", "a", "b")], {}), ([], {"mode": "off"}), ([], {"status": "HALTED"})):
        d = decide(results, **kw)
        assert d.reason.strip() and d.rule.strip()
