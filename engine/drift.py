"""
engine/drift.py — Owner: M3 (Identity, Audit & Analytics Lead)
[W2] Behavioural drift: z-score / EWMA on rate & arg size, Markov tool transitions.

Pipeline calls: check_drift(event, history) -> Optional[Finding]
Also: score_drift(...), reset_baselines(), get_baseline()
"""
from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

from engine.findings import Finding

RATE_WINDOW_MIN = 10
ARG_SIZE_MIN = 10
Z_THRESHOLD = 3.0
EWMA_ALPHA = 0.2
MARKOV_MIN_COUNT = 5


@dataclass
class AgentBaseline:
    rates: Deque[float] = field(default_factory=lambda: deque(maxlen=200))
    arg_sizes: Deque[float] = field(default_factory=lambda: deque(maxlen=50))
    transitions: Deque[Tuple[str, str]] = field(default_factory=lambda: deque(maxlen=100))
    last_tool: Optional[str] = None
    last_ts: Optional[float] = None
    ewma_rate: float = 0.0
    ewma_arg: float = 0.0
    transition_counts: Dict[Tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))
    tool_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))


_baselines: Dict[str, AgentBaseline] = {}


def _mean_std(values: List[float]) -> Tuple[float, float]:
    if not values:
        return 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    var = sum((x - mean) ** 2 for x in values) / (n - 1)
    return mean, math.sqrt(var)


def _z(value: float, mean: float, std: float) -> float:
    if std < 1e-9:
        return 0.0
    return (value - mean) / std


def get_baseline(agent_id: str) -> AgentBaseline:
    if agent_id not in _baselines:
        _baselines[agent_id] = AgentBaseline()
    return _baselines[agent_id]


def reset_baselines() -> None:
    _baselines.clear()


def _parse_ts(ts_raw: Any) -> float:
    if isinstance(ts_raw, (int, float)):
        return float(ts_raw)
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")).timestamp()
    except Exception:
        import time
        return time.time()


def check_drift(event: Dict[str, Any], history=None, *, z_threshold: float = Z_THRESHOLD) -> Optional[Finding]:
    """
    Pipeline step 5 entrypoint.
    Returns a Finding (usually FLAG) when anomalous, else None.
    """
    agent_id = str(event.get("agent_id") or "unknown")
    hit = score_drift(agent_id, event, history, z_threshold=z_threshold)
    if not hit:
        return None
    return Finding(
        verdict=hit["verdict"],
        rule=hit["rule"],
        reason=hit["reason"],
        severity=hit.get("severity") or "MEDIUM",
        penalty_key="drift_anomaly",
        evidence=hit.get("evidence") or {},
    )


def score_drift(
    agent_id: str,
    event: Dict[str, Any],
    history=None,
    *,
    z_threshold: float = Z_THRESHOLD,
) -> Optional[Dict[str, Any]]:
    bl = get_baseline(agent_id)
    tool = str(event.get("tool") or event.get("type") or "unknown")
    args = event.get("args") or {}
    arg_size = float(len(str(args)))
    ts = _parse_ts(event.get("ts"))
    evidence: Dict[str, Any] = {"tool": tool, "arg_size": arg_size}
    findings: List[Dict[str, Any]] = []

    if bl.last_ts is not None:
        delta = max(ts - bl.last_ts, 1e-3)
        instant_rate = 1.0 / delta
        bl.rates.append(instant_rate)
        bl.ewma_rate = (
            EWMA_ALPHA * instant_rate + (1 - EWMA_ALPHA) * bl.ewma_rate
            if bl.ewma_rate else instant_rate
        )
        mean_r, std_r = _mean_std(list(bl.rates))
        z_rate = _z(instant_rate, mean_r, std_r)
        evidence["rate"] = instant_rate
        evidence["z_rate"] = round(z_rate, 3)
        if abs(z_rate) >= z_threshold and len(bl.rates) >= RATE_WINDOW_MIN:
            findings.append({
                "verdict": "FLAG",
                "rule": "drift.rate_zscore",
                "reason": f"Action rate z-score {z_rate:.2f} exceeds threshold {z_threshold}.",
                "severity": "MEDIUM",
                "evidence": {"z_rate": z_rate, "rate": instant_rate},
            })
    bl.last_ts = ts

    bl.arg_sizes.append(arg_size)
    bl.ewma_arg = (
        EWMA_ALPHA * arg_size + (1 - EWMA_ALPHA) * bl.ewma_arg
        if bl.ewma_arg else arg_size
    )
    mean_a, std_a = _mean_std(list(bl.arg_sizes))
    z_arg = _z(arg_size, mean_a, std_a)
    evidence["z_arg_size"] = round(z_arg, 3)
    if abs(z_arg) >= z_threshold and len(bl.arg_sizes) >= ARG_SIZE_MIN:
        findings.append({
            "verdict": "FLAG",
            "rule": "drift.arg_size_zscore",
            "reason": f"Argument size z-score {z_arg:.2f} exceeds threshold {z_threshold}.",
            "severity": "LOW",
            "evidence": {"z_arg_size": z_arg, "arg_size": arg_size},
        })

    if bl.last_tool is not None:
        pair = (bl.last_tool, tool)
        bl.transitions.append(pair)
        bl.transition_counts[pair] += 1
        bl.tool_counts[bl.last_tool] += 1
        total_from = bl.tool_counts[bl.last_tool]
        if total_from >= MARKOV_MIN_COUNT:
            expected = bl.transition_counts[pair] / total_from
            if bl.transition_counts[pair] <= 1 and expected < 0.05:
                findings.append({
                    "verdict": "FLAG",
                    "rule": "drift.tool_transition",
                    "reason": f"Unusual tool transition {bl.last_tool} -> {tool}.",
                    "severity": "MEDIUM",
                    "evidence": {"from": bl.last_tool, "to": tool, "count": bl.transition_counts[pair]},
                })
    bl.last_tool = tool

    if not findings:
        return None
    rank = {"ALLOW": 0, "FLAG": 1, "THROTTLE": 2, "HOLD": 3, "BLOCK": 4, "QUARANTINE": 5, "HALT": 6}
    best = max(findings, key=lambda f: rank.get(f["verdict"], 0))
    best["evidence"] = {**evidence, **best.get("evidence", {})}
    return best
