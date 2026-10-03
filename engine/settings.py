# engine/settings.py
# Owner: M2
# Purpose: every number M2's code uses (thresholds, penalties, windows) in ONE place.
#
# WHY: the PRD says "nothing is hard-coded, all thresholds live in .env".
# M1's gateway/config.py will eventually load .env. Until then (and so our unit tests
# can run alone), we read the same names straight from environment variables and fall
# back to the PRD defaults. Reading happens at call time, so tests can change values.
import os
from dataclasses import dataclass, field
from typing import Dict, Tuple


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _list(name: str, default: str) -> Tuple[str, ...]:
    raw = os.environ.get(name, default)
    return tuple(x.strip() for x in raw.split(",") if x.strip())


@dataclass(frozen=True)
class M2Settings:
    # trust ladder (PRD section 10.1)
    trust_start: int = 100
    healthy_min: int = 70
    flagged_min: int = 40
    throttled_min: int = 20           # below this = QUARANTINED
    hysteresis: int = 5               # extra points needed to move UP a band
    recovery_per_min: float = 1.0
    # penalties (PRD section 10.2)
    penalties: Dict[str, int] = field(default_factory=lambda: {
        "tool_not_allowed": 40,
        "sequence_violation": 40,
        "constraint_violated": 25,
        "rate_exceeded": 15,
        "drift_anomaly": 10,
        "honeytoken": 70,             # "big drop in one step"
    })
    # recovery / probation (PRD section 10.3 and 10.5)
    resume_trust: int = 50            # a restored agent does NOT start at 100
    probation_clean_actions: int = 20 # open item #7: N
    probation_exit_trust: int = 80
    probation_limit_factor: float = 0.5
    # time windows (seconds)
    sequence_window_seconds: int = 600
    taint_window_seconds: int = 900
    # speed check: how many THROTTLED answers in the last minute before we HALT
    sustained_throttle_limit: int = 3
    # peers
    peer_min_trust: int = 30
    # leak filter + honeytokens
    allowed_email_domains: Tuple[str, ...] = ("novabank.test",)
    honeytoken_ids: Tuple[str, ...] = ("cust_honey_001", "cust_honey_002", "sk-honeytoken-do-not-use")


def get_settings() -> M2Settings:
    d = M2Settings()
    penalties = dict(d.penalties)
    for key in list(penalties):
        penalties[key] = _int("PENALTY_" + key.upper(), penalties[key])
    return M2Settings(
        trust_start=_int("TRUST_START", d.trust_start),
        healthy_min=_int("TRUST_HEALTHY_MIN", d.healthy_min),
        flagged_min=_int("TRUST_FLAGGED_MIN", d.flagged_min),
        throttled_min=_int("TRUST_THROTTLED_MIN", d.throttled_min),
        hysteresis=_int("TRUST_HYSTERESIS", d.hysteresis),
        recovery_per_min=_float("TRUST_RECOVERY_PER_MIN", d.recovery_per_min),
        penalties=penalties,
        resume_trust=_int("TRUST_RESUME", d.resume_trust),
        probation_clean_actions=_int("PROBATION_CLEAN_ACTIONS", d.probation_clean_actions),
        probation_exit_trust=_int("TRUST_PROBATION_EXIT", d.probation_exit_trust),
        probation_limit_factor=_float("PROBATION_LIMIT_FACTOR", d.probation_limit_factor),
        sequence_window_seconds=_int("SEQUENCE_WINDOW_SECONDS", d.sequence_window_seconds),
        taint_window_seconds=_int("TAINT_WINDOW_SECONDS", d.taint_window_seconds),
        sustained_throttle_limit=_int("SUSTAINED_THROTTLE_LIMIT", d.sustained_throttle_limit),
        peer_min_trust=_int("PEER_MIN_TRUST", d.peer_min_trust),
        allowed_email_domains=_list("ALLOWED_EMAIL_DOMAINS", ",".join(d.allowed_email_domains)),
        honeytoken_ids=_list("HONEYTOKEN_IDS", ",".join(d.honeytoken_ids)),
    )
