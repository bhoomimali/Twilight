# engine/enforcer.py
# Owner: M2   (Phase 3)
# Purpose: the ONE place that turns findings into ONE final Decision.
#
# Interface for M1 (pipeline steps 1, 6, 8, 9):
#     check_status_first(agent_status, ...) -> Decision or None     (step 1, cheapest check)
#     decide(results, mode, status, *, trust_score, event, policy)  -> Decision
#
# Rules from the PRD that live here:
#   - verdicts: ALLOW FLAG HOLD THROTTLE BLOCK QUARANTINE HALT. Unknown values are rejected.
#   - modes: off (no checks) / dry-run (log "would block", action still runs) / on (full).
#   - fail closed: if ANYTHING goes wrong in here, the answer is BLOCK.
#   - golden rule: nothing in this file calls an LLM, and nothing can lower a verdict because
#     somebody "explained" it nicely.
#   - every Decision has a non-empty reason and rule (FR10).
#
# GATING NOTE FOR M1: run the tool only when decision.response == "allow".
# In dry-run we return verdict ALLOW (so the action runs) and keep the real answer in
# evidence["would_verdict"], so there is no way to accidentally block in dry-run.
from typing import Iterable, Optional

from engine import trust as trust_mod
from engine._util import get
from engine.findings import (MODES, RESPONSE_FOR_VERDICT, SEVERITY_RANK, VERDICT_RANK, Finding, worst)
from engine.settings import M2Settings, get_settings
from gateway.schemas import Decision


def _decision(event, verdict, rule, reason, severity, before, after, status, evidence=None) -> Decision:
    return Decision(
        event_id=str(get(event, "event_id", "unknown")), agent_id=str(get(event, "agent_id", "unknown")),
        verdict=verdict, response=RESPONSE_FOR_VERDICT[verdict], reason=reason, rule=rule,
        severity=severity, trust_before=before, trust_after=after, status=status, latency_ms=0.0,
        evidence=evidence or {},
    )


def check_status_first(agent_status: str, event=None, trust_score: int = 0) -> Optional[Decision]:
    """Pipeline step 1. A QUARANTINED or HALTED agent is rejected right away (cheapest check)."""
    if agent_status == "HALTED":
        return _decision(event, "HALT", "status.halted", "This agent is HALTED. A human must resume it.",
                         "HIGH", trust_score, trust_score, "HALTED")
    if agent_status == "QUARANTINED":
        return _decision(event, "BLOCK", "status.quarantined",
                         "This agent is QUARANTINED, so every action it sends is rejected.",
                         "HIGH", trust_score, trust_score, "QUARANTINED")
    return None


def decide(results: Iterable, mode: str, status: str, *, trust_score: Optional[int] = None, event=None,
           policy: Optional[dict] = None, settings: Optional[M2Settings] = None) -> Decision:
    s = settings or get_settings()
    before = s.trust_start if trust_score is None else trust_score
    try:
        return _decide(list(results), mode, status, before, event, policy, s)
    except Exception as exc:     # FAIL CLOSED: a crash must never become a free pass
        return _decision(event, "BLOCK", "enforcer.internal_error", "Internal error while deciding, so the action was blocked.",
                         "HIGH", before, before, status if status in ("QUARANTINED", "HALTED") else "HEALTHY",
                         {"error_type": type(exc).__name__})


def _decide(results, mode, status, before, event, policy, s: M2Settings) -> Decision:
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode!r}")
    if mode == "off":
        return _decision(event, "ALLOW", "mode.off", "Guard is OFF: no checks were run.", "LOW", before, before, status, {"mode": "off"})

    findings = [f for f in results if get(f, "verdict") != "ALLOW"]
    findings = [f if isinstance(f, Finding) else Finding(f.verdict, f.rule, f.reason, f.severity) for f in findings]

    # 1. status first
    gate = check_status_first(status, event, before)
    if gate is not None:
        findings.append(Finding(gate.verdict, gate.rule, gate.reason, gate.severity))

    top = worst(findings) if findings else None
    verdict = top.verdict if top else "ALLOW"
    rule, reason, severity = (top.rule, top.reason, top.severity) if top else ("allow.clean", "No rule matched, action allowed.", "LOW")

    # 2. the status ladder makes the SAME clean action stricter when the agent is already in trouble
    tool = get(event, "tool")
    risky = bool(((policy or {}).get("constraints") or {}).get(tool))
    if verdict == "ALLOW" and status == "FLAGGED":
        verdict, rule, reason, severity = "FLAG", "status.flagged", "Agent is FLAGGED: action allowed but watched.", "LOW"
    elif verdict == "ALLOW" and status == "THROTTLED" and risky:
        verdict, rule, reason, severity = ("HOLD", "status.throttled_requires_approval",
                                           "Agent is THROTTLED: this kind of action needs human approval.", "MEDIUM")

    # 3. trust: apply each distinct penalty once (the status gate itself adds no penalty)
    score, new_status, seen = before, status, set()
    for f in findings:
        if f.penalty_key and f.penalty_key not in seen and f.rule not in ("status.quarantined", "status.halted"):
            seen.add(f.penalty_key)
            r = trust_mod.apply_penalty(score, f.penalty_key, policy, new_status, s)
            score, new_status = r.score, r.status
    if verdict == "HALT":
        new_status = "HALTED"
    elif verdict == "QUARANTINE" and new_status not in trust_mod.STICKY:
        new_status = "QUARANTINED"
        score = min(score, s.throttled_min - 1)
    elif new_status == "QUARANTINED" and status not in trust_mod.STICKY and VERDICT_RANK[verdict] < VERDICT_RANK["QUARANTINE"]:
        verdict = "QUARANTINE"        # this very penalty pushed the agent over the edge
        rule, reason = "trust.fell_below_quarantine", f"Trust fell to {score}, below {s.throttled_min}: the agent is now QUARANTINED. (Last issue: {reason})"
        severity = "HIGH" if SEVERITY_RANK[severity] < SEVERITY_RANK["HIGH"] else severity

    evidence = {"findings": [{"rule": f.rule, "verdict": f.verdict, **f.evidence} for f in findings][:6]}

    # 4. dry-run: say what WOULD have happened, change nothing
    if mode == "dry-run":
        if verdict == "ALLOW":
            return _decision(event, "ALLOW", rule, reason, severity, before, before, status, {"mode": "dry-run", **evidence})
        evidence.update({"mode": "dry-run", "would_verdict": verdict, "would_status": new_status})
        return _decision(event, "ALLOW", rule, f"DRY-RUN: would {verdict}. {reason}", severity, before, before, status, evidence)

    return _decision(event, verdict, rule, reason, severity, before, score, new_status, evidence)

# --- Pipeline helpers (M1 names, native M2 objects underneath) ---
def check_status(agent: dict):
    """(should_reject, response, reason) for pipeline step 1."""
    status = (agent or {}).get("status") or "HEALTHY"
    d = check_status_first(status, event=None, trust_score=(agent or {}).get("trust_score", 100) or 100)
    if d is None:
        return False, None, None
    return True, d.response, d.reason

def write_incident(*args, **kwargs):
    try:
        from engine.incidents import create as create_incident
        if args and hasattr(args[0], "verdict"):
            create_incident(args[0])
        elif len(args) >= 4:
            class _D: pass
            d = _D()
            d.agent_id, d.severity, d.reason, d.rule = args[0], args[1], args[2], args[3]
            d.verdict = getattr(args[0], "verdict", "BLOCK") if False else "BLOCK"
            d.event_id = kwargs.get("event_id", "unknown")
            create_incident(d)
    except Exception:
        pass

def apply_response_ladder(agent_id, verdict, response, agent, policy, reason=None, rule=None, event=None):
    """Apply penalty for a blocking verdict; returns (new_score, new_status)."""
    from engine.trust import apply_penalty, status_for_score
    score = (agent or {}).get("trust_score", 100) or 100
    key_map = {
        "BLOCK": "tool_not_allowed", "QUARANTINE": "honeytoken", "THROTTLE": "rate_exceeded",
        "HOLD": None, "FLAG": "drift_anomaly", "HALT": "sequence_violation", "ALLOW": None,
    }
    key = key_map.get(str(verdict), "constraint_violated")
    if key is None:
        return score, status_for_score(score, (agent or {}).get("status"))
    result = apply_penalty(score, key, policy)
    try:
        from gateway.db import db
        db.update_agent_trust(agent_id, result.score, result.status, result.reason)
    except Exception:
        pass
    return result.score, result.status

def check_sustained_rate_violations(agent_id, history=None):
    return False

def publish_trust_change(agent_id, before, after, reason=""):
    pass

def publish_status_change(agent_id, *args, **kwargs):
    pass
