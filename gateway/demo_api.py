"""Dashboard control endpoints (demo only).

  GET  /demo/state        everything the dashboard needs, polled every second
  POST /demo/mode         {"mode": "on"|"off", "reset": true}  flips the REAL gateway guard
  POST /demo/reset        fresh bank + fresh trust + empty audit log
  POST /demo/run-attack   launches the attack script; its conversation prints in THIS terminal
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gateway import ledger
from gateway.config import settings
from gateway.db import db
from gateway.tools import clear_effects

ROOT = Path(__file__).resolve().parent.parent
router = APIRouter(prefix="/demo", tags=["demo"])
_attack: dict = {"proc": None}

BLOCKING = {"BLOCK", "HOLD", "HALT", "QUARANTINE", "THROTTLE"}


class ModeBody(BaseModel):
    mode: str
    reset: bool = True


def _attack_running() -> bool:
    p = _attack["proc"]
    return p is not None and p.poll() is None


def soft_reset() -> None:
    """Clean slate without restarting the server or touching keys/configs."""
    conn = db.get_connection()
    for table in ("audit", "audit_checkpoints", "incidents", "nonces",
                  "trust_history", "held_actions", "events", "heartbeat_challenges"):
        try:
            conn.execute(f"DELETE FROM {table}")
        except Exception:
            pass
    try:
        conn.execute("DELETE FROM sqlite_sequence WHERE name='audit'")  # chain depth restarts at #1
    except Exception:
        pass
    conn.execute("UPDATE agents SET status='HEALTHY', trust_score=100, probation_until=NULL")
    conn.commit()
    ledger.reset()
    clear_effects()


@router.get("/state")
async def state():
    snap = ledger.snapshot()
    agents = [
        {"id": a["agent_id"], "trust": a["trust_score"], "status": a["status"]}
        for a in db.get_agents_with_history()
    ]
    events = []
    for row in db.get_audit_records(limit=25):  # newest first
        try:
            rec = json.loads(row["record_json"])
        except Exception:
            rec = {}
        events.append({
            "seq": row["seq"],
            "ts": rec.get("ts") or row.get("ts"),
            "agent_id": rec.get("agent_id") or row.get("agent_id"),
            "tool": rec.get("tool"),
            "args": rec.get("args"),
            "verdict": rec.get("verdict"),
            "reason": rec.get("reason"),
            "rule": rec.get("rule"),
            "trust_before": rec.get("trust_before"),
            "trust_after": rec.get("trust_after"),
            "hash": row.get("record_hash"),
        })
    if settings.runtime_mode == "off":
        # Guard OFF = Twilight is blind. Whatever the gateway saw is not shown anywhere.
        events, depth, blocks = [], None, 0
    else:
        depth, blocks = db.get_last_audit_seq(), sum(
            1 for e in events if str(e["verdict"]).upper() in BLOCKING)
    return {
        "mode": settings.runtime_mode,
        "attack_running": _attack_running(),
        **snap,
        "agents": agents,
        "events": events,
        "audit_depth": depth,
        "blocks": blocks,
    }


@router.post("/mode")
async def set_mode(body: ModeBody):
    if body.mode not in ("on", "off", "dry-run"):
        raise HTTPException(status_code=400, detail="mode must be on, off or dry-run")
    settings.runtime_mode = body.mode
    if body.reset:
        soft_reset()
    print(f"\n\033[1m[dashboard] Guard switched {body.mode.upper()}"
          f"{' (fresh state)' if body.reset else ''}\033[0m")
    return {"mode": settings.runtime_mode, "reset": body.reset}


@router.post("/reset")
async def reset():
    soft_reset()
    return {"ok": True}


@router.post("/run-attack")
async def run_attack(flavor: Optional[str] = "classic"):
    """flavor=classic -> scripts/run_attack.py (no LLM needed)
       flavor=langchain -> scripts/run_langchain_attack.py (uses GROQ/OPENAI key if set)"""
    if _attack_running():
        return {"started": False, "reason": "attack already running"}
    script, extra = (
        ("scripts/run_langchain_attack.py", ["--live"])
        if flavor == "langchain"
        else ("scripts/run_attack.py", ["--attacker", "both", "--live"])
    )
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("TWILIGHT_URL", f"http://127.0.0.1:{settings.gateway_port}")
    # No PIPE: the child inherits this terminal, so the agent conversation shows up right here.
    _attack["proc"] = subprocess.Popen(
        [sys.executable, script, "--mode", "auto", *extra], cwd=str(ROOT), env=env
    )
    return {"started": True, "mode": settings.runtime_mode, "flavor": flavor}
