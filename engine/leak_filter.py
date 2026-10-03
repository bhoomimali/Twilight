# engine/leak_filter.py
# Owner: M2   (Phase 4-5)
# Purpose: stop data from LEAVING, even when the tool itself was allowed.
# It looks for: card-like numbers, email addresses outside our domain, and key-like secrets.
#
# WHY: contracts say "who may do what". A leak is "an allowed tool carrying forbidden
# content". Example: Coordinator is allowed to send_message, but not with a card number inside.
#
# PRIVACY RULE (PRD 23.4): we never put the leaked value into evidence. Cards are masked
# (last 4 only), emails keep only the domain, secrets keep only a short prefix + length.
# Otherwise the log we use to prove safety would itself contain the leak.
import math
import re
from collections import Counter
from typing import List, Optional

from engine._util import get, walk_strings
from engine.findings import MESSAGE_TOOLS, Finding
from engine.settings import M2Settings, get_settings

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
KEY_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
LONG_TOKEN_RE = re.compile(r"[A-Za-z0-9+/_=-]{40,}")


def luhn_ok(number: str) -> bool:
    """Luhn check: real card numbers pass it, random digit strings mostly do not."""
    digits = [int(c) for c in number if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total, double = 0, False
    for d in reversed(digits):
        if double:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        double = not double
    return total % 10 == 0


def _entropy(text: str) -> float:
    counts = Counter(text)
    n = len(text)
    return -sum(c / n * math.log2(c / n) for c in counts.values())


def _domain_allowed(domain: str, allowed) -> bool:
    d = domain.lower()
    return any(d == a.lower() or d.endswith("." + a.lower()) for a in allowed)


def scan_text(text: str, allowed_domains=("novabank.test",), categories=("cards", "emails", "secrets")) -> List[dict]:
    """Return a list of hits (already redacted). Empty list = clean."""
    hits: List[dict] = []
    if "cards" in categories:
        for m in CARD_RE.finditer(text):
            if luhn_ok(m.group()):
                digits = re.sub(r"\D", "", m.group())
                hits.append({"kind": "card_number", "masked": "*" * (len(digits) - 4) + digits[-4:]})
    if "secrets" in categories:
        for pat in KEY_PATTERNS:
            for m in pat.finditer(text):
                hits.append({"kind": "secret_key", "prefix": m.group()[:4] + "...", "length": len(m.group())})
        for m in LONG_TOKEN_RE.finditer(text):
            token = m.group()
            if _entropy(token) >= 4.2 and not any(h["kind"] == "secret_key" for h in hits):
                hits.append({"kind": "secret_key", "prefix": token[:4] + "...", "length": len(token)})
    if "emails" in categories:
        for m in EMAIL_RE.finditer(text):
            domain = m.group(1)
            if not _domain_allowed(domain, allowed_domains):
                hits.append({"kind": "outside_email", "domain": domain.lower()})
    return hits


def find_outside_emails(args, allowed_domains) -> List[str]:
    """Helper for sequence rules: domains of any outside email found inside args."""
    out = []
    for text in walk_strings(args):
        out += [h["domain"] for h in scan_text(text, allowed_domains, ("emails",))]
    return out


_PRIORITY = {"card_number": 0, "secret_key": 1, "outside_email": 2}
_CATEGORY_NAMES = {"card_numbers": "cards", "outside_addresses": "emails"}


def check_leak(event, policy: Optional[dict], settings: Optional[M2Settings] = None) -> Optional[Finding]:
    """Scan outgoing content. Runs on messaging tools, and on any tool whose contract has a `scan:` list.
    We scan only outbound tools on purpose: scanning every argument of every tool would create
    false alarms (e.g. a 16-digit ticket number that happens to pass Luhn)."""
    s = settings or get_settings()
    tool = get(event, "tool")
    constraint = ((policy or {}).get("constraints") or {}).get(tool) or {}
    scan_list = constraint.get("scan")
    if tool not in MESSAGE_TOOLS and not scan_list:
        return None
    if scan_list:
        categories = {"secrets"} | {_CATEGORY_NAMES[c] for c in scan_list if c in _CATEGORY_NAMES}
    else:
        categories = {"cards", "emails", "secrets"}
    allowed = tuple(s.allowed_email_domains) + tuple((policy or {}).get("allowed_email_domains") or ())
    hits: List[dict] = []
    for text in walk_strings(get(event, "args", {})):
        hits += scan_text(text, allowed, tuple(categories))
    if not hits:
        return None
    hits.sort(key=lambda h: _PRIORITY[h["kind"]])
    first = hits[0]["kind"]
    nice = {"card_number": "a card-like number", "secret_key": "a key or secret", "outside_email": "an outside email address"}[first]
    return Finding(
        "BLOCK", f"leak_filter.{first}",
        f"The outgoing message contains {nice}, so it was stopped before leaving.",
        "HIGH", penalty_key="constraint_violated", evidence={"hits": hits[:5], "tool": tool},
    )
