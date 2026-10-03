"""Sign demo events with the agent's real Ed25519 key, so the gateway judges the *policy*
(refund limit, taint, rate) instead of rejecting an unsigned event.
Used by scripts/run_attack.py and the LangChain tools."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent


def sign_event(event: Dict[str, Any], agent_id: Optional[str] = None) -> Dict[str, Any]:
    agent_id = agent_id or event.get("agent_id")
    key_file = ROOT / "keys" / f"{agent_id}_private.pem"
    if not key_file.exists():
        return event  # stays unsigned: the gateway will reject it, which is the honest outcome

    import nacl.encoding
    import nacl.signing
    from gateway.schemas import canonical_json

    body = {k: v for k, v in event.items() if k != "signature"}
    sk = nacl.signing.SigningKey(key_file.read_text().strip(), encoder=nacl.encoding.HexEncoder)
    body["signature"] = sk.sign(canonical_json(body).encode("utf-8")).signature.hex()
    return body
