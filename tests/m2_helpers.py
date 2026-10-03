# tests/m2_helpers.py (Owner: M2): small builders so tests read like sentences.
import itertools
import os
from datetime import datetime, timedelta, timezone

from engine import policy as policy_mod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T0 = datetime(2026, 10, 2, 10, 0, 0, tzinfo=timezone.utc)
_n = itertools.count(1)


def ts(offset_seconds=0):
    return (T0 + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def ev(tool, args=None, agent="supportbot", at=0, taint="trusted"):
    return {"event_id": f"e{next(_n)}", "ts": ts(at), "agent_id": agent, "type": "tool_call",
            "tool": tool, "args": args or {}, "context": {"triggered_by": None, "input_taint": taint}}


def hist(tool, at, response="allow", args=None, agent="supportbot"):
    return {"ts": ts(at), "agent_id": agent, "tool": tool, "args": args or {}, "response": response}


def pol(agent="supportbot"):
    return policy_mod.load_policy(os.path.join(ROOT, "policies", f"{agent}.yaml"))
