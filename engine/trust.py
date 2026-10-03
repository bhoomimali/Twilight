# engine/trust.py
# Owner: M2   (Phase 3, recovery + probation in Phase 6)
# Purpose: the trust SCORE and what it means. Pure functions, no database, easy to unit test.
#
#   score 70-100 HEALTHY | 40-70 FLAGGED | 20-40 THROTTLED | below 20 QUARANTINED
#   HALTED = manual / critical only
#
# Interfaces for M1 (pipeline steps 8-9):
#     apply_penalty(score, reason, policy=None, current_status=None)  -> TrustResult
#     recover_clean_agent(score, minutes_clean, current_status=None, probation=None) -> TrustResult
#     status_for_score(score, current_status=None)                    -> status string
#     start_probation() / record_clean_action(...)                    -> for D8 recovery
from dataclasses import dataclass, replace
from typing import Optional, Tuple

from engine.settings import M2Settings, get_settings

# worst -> best. HALTED is separate: it is a manual state, not a score band.
_RANK = {"QUARANTINED": 0, "THROTTLED": 1, "FLAGGED": 2, "HEALTHY": 3}
STICKY = ("QUARANTINED", "HALTED")   # the score alone can never release these


@dataclass(frozen=True)
class TrustResult:
    score: int
    status: str
    delta: int = 0
    critical: bool = False
    note: str = ""


@dataclass(frozen=True)
class Probation:
    required: int
    clean_actions: int = 0

    @property
    def active(self) -> bool:
        return self.clean_actions < self.required


def _band(score: int, s: M2Settings, margin: int = 0) -> str:
    if score >= s.healthy_min + margin:
        return "HEALTHY"
    if score >= s.flagged_min + margin:
        return "FLAGGED"
    if score >= s.throttled_min + margin:
        return "THROTTLED"
    return "QUARANTINED"


def status_for_score(score: int, current_status: Optional[str] = None, settings: Optional[M2Settings] = None) -> str:
    """Going DOWN is immediate. Going UP needs `hysteresis` extra points.
    WHY: an agent sitting at 69-71 would otherwise flip HEALTHY<->FLAGGED every few seconds."""
    s = settings or get_settings()
    if current_status in STICKY:
        return current_status
    down = _band(score, s, 0)
    if current_status is None:
        return down
    if _RANK[down] <= _RANK[current_status]:
        return down                         # same or worse: take it immediately
    up = _band(score, s, s.hysteresis)      # better: only if we cleared the margin
    return up if _RANK[up] > _RANK[current_status] else current_status


def penalty_for(reason: str, policy: Optional[dict] = None, settings: Optional[M2Settings] = None) -> int:
    s = settings or get_settings()
    table = dict(s.penalties)
    table.update((policy or {}).get("penalties") or {})   # a contract may override numbers
    if reason not in table:
        raise ValueError(f"unknown penalty reason: {reason!r}")   # never invent synonyms
    return int(table[reason])


def apply_penalty(score: int, reason: str, policy: Optional[dict] = None,
                  current_status: Optional[str] = None, settings: Optional[M2Settings] = None) -> TrustResult:
    s = settings or get_settings()
    if reason == "config_mismatch":
        # Critical override: quarantine NOW, whatever the score was (PRD 10.2).
        new = min(score, s.throttled_min - 1)
        status = current_status if current_status == "HALTED" else "QUARANTINED"
        return TrustResult(new, status, new - score, True, "config hash mismatch")
    p = penalty_for(reason, policy, s)
    new = max(0, score - p)
    return TrustResult(new, status_for_score(new, current_status, s), new - score, reason == "honeytoken", reason)


def recover_clean_agent(score: int, minutes_clean: float, current_status: Optional[str] = None,
                        probation: Optional[Probation] = None, settings: Optional[M2Settings] = None) -> TrustResult:
    """+recovery_per_min for each WHOLE minute of clean behaviour (caller keeps the leftover seconds).
    While on probation the score is capped below HEALTHY: trust must be earned with real clean actions."""
    s = settings or get_settings()
    if current_status in STICKY:
        return TrustResult(score, current_status, 0, False, "needs admin resume/restore")
    gain = int(max(0.0, minutes_clean) * s.recovery_per_min)
    cap = 100
    if probation is not None and probation.active:
        cap = s.healthy_min - 1
    new = score if score >= cap else min(score + gain, cap)
    return TrustResult(new, status_for_score(new, current_status, s), new - score, False, "clean-time recovery")


def start_probation(settings: Optional[M2Settings] = None) -> Tuple[TrustResult, Probation]:
    """Called when an admin restores/resumes an agent (D8). It starts at reduced trust, not 100."""
    s = settings or get_settings()
    result = TrustResult(s.resume_trust, status_for_score(s.resume_trust, None, s), 0, False, "resumed on probation")
    return result, Probation(required=s.probation_clean_actions)


def record_clean_action(probation: Probation, score: int, current_status: str,
                        settings: Optional[M2Settings] = None) -> Tuple[Probation, TrustResult]:
    """Count one clean executed action. When the count reaches N, probation ends and trust is lifted."""
    s = settings or get_settings()
    if not probation.active:
        return probation, TrustResult(score, current_status)
    probation = replace(probation, clean_actions=probation.clean_actions + 1)
    if probation.active:
        return probation, TrustResult(score, current_status, 0, False, "probation continues")
    new = max(score, s.probation_exit_trust)
    return probation, TrustResult(new, status_for_score(new, current_status, s), new - score, False, "probation finished")


def probation_limits_factor(probation: Optional[Probation], settings: Optional[M2Settings] = None) -> float:
    """Amount limits (max_amount) are tightened (x0.5 by default) while on probation."""
    s = settings or get_settings()
    return s.probation_limit_factor if probation is not None and probation.active else 1.0

def apply_trust_update(agent_id: str, new_score: int, new_status, reason: str = "") -> None:
    """Persist score+status for pipeline. No-op in pure unit tests."""
    try:
        from gateway.db import db
        db.update_agent_trust(agent_id, int(new_score), str(new_status), reason)
    except Exception:
        pass
