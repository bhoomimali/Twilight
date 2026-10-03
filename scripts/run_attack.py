#!/usr/bin/env python3
"""
Real attack path (not a fake print-only demo):

  1. Talker and/or Poisoner *generate* messages (attackers/*.py)
  2. SupportBot *decides* issue_refund from that text (agents/support_flow.py)
  3. Gateway policy *judges* the tool call (engine.policy) — or live /action if --live

Usage (from twilight/ with venv):
  python scripts/run_attack.py --mode on --attacker both
  python scripts/run_attack.py --mode off --attacker talker
  python scripts/run_attack.py --mode on --attacker poisoner
  python scripts/run_attack.py --mode on --attacker both --live
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from attackers.talker import craft_refund_plea, say as talker_say
from attackers.poisoner import poison_ticket, say as poisoner_say
from agents.support_flow import decide_from_message, say_reading, say_action

try:
    from gateway import logger as glog
except Exception:
    glog = None


def judge_local(event: dict, mode: str) -> dict:
    """Use real policy engine when mode=on; mode=off skips checks."""
    if mode == "off":
        return {
            "verdict": "ALLOW",
            "reason": "Guard is OFF: no checks were run.",
            "rule": "mode.off",
            "trust_before": 100,
            "trust_after": 100,
        }

    # Load SupportBot policy YAML if present
    try:
        from engine.policy import check_policy, load_policy

        policy_path = ROOT / "policies" / "supportbot.yaml"
        if policy_path.exists():
            policy = load_policy(str(policy_path))
        else:
            policy = {
                "agent_id": "supportbot",
                "tools": {
                    "issue_refund": {
                        "allowed": True,
                        "constraints": {"max_amount": 500},
                    }
                },
            }
        finding = check_policy(event, policy, history=[])
        verdict = getattr(finding, "verdict", None) or finding.get("verdict")
        reason = getattr(finding, "reason", None) or finding.get("reason") or ""
        rule = getattr(finding, "rule", None) or finding.get("rule")
        return {
            "verdict": str(verdict),
            "reason": str(reason),
            "rule": str(rule) if rule else None,
            "trust_before": 96,
            "trust_after": 75 if str(verdict).upper() in ("BLOCK", "HOLD", "QUARANTINE", "HALT") else 96,
        }
    except Exception as exc:
        # Fallback mirror of PRD limit so demo always works
        amount = float(event.get("args", {}).get("amount") or 0)
        if amount > 500:
            return {
                "verdict": "BLOCK",
                "reason": f"issue_refund amount {amount} exceeds limit 500 ({exc.__class__.__name__})",
                "rule": "constraints.issue_refund.max_amount",
                "trust_before": 96,
                "trust_after": 75,
            }
        return {
            "verdict": "ALLOW",
            "reason": "within limit",
            "rule": "allow.clean",
            "trust_before": 96,
            "trust_after": 96,
        }


def resolve_mode(mode: str, gateway_url: str) -> str:
    """--mode auto reads whatever the dashboard toggle set on the gateway."""
    if mode != "auto":
        return mode
    try:
        import httpx

        return httpx.get(f"{gateway_url}/mode", timeout=3.0).json().get("mode", "on")
    except Exception:
        return "on"


def judge_live(event: dict, mode: str, gateway_url: str, explicit_mode: bool = False) -> dict:
    """POST to running gateway (signed, like a real agent would)."""
    import os

    import httpx

    from gateway.signing import sign_event

    if explicit_mode:  # only force the mode when the user typed --mode on/off
        try:
            httpx.post(f"{gateway_url}/mode", json={"mode": mode}, timeout=5.0)
        except Exception:
            pass
    event = sign_event(event, event.get("agent_id"))
    headers = {"X-API-Key": os.getenv("TWILIGHT_API_KEY", "change-me")}
    r = httpx.post(f"{gateway_url}/action", json=event, headers=headers, timeout=30.0)
    r.raise_for_status()
    data = r.json()
    return {
        "verdict": data.get("verdict") or data.get("response"),
        "reason": data.get("reason", ""),
        "rule": data.get("rule"),
        "trust_before": data.get("trust_before"),
        "trust_after": data.get("trust_after"),
    }


def run(attacker: str, mode: str, live: bool, gateway_url: str, amount: float):
    explicit_mode = mode != "auto"
    mode = resolve_mode(mode, gateway_url)
    if glog:
        glog.banner(f"RUN ATTACK · mode={mode.upper()} · attacker={attacker}")
    else:
        print(f"\n=== RUN ATTACK · mode={mode} · attacker={attacker} ===\n")

    messages = []

    if attacker in ("talker", "both"):
        msg = craft_refund_plea(amount=amount, ticket_id="T-9000", customer_id="TB-4471")
        print("\033[95m" + talker_say(msg) + "\033[0m")
        messages.append(msg)

    if attacker in ("poisoner", "both"):
        msg = poison_ticket(ticket_id="T-812", amount=amount, customer_id="TB-4471")
        print("\033[91m" + poisoner_say(msg) + "\033[0m")
        messages.append(msg)

    if not messages:
        print("No attacker selected.")
        return

    # SupportBot reacts to the *last* planted message (poisoner overrides if both)
    target = messages[-1]
    print("\033[96m" + say_reading(target) + "\033[0m")
    event = decide_from_message(target, agent_id="supportbot")
    print("\033[96m" + say_action(event) + "\033[0m")

    if live:
        decision = judge_live(event, mode, gateway_url, explicit_mode)
        source = "gateway /action"
    else:
        decision = judge_local(event, mode)
        source = "local policy"

    verdict = str(decision.get("verdict", "?")).upper()
    reason = decision.get("reason") or ""
    rule = decision.get("rule") or ""

    if glog:
        if verdict in ("BLOCK", "QUARANTINE", "HALT"):
            glog.fail(f"{verdict}: {reason}")
        elif verdict in ("HOLD", "THROTTLE", "FLAG"):
            glog.warn(f"{verdict}: {reason}")
        else:
            glog.ok(f"{verdict}: {reason}")
        glog.verdict_box(
            verdict,
            reason or rule or source,
            decision.get("trust_before"),
            decision.get("trust_after"),
            3.0,
        )
    else:
        print(f"  [{source}] VERDICT={verdict}  {reason}  rule={rule}")

    if mode == "off" or verdict in ("ALLOW", "FLAG"):
        print("\033[91m  [ledger]\033[0m  would move / moved funds (guard off or allowed)")
    else:
        print("\033[92m  [ledger]\033[0m  balance unchanged — Twilight stopped the call")

    # Machine-readable trail for UI later
    trail = {
        "attacker": attacker,
        "mode": mode,
        "messages": messages,
        "event": event,
        "decision": decision,
        "source": source,
    }
    out = ROOT / "data" / "last_attack.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(trail, indent=2), encoding="utf-8")
    print(f"\n  wrote {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["off", "on", "auto"], default="auto",
                    help="auto = follow the dashboard toggle (default)")
    ap.add_argument("--attacker", choices=["talker", "poisoner", "both"], default="both")
    ap.add_argument("--amount", type=float, default=9000.0)
    ap.add_argument("--live", action="store_true", help="POST to running gateway")
    ap.add_argument("--gateway", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    run(args.attacker, args.mode, args.live, args.gateway, args.amount)


if __name__ == "__main__":
    main()
