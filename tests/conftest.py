# tests/conftest.py — shared fixtures (M1 + M2)
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _ensure_schema_and_agents(tmp_path, monkeypatch):
    """
    Every test gets a schema. Integration tests that touch the DB also get
    the three NovaBank agents registered so FK constraints succeed.
    """
    Path("data").mkdir(exist_ok=True)
    try:
        from gateway.db import db
        db.create_schema()
        # Seed NovaBank agents if keys exist (idempotent enough for tests)
        for agent_id in ("supportbot", "databot", "coordinator", "researcher", "emailer", "payments"):
            key_path = ROOT / "keys" / f"{agent_id}_public.pem"
            if not key_path.exists():
                continue
            pub = key_path.read_text().strip()
            try:
                existing = db.get_agent(agent_id)
            except Exception:
                existing = None
            if not existing:
                try:
                    db.insert_agent(agent_id, pub, status="HEALTHY", trust_score=100)
                except Exception:
                    pass
                # manifest optional for many tests
                man = ROOT / "manifests" / f"{agent_id}.manifest.json"
                if man.exists():
                    try:
                        import json
                        data = json.loads(man.read_text())
                        db.insert_manifest(
                            agent_id,
                            man.read_text(),
                            data.get("config_hash", ""),
                            data.get("admin_signature", ""),
                        )
                    except Exception:
                        pass
    except Exception as e:
        print(f"conftest seed warning: {e}")
    yield
