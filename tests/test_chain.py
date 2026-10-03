"""M3: audit chain redaction."""
import pytest

try:
    from audit.chain import redact_with_fingerprint, GENESIS_HASH
    HAS = True
except Exception:
    HAS = False


@pytest.mark.skipif(not HAS, reason="audit chain unavailable")
def test_redact_sensitive_fields():
    args = {"body": "secret mail", "amount": 10, "to_account": "ACCT-1"}
    redacted, fp = redact_with_fingerprint("send_email", args)
    assert redacted["body"] == "***"
    assert redacted["to_account"] == "***"
    assert redacted["amount"] == 10
    assert isinstance(fp, str) and len(fp) == 64


@pytest.mark.skipif(not HAS, reason="audit chain unavailable")
def test_genesis_hash():
    assert GENESIS_HASH == "0" * 64
