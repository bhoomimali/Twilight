#!/usr/bin/env python3
"""Warm drift baselines with clean tool transitions (M3)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.drift import check_drift, reset_baselines, get_baseline


def main(agent_id: str = "supportbot", n: int = 40) -> None:
    reset_baselines()
    base_ts = 1_700_000_000.0
    tools = ["read_ticket", "issue_refund", "read_ticket", "issue_refund"]
    for i in range(n):
        tool = tools[i % len(tools)]
        check_drift({
            "agent_id": agent_id,
            "tool": tool,
            "args": {"id": i, "amount": 50} if tool == "issue_refund" else {"id": i},
            "ts": base_ts + i * 2.0,
        })
    bl = get_baseline(agent_id)
    print(f"Baseline for {agent_id}: rates={len(bl.rates)} last_tool={bl.last_tool}")
    print("Drift demo: send a burst of actions or unusual tool order after this.")


if __name__ == "__main__":
    main(*sys.argv[1:])
