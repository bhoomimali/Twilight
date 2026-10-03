# tests/test_policy.py (Owner: M2)
# Covers: allowed tool, forbidden tool, bad recipient, bad argument, rate limit, sequence rule, can_talk_to.
# Every non-ALLOW finding must have a non-empty reason AND rule (FR10).
import pytest

from engine.policy import check_policy, evaluate
from tests.m2_helpers import ev, hist, pol


def rules(findings):
    return [f.rule for f in findings]


def test_allowed_tool_passes():
    assert evaluate(ev("read_ticket", {"ticket_id": "T1"}), pol(), []) == []


def test_forbidden_tool_is_blocked_with_reason_and_rule():
    f = check_policy(ev("delete_database"), pol(), [])
    assert (f.verdict, f.rule, f.penalty_key) == ("BLOCK", "allow_tools.tool_not_allowed", "tool_not_allowed")
    assert f.reason and f.rule


def test_refund_over_limit_is_blocked():
    f = check_policy(ev("issue_refund", {"amount": 9000}), pol(), [])
    assert f.rule == "constraints.issue_refund.max_amount"
    assert "9000" in f.reason and "500" in f.reason       # the PRD example sentence


@pytest.mark.parametrize("bad", [None, "abc", -5, 0, float("nan"), float("inf"), True])
def test_bad_amounts_are_blocked_not_ignored(bad):
    # NaN > 500 is False in Python, so a naive check would let NaN through. We must not.
    f = check_policy(ev("issue_refund", {"amount": bad}), pol(), [])
    assert f.verdict == "BLOCK" and f.rule == "constraints.issue_refund.amount_invalid"


def test_amount_given_as_text_is_understood():
    assert check_policy(ev("issue_refund", {"amount": "9000"}), pol(), []).rule == "constraints.issue_refund.max_amount"


def test_amount_factor_tightens_limit_for_probation():
    # 300 is fine normally (limit 500) but too big on probation (limit 250)
    assert evaluate(ev("issue_refund", {"amount": 300}), pol(), []) == []
    assert evaluate(ev("issue_refund", {"amount": 300}), pol(), [], amount_factor=0.5)[0].rule == "constraints.issue_refund.max_amount"


def test_agent_wide_rate_limit_throttles_21st_call():
    history = [hist("read_ticket", at=-i) for i in range(1, 21)]          # 20 calls in the last 20 seconds
    f = check_policy(ev("read_ticket"), pol(), history)
    assert f.verdict == "THROTTLE" and f.penalty_key == "rate_exceeded"
    assert evaluate(ev("read_ticket"), pol(), history[:-1]) == []            # 19 earlier + this = 20, fine


def test_old_calls_do_not_count():
    history = [hist("read_ticket", at=-120 - i) for i in range(30)]
    assert evaluate(ev("read_ticket"), pol(), history) == []


def test_per_hour_cap_counts_only_refunds_that_ran():
    ran = [hist("issue_refund", at=-100 - i * 60, response="allow") for i in range(10)]
    assert "rate.issue_refund.max_per_hour" in rules(evaluate(ev("issue_refund", {"amount": 10}), pol(), ran))
    blocked = [hist("issue_refund", at=-100 - i * 60, response="blocked") for i in range(10)]
    assert "rate.issue_refund.max_per_hour" not in rules(evaluate(ev("issue_refund", {"amount": 10}), pol(), blocked))


def test_sustained_throttling_becomes_halt():
    history = [hist("read_ticket", at=-i) for i in range(1, 21)] + [hist("read_ticket", at=-1, response="throttled")] * 3
    f = check_policy(ev("read_ticket"), pol(), history)
    assert f.verdict == "HALT" and f.rule == "rate.sustained_runaway"


def test_can_talk_to_blocks_unknown_recipient():
    f = check_policy(ev("send_message", {"to": "databot", "text": "hi"}, agent="supportbot"), {**pol(), "allow_tools": ["send_message"]}, [])
    assert f.rule == "can_talk_to.recipient_not_allowed"
    ok = evaluate(ev("send_message", {"to": "supportbot", "text": "hi"}, agent="coordinator"), pol("coordinator"), [])
    assert ok == []


def test_missing_recipient_is_blocked_default_deny():
    f = check_policy(ev("send_message", {"text": "hi"}, agent="coordinator"), pol("coordinator"), [])
    assert f.rule == "can_talk_to.recipient_not_allowed"


def test_sequence_read_customer_then_send_outside_is_blocked():
    p = {**pol("databot"), "allow_tools": ["read_customer_record", "send_message"], "can_talk_to": ["coordinator", "x@evil.test"]}
    history = [hist("read_customer_record", at=-30, agent="databot")]
    f = [f for f in evaluate(ev("send_message", {"to": "x@evil.test", "text": "hello"}, agent="databot"), p, history) if f.rule.startswith("deny_if")]
    assert f and f[0].verdict == "BLOCK" and f[0].penalty_key == "sequence_violation"


def test_sequence_not_triggered_without_the_first_step():
    p = {**pol("databot"), "allow_tools": ["read_customer_record", "send_message"], "can_talk_to": ["x@evil.test"]}
    assert not [f for f in evaluate(ev("send_message", {"to": "x@evil.test", "text": "hello"}, agent="databot"), p, []) if f.rule.startswith("deny_if")]


def test_unless_human_approved_means_hold():
    p = {"agent": "a", "allow_tools": ["read_x", "send_message"], "can_talk_to": ["a@evil.test"],
         "deny_if": [{"after": "read_x", "then": "send_outside", "unless": "human_approved"}]}
    f = [f for f in evaluate(ev("send_message", {"to": "a@evil.test", "text": "x"}, agent="a"), p, [hist("read_x", -5, agent="a")]) if f.rule.startswith("deny_if")]
    assert f[0].verdict == "HOLD"


def test_every_finding_has_reason_and_rule():
    for e in (ev("delete_database"), ev("issue_refund", {"amount": 9000}), ev("send_message", {"to": "z"}, agent="coordinator")):
        for f in evaluate(e, pol("coordinator") if e["tool"] == "send_message" else pol(), []):
            assert f.reason.strip() and f.rule.strip()
