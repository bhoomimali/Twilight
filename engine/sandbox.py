"""
engine/sandbox.py — Owner: M3
[S] Replay dataset rows as fake agent actions for offline detection metrics.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple


@dataclass
class SandboxResult:
    total: int = 0
    caught: int = 0
    missed: int = 0
    false_alarms: int = 0
    details: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def precision(self) -> float:
        tp, fp = self.caught, self.false_alarms
        return tp / (tp + fp) if (tp + fp) else 0.0

    @property
    def recall(self) -> float:
        tp, fn = self.caught, self.missed
        return tp / (tp + fn) if (tp + fn) else 0.0

    def summary(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "caught": self.caught,
            "missed": self.missed,
            "false_alarms": self.false_alarms,
            "precision": round(self.precision, 3),
            "recall": round(self.recall, 3),
        }


def load_dataset(path: str | Path) -> List[Dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(l) for l in text.splitlines() if l.strip()]
    data = json.loads(text)
    if isinstance(data, list):
        return data
    return data.get("events") or []


def row_to_event(row: Dict[str, Any], agent_id: str = "sandbox_agent") -> Dict[str, Any]:
    return {
        "event_id": row.get("event_id") or str(uuid.uuid4()),
        "ts": row.get("ts") or datetime.now(timezone.utc).isoformat(),
        "agent_id": row.get("agent_id") or agent_id,
        "type": "tool_call",
        "tool": row.get("tool") or "unknown",
        "args": row.get("args") or {},
        "context": row.get("context") or {},
        "signature": row.get("signature") or "sandbox-unsigned",
        "nonce": row.get("nonce") or str(uuid.uuid4()),
    }


def run_sandbox(
    dataset_path: str | Path,
    checker: Callable[[Dict[str, Any]], Dict[str, Any]],
    *,
    attack_labels: Tuple[str, ...] = ("attack", "malicious", "bad"),
) -> SandboxResult:
    rows = load_dataset(dataset_path)
    result = SandboxResult()
    for row in rows:
        event = row_to_event(row)
        label = str(row.get("label") or row.get("expected") or "benign").lower()
        is_attack = label in attack_labels
        try:
            decision = checker(event)
        except Exception as exc:
            decision = {"verdict": "BLOCK", "reason": f"checker error: {exc}"}
        verdict = str(decision.get("verdict") or "ALLOW").upper()
        if is_attack:
            if verdict in ("FLAG", "HOLD", "THROTTLE", "BLOCK", "QUARANTINE", "HALT"):
                result.caught += 1
            else:
                result.missed += 1
        else:
            if verdict in ("BLOCK", "QUARANTINE", "HALT", "HOLD"):
                result.false_alarms += 1
        result.total += 1
        result.details.append({
            "event_id": event["event_id"],
            "tool": event["tool"],
            "label": label,
            "verdict": verdict,
            "reason": decision.get("reason"),
        })
    return result


def write_report(result: SandboxResult, out_path: str | Path) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"summary": result.summary(), "details": result.details[:200]}, indent=2),
        encoding="utf-8",
    )
