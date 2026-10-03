"""M3: attestation smoke tests."""
import pytest

try:
    from engine.attestation import (
        verify_signature,
        check_nonce_and_timestamp,
        verify_config_hash,
        insert_nonce,
    )
    HAS = True
except Exception:
    HAS = False


@pytest.mark.skipif(not HAS, reason="attestation unavailable")
def test_missing_signature_rejected():
    ok, err = verify_signature({"agent_id": "x", "tool": "read_ticket", "args": {}}, "00" * 32)
    assert ok is False
    assert err


@pytest.mark.skipif(not HAS, reason="attestation unavailable")
def test_helpers_callable():
    assert callable(check_nonce_and_timestamp)
    assert callable(insert_nonce)
    assert callable(verify_config_hash)
