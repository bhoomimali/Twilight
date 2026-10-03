# engine/findings.py
# Owner: M2
# Purpose: the small "result" object every M2 check returns, plus the allowed values.
#
# WHY a Finding and not a full Decision?
#   A full Decision (PRD 9.3) needs trust_before / trust_after / status. At pipeline step 4
#   (policy) we do not know those yet. So each check returns a Finding ("I saw X, I suggest
#   verdict Y"). enforcer.decide() then combines all Findings into ONE final Decision.
#   Finding has the same core fields as Decision (verdict, rule, reason, severity, evidence),
#   so M1 can treat it as a "Decision-shaped" result.
#
# Unknown values are rejected on purpose (decision rule: never invent synonyms).
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

# Order here = how strong the answer is. Stronger wins when several checks fire.
VERDICT_ORDER = ("ALLOW", "FLAG", "THROTTLE", "HOLD", "BLOCK", "QUARANTINE", "HALT")
VERDICT_RANK = {v: i for i, v in enumerate(VERDICT_ORDER)}
SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}
STATUSES = ("HEALTHY", "FLAGGED", "THROTTLED", "QUARANTINED", "HALTED")
MODES = ("off", "dry-run", "on")

# What /action tells the agent (PRD 9.1)
RESPONSE_FOR_VERDICT = {
    "ALLOW": "allow",
    "FLAG": "allow",        # runs, but the dashboard shows a yellow alert
    "HOLD": "held",
    "THROTTLE": "throttled",
    "BLOCK": "blocked",
    "QUARANTINE": "blocked",
    "HALT": "halted",
}

# Tools that send something to another agent or to the outside world
MESSAGE_TOOLS = ("send_message", "send_email")


@dataclass
class Finding:
    verdict: str                       # suggested verdict
    rule: str                          # id like constraints.issue_refund.max_amount
    reason: str                        # plain-language sentence
    severity: str = "MEDIUM"
    penalty_key: Optional[str] = None  # key into the penalty table (None = no penalty)
    critical: bool = False             # critical override (e.g. config mismatch)
    evidence: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.verdict not in VERDICT_RANK:
            raise ValueError(f"unknown verdict: {self.verdict!r}")
        if self.severity not in SEVERITY_RANK:
            raise ValueError(f"unknown severity: {self.severity!r}")
        if not self.rule or not self.reason:
            raise ValueError("every Finding needs a non-empty rule and reason (FR10)")


def allow_finding() -> Finding:
    return Finding("ALLOW", "allow.clean", "No rule matched, action allowed.", "LOW")


def worst(findings: Iterable[Finding]) -> Finding:
    """Strongest verdict wins; if tied, higher severity wins; if still tied, first one."""
    best = None
    for f in findings:
        key = (VERDICT_RANK[f.verdict], SEVERITY_RANK[f.severity])
        if best is None or key > best[0]:
            best = (key, f)
    return best[1] if best else allow_finding()


def from_config_mismatch(expected: str, actual: str) -> Finding:
    """M3 tells us the config hash did not match. We turn it into the critical override.
    Called by gateway/pipeline.py at step 3 (PRD: 'instant QUARANTINE, regardless of score')."""
    return Finding(
        "QUARANTINE", "attestation.config_mismatch",
        "The agent's configuration no longer matches its signed manifest, so it was quarantined.",
        "CRITICAL", penalty_key="config_mismatch", critical=True,
        evidence={"expected_hash": expected, "actual_hash": actual},
    )
