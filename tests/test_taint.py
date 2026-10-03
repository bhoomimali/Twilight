# tests/test_taint.py (Owner: M2)
# FR14: a 400 refund after reading an untrusted ticket is HELD, a 50 refund is allowed.
from engine.policy import evaluate
from engine.taint import apply_taint_rules, effective_taint
from tests.m2_helpers import ev, hist, pol

TICKET = [hist("read_ticket", at=-30)]


def test_400_held_50_allowed_after_untrusted_ticket():
    big = apply_taint_rules(ev("issue_refund", {"amount": 400}), pol(), TICKET)
    assert big.verdict == "HOLD" and big.penalty_key is None            # a human decides, no penalty
    assert apply_taint_rules(ev("issue_refund", {"amount": 50}), pol(), TICKET) is None


def test_no_ticket_read_and_trusted_means_no_hold():
    assert apply_taint_rules(ev("issue_refund", {"amount": 400}), pol(), []) is None


def test_event_flag_alone_is_enough():
    assert apply_taint_rules(ev("issue_refund", {"amount": 400}, taint="untrusted"), pol(), []).verdict == "HOLD"


def test_missing_or_weird_flag_is_treated_as_untrusted():
    e = ev("issue_refund", {"amount": 400}); e["context"]["input_taint"] = "banana"
    assert effective_taint(e, pol(), []) is True
    e["context"] = {}
    assert effective_taint(e, pol(), []) is True


def test_taint_expires_after_the_window():
    old = [hist("read_ticket", at=-3600)]
    assert apply_taint_rules(ev("issue_refund", {"amount": 400}), pol(), old) is None


def test_agent_cannot_clear_it_by_claiming_approval():
    e = ev("issue_refund", {"amount": 400}); e["context"]["human_approved"] = True
    assert apply_taint_rules(e, pol(), TICKET).verdict == "HOLD"


def test_taint_and_amount_limit_together_block_wins():
    rules = [(f.verdict, f.rule) for f in evaluate(ev("issue_refund", {"amount": 9000}, taint="untrusted"), pol(), [])]
    assert ("BLOCK", "constraints.issue_refund.max_amount") in rules and ("HOLD", "taint.issue_refund.untrusted_over_limit") in rules
