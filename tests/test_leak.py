# tests/test_leak.py (Owner: M2)
# Covers: card number blocked, outside email blocked, secrets blocked, normal text passes (no false alarm).
from engine.leak_filter import check_leak, luhn_ok, scan_text
from tests.m2_helpers import ev, pol


def msg(text, to="supportbot"):
    return ev("send_message", {"to": to, "text": text}, agent="coordinator")


def test_normal_text_passes():
    for text in ("Your refund of 50 has been processed.", "Please handle ticket T1042 for cust_007.",
                 "Order 1234567890123 shipped",            # 13 digits but fails Luhn
                 "event 3f2b8c1e-9a4d-4e7b-8c11-0d5a1b2c3d4e"):  # a UUID is not a secret
        assert check_leak(msg(text), pol("coordinator")) is None, text


def test_card_number_blocked_and_masked():
    for text in ("card 4111 1111 1111 1111", "card 4111-1111-1111-1111", "4111111111111111"):
        f = check_leak(msg(text), pol("coordinator"))
        assert f and f.rule == "leak_filter.card_number" and f.verdict == "BLOCK"
        assert "4111111111111111" not in str(f.evidence)           # the leaked value must not be logged
        assert f.evidence["hits"][0]["masked"].endswith("1111")


def test_outside_email_blocked_internal_allowed():
    f = check_leak(msg("send it to bob@attacker.com"), pol("coordinator"))
    assert f and f.rule == "leak_filter.outside_email" and f.evidence["hits"][0]["domain"] == "attacker.com"
    assert check_leak(msg("cc alice@novabank.test"), pol("coordinator")) is None
    assert check_leak(msg("cc alice@mail.novabank.test"), pol("coordinator")) is None
    assert check_leak(msg("cc alice@evilnovabank.test"), pol("coordinator")) is not None   # look-alike domain


def test_secrets_blocked():
    for text in ("key sk-abcdefghijklmnop1234", "AKIAABCDEFGHIJKLMNOP", "-----BEGIN RSA PRIVATE KEY-----",
                 "token Zx9Qm2LkP7vR4tY8uW1nB6cD3fG5hJ0sA2eX7iO9pK4lM1"):
        f = check_leak(msg(text), pol("coordinator"))
        assert f and f.rule == "leak_filter.secret_key", text


def test_only_outbound_tools_are_scanned():
    assert check_leak(ev("issue_refund", {"customer": "4111111111111111", "amount": 5}), pol()) is None


def test_luhn():
    assert luhn_ok("4111111111111111") and not luhn_ok("4111111111111112")


def test_nested_args_are_scanned():
    e = ev("send_message", {"to": "supportbot", "payload": {"rows": [{"note": "4111 1111 1111 1111"}]}}, agent="coordinator")
    assert check_leak(e, pol("coordinator")) is not None


def test_scan_text_clean_returns_empty_list():
    assert scan_text("hello world") == []
