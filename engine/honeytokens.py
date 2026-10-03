# engine/honeytokens.py
# Owner: M2   (Phase 4-5)
# Purpose: bait records / keys. No real task ever needs them, so touching one is an
# instant CRITICAL alarm with almost no false alarms (differentiator #2).
#
# WHY it is so valuable: normal rules ask "is this action too big / in the wrong order?".
# A honeytoken asks nothing fuzzy: "did you touch something you had no reason to touch?"
# Yes or no. That is why judges like it and why it never needs tuning.
#
# The bait list comes from HONEYTOKEN_IDS in .env. M1 must put matching fake rows in the
# mock customer data (tools.py) and make sure NO normal scenario ever reads them.
from typing import Optional

from engine._util import get, walk_strings
from engine.findings import Finding
from engine.settings import M2Settings, get_settings


def find_honeytoken(args, settings: Optional[M2Settings] = None) -> Optional[str]:
    """Return the bait string that was touched, or None. Case-insensitive, and it also
    catches a bait id hidden inside a longer string (e.g. 'customer cust_honey_001')."""
    s = settings or get_settings()
    baits = [b.lower() for b in s.honeytoken_ids]
    for text in walk_strings(args):
        low = text.lower()
        for bait in baits:
            if bait in low:
                return bait
    return None


def is_honeytoken(args, settings: Optional[M2Settings] = None) -> bool:
    return find_honeytoken(args, settings) is not None


def check_honeytokens(event, settings: Optional[M2Settings] = None) -> Optional[Finding]:
    bait = find_honeytoken(get(event, "args", {}), settings)
    if bait is None:
        return None
    return Finding(
        "BLOCK", "honeytoken.touched",
        "The agent touched a bait record that no real task needs. This is treated as a critical event.",
        "CRITICAL", penalty_key="honeytoken", critical=True,
        evidence={"bait": bait, "tool": get(event, "tool")},
    )
