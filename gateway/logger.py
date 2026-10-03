"""Hardcoded terminal logger for demo visibility (M4 request)."""
import sys
from datetime import datetime

# ANSI colors
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
MAGENTA= "\033[95m"
BLUE   = "\033[94m"
WHITE  = "\033[97m"

def _ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def banner(msg: str):
    line = "─" * 62
    print(f"\n{CYAN}{BOLD}{line}{RESET}")
    print(f"{CYAN}{BOLD}  GATEWAY  │  {msg}{RESET}")
    print(f"{CYAN}{BOLD}{line}{RESET}")

def step(num: int, title: str, detail: str = ""):
    print(f"{BLUE}{BOLD}  [{num:02d}]{RESET} {WHITE}{title}{RESET}  {DIM}{detail}{RESET}")

def ok(msg: str):
    print(f"       {GREEN}✓ {msg}{RESET}")

def warn(msg: str):
    print(f"       {YELLOW}⚠ {msg}{RESET}")

def fail(msg: str):
    print(f"       {RED}✗ {msg}{RESET}")

def verdict_box(verdict: str, reason: str, trust_before, trust_after, latency_ms):
    color = GREEN
    v = str(verdict).upper()
    if v in ("BLOCK", "QUARANTINE", "HALT"):
        color = RED
    elif v in ("HOLD", "THROTTLE", "FLAG"):
        color = YELLOW

    print(f"\n{color}{BOLD}  ┌─────────────────────────────────────────────────────────┐{RESET}")
    print(f"{color}{BOLD}  │  VERDICT: {v:<12}                                 │{RESET}")
    print(f"{color}{BOLD}  │  Reason : {reason[:45]:<45} │{RESET}")
    tb = trust_before if trust_before is not None else "?"
    ta = trust_after if trust_after is not None else "?"
    print(f"{color}{BOLD}  │  Trust  : {tb} → {ta:<40} │{RESET}")
    print(f"{color}{BOLD}  │  Latency: {latency_ms or 0:.1f} ms{' '*(42)}│{RESET}")
    print(f"{color}{BOLD}  └─────────────────────────────────────────────────────────┘{RESET}\n")
    sys.stdout.flush()

def agent_action(agent_id: str, tool: str, args: dict):
    print(f"{MAGENTA}{BOLD}  ▶ AGENT {agent_id} wants: {tool}({args}){RESET}")
