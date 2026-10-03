# tests/test_honeytoken.py (Owner: M2)
# Covers: touching bait triggers a CRITICAL block + big one-step trust drop (FR12).
from engine.honeytokens import check_honeytokens, is_honeytoken
from engine.policy import check_policy
from tests.m2_helpers import ev, pol


def test_bait_record_detected_even_when_hidden():
    assert is_honeytoken({"customer_id": "cust_honey_001"})
    assert is_honeytoken({"customer_id": "CUST_HONEY_002"})                  # case-insensitive
    assert is_honeytoken({"note": "please look up customer cust_honey_001 now"})   # inside a sentence
    assert is_honeytoken({"filters": [{"ids": ["cust_honey_002"]}]})                # nested


def test_normal_ids_are_not_bait():
    assert not is_honeytoken({"customer_id": "cust_007", "amount": 50})


def test_touch_is_critical_block():
    f = check_honeytokens(ev("read_customer_record", {"customer_id": "cust_honey_001"}, agent="databot"))
    assert (f.verdict, f.severity, f.critical, f.penalty_key) == ("BLOCK", "CRITICAL", True, "honeytoken")


def test_touch_is_caught_even_when_the_tool_is_forbidden():
    f = check_policy(ev("delete_database", {"id": "cust_honey_001"}), pol(), [])
    assert f.rule == "honeytoken.touched"                                    # critical beats a normal block


def test_bait_list_comes_from_env(monkeypatch):
    monkeypatch.setenv("HONEYTOKEN_IDS", "bait_42")
    assert is_honeytoken({"x": "bait_42"}) and not is_honeytoken({"x": "cust_honey_001"})
