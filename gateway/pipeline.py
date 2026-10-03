"""
Decision pipeline for Twilight Gateway.
Orchestrates steps 1-4, 6-9, 10-12 with fail-closed wrapper.
"""
import time
import threading
from datetime import datetime, timezone
from typing import Dict, Any
from gateway.schemas import Verdict, AgentStatus, Decision, Severity
from gateway.db import db
from gateway.config import settings
from engine.attestation import verify_signature, check_nonce_and_timestamp, verify_config_hash, insert_nonce
from engine.policy import check_policy, get_recent_history
from engine.trust import apply_penalty, status_for_score, apply_trust_update
from engine.enforcer import (
    check_status, decide, check_sustained_rate_violations,
    apply_response_ladder, write_incident, publish_trust_change, publish_status_change
)
from gateway.tools import execute_tool
from audit.chain import append_record
from gateway.websocket import manager
from gateway import logger as glog


# Lock for serializing decisions to ensure audit seq consistency
decision_lock = threading.Lock()


def run_pipeline(event: Dict[str, Any], api_key: str, runtime_mode: str = "on") -> Decision:
    """
    Run the decision pipeline for an event.
    Steps 1-4 and 10-12 with fail-closed wrapper.
    
    runtime_mode: "off" (no checks, action still executes — PRD), "dry-run" (checks run, tool not executed, would_* in evidence), "on" (full enforcement)
    """
    start_time = time.perf_counter()

    # ── DEMO TERMINAL LOGGING (hardcoded for visibility) ──
    agent_id = event.get("agent_id", "?")
    tool = event.get("tool", "?")
    args = event.get("args", {})
    glog.banner(f"{agent_id} → {tool}")
    glog.agent_action(agent_id, tool, args)
    glog.step(0, "Runtime mode", runtime_mode)
    
    # Initialize decision
    decision = Decision(
        verdict="BLOCK",
        response="blocked",
        reason="",
        rule=None,
        severity=None,
        trust_before=None,
        trust_after=None,
        status=None,
        evidence={},
        latency_ms=None
    )
    
    try:
        # PRD mode semantics: off = no checks, action still executes
        if runtime_mode == "off":
            decision.verdict = "ALLOW"
            decision.response = "allow"
            decision.reason = "Guard is OFF: no checks were run."
            decision.rule = "mode.off"
            decision.evidence = {"mode": "off"}
            try:
                tool = event.get("tool")
                tool_result = execute_tool(tool, event.get("args", {}), event.get("event_id"), api_key)
                decision.evidence["tool_result"] = tool_result.get("redacted_args") if isinstance(tool_result, dict) else tool_result
            except Exception as exc:
                decision.evidence["tool_error"] = str(exc)
            decision.latency_ms = (time.perf_counter() - start_time) * 1000
            glog.ok("MODE=OFF → auto ALLOW (no checks)")
            glog.verdict_box(decision.verdict, decision.reason, None, None, decision.latency_ms)
            return decision

        with decision_lock:
            # Step 1: Status check (reject QUARANTINED/HALTED first)
            glog.step(1, "Status check")
            agent = db.get_agent(event.get("agent_id"))
            if not agent:
                decision.reason = "Agent not registered"
                decision.rule = "registration.unknown_agent"
                decision.response = "blocked"
                decision.verdict = Verdict.BLOCK
                glog.fail("Agent not registered")
                return decision
            
            agent_status = agent["status"]
            if agent_status in ["QUARANTINED", "HALTED"]:
                decision.reason = f"Agent is {agent_status}"
                decision.rule = f"status.{agent_status.lower()}"
                decision.response = "halted" if agent_status == "HALTED" else "blocked"
                decision.verdict = Verdict.BLOCK
                decision.status = AgentStatus(agent_status)
                decision.trust_before = agent["trust_score"]
                decision.trust_after = agent["trust_score"]
                glog.fail(f"Agent is {agent_status}")
                return decision
            
            decision.trust_before = agent["trust_score"]
            decision.status = AgentStatus(agent_status)
            glog.ok(f"status={agent_status}  trust={agent['trust_score']}")
            
            # Step 2: Signature and replay
            glog.step(2, "Signature + nonce / replay check")
            is_valid_sig, sig_error = verify_signature(event, agent["public_key"])
            if not is_valid_sig:
                decision.reason = sig_error
                decision.rule = "attestation.signature"
                decision.response = "blocked"
                decision.verdict = Verdict.BLOCK
                glog.fail(f"Bad signature: {sig_error}")
                return decision
            glog.ok("signature valid")
            
            is_valid_nonce, nonce_error = check_nonce_and_timestamp(event)
            if not is_valid_nonce:
                decision.reason = nonce_error
                decision.rule = "attestation.replay" if "replay" in nonce_error else "attestation.timestamp"
                decision.response = "blocked"
                decision.verdict = Verdict.BLOCK
                glog.fail(f"Replay/timestamp: {nonce_error}")
                return decision
            glog.ok("nonce + timestamp OK")
            
            # Insert nonce (atomically with decision)
            insert_nonce(event)
            
            # Step 3: Attestation (config hash vs manifest)
            glog.step(3, "Config-hash attestation")
            is_valid_hash, hash_error, computed_hash = verify_config_hash(event["agent_id"])
            if not is_valid_hash:
                # Mismatch: set QUARANTINED immediately, CRITICAL severity
                db.update_agent_status(event["agent_id"], "QUARANTINED")
                decision.reason = hash_error
                decision.rule = "attestation.config_hash_mismatch"
                decision.response = "blocked"
                decision.verdict = Verdict.QUARANTINE
                glog.fail(f"CONFIG HASH MISMATCH → QUARANTINE: {hash_error}")
                decision.severity = Severity.CRITICAL
                decision.status = AgentStatus.QUARANTINED
                decision.trust_after = agent["trust_score"]  # Trust unchanged (critical override)
                decision.evidence = {"computed_hash": computed_hash}
                
                # Create incident
                from gateway.schemas import Incident
                incident = Incident(
                    agent_id=event["agent_id"],
                    severity="CRITICAL",
                    summary=f"Config hash mismatch: {hash_error}"
                )
                db.insert_incident(incident.model_dump())
                write_incident(event["agent_id"], "CRITICAL", f"Config hash mismatch: {hash_error}", "attestation.config_hash_mismatch")
                
                return decision
            glog.ok("config hash matches")
            
            # Step 4: Full policy check
            policy = load_agent_policy(event["agent_id"])
            if not policy:
                decision.reason = "Policy not found for agent"
                decision.rule = "policy.missing"
                decision.response = "blocked"
                decision.verdict = Verdict.BLOCK
                return decision
            
            tool = event.get("tool")
            history = get_recent_history(event["agent_id"])
            registry = None
            try:
                agents = db.list_agents() if hasattr(db, "list_agents") else []
                if not agents and hasattr(db, "get_all_agents"):
                    agents = db.get_all_agents()
                registry = {a["agent_id"]: a for a in (agents or [])}
            except Exception:
                registry = None
            try:
                finding = check_policy(event, policy, history, registry=registry)
            except TypeError:
                finding = check_policy(event, policy, history)
            # finding is a Finding (verdict, rule, reason, severity, penalty_key, ...)
            findings = [finding] if finding is not None else []

            # Step 5: Drift (W2 / M3) — best-effort; NEVER overwrite a stronger policy finding
            try:
                from engine import drift as drift_mod
                if hasattr(drift_mod, "check_drift"):
                    df = drift_mod.check_drift(event, history)
                    if df is not None and getattr(df, "verdict", "ALLOW") != "ALLOW":
                        findings.append(df)
            except Exception:
                pass

            # Step 6: Decide via M2 enforcer (worst finding wins)
            mode = runtime_mode if runtime_mode in ("off", "dry-run", "on") else "on"
            status = agent.get("status") or "HEALTHY"
            trust_score = agent.get("trust_score", 100) or 100

            final = decide(
                findings,
                mode,
                status,
                trust_score=trust_score,
                event=event,
                policy=policy,
            )
            # final is a Decision from M2 enforcer
            decision.verdict = final.verdict
            decision.response = final.response
            decision.reason = final.reason
            decision.rule = final.rule
            decision.severity = final.severity
            decision.evidence = dict(final.evidence or {})
            decision.evidence["policy_finding"] = {
                "verdict": getattr(finding, "verdict", None),
                "rule": getattr(finding, "rule", None),
                "reason": getattr(finding, "reason", None),
            }
            if len(findings) > 1:
                decision.evidence["drift_finding"] = {
                    "verdict": getattr(findings[-1], "verdict", None),
                    "rule": getattr(findings[-1], "rule", None),
                    "reason": getattr(findings[-1], "reason", None),
                }
            decision.trust_before = final.trust_before if final.trust_before is not None else trust_score
            decision.trust_after = final.trust_after if final.trust_after is not None else trust_score
            decision.status = final.status or status

            # Persist trust if score changed and mode is on
            if mode == "on" and decision.trust_after is not None and decision.trust_after != trust_score:
                apply_trust_update(
                    event["agent_id"],
                    int(decision.trust_after),
                    decision.status,
                    decision.reason or "",
                )
                publish_trust_change(event["agent_id"], trust_score, decision.trust_after, decision.reason or "")

            # Early exit for hard rejects (same as old path, but using Finding)
            if finding.verdict in ("BLOCK", "QUARANTINE", "HALT") and mode == "on":
                if decision.severity:
                    sev = decision.severity.value if hasattr(decision.severity, "value") else str(decision.severity)
                    write_incident(event["agent_id"], sev, decision.reason, decision.rule)
                return decision

            verdict = decision.verdict
            response = decision.response
            
            # Check for sustained rate violations (THROTTLE -> HALT)
            if response == "throttled" and check_sustained_rate_violations(event["agent_id"]):
                decision.verdict = Verdict.BLOCK
                decision.response = "halted"
                decision.reason = "Sustained rate violations - agent halted"
                decision.rule = "rate.sustained_violations"
                decision.status = AgentStatus.HALTED
                apply_trust_update(event["agent_id"], agent["trust_score"], AgentStatus.HALTED, decision.reason)
                write_incident(event["agent_id"], "CRITICAL", decision.reason, decision.rule)
                publish_status_change(event["agent_id"], agent["status"], "HALTED", decision.reason)
                return decision
            
            # Normalize verdict to string for comparisons
            vstr = verdict.value if hasattr(verdict, "value") else str(verdict)

            # Step 7: HOLD queue
            if vstr == "HOLD":
                import json
                db.insert_held_action(
                    event.get("event_id"),
                    event["agent_id"],
                    json.dumps(event)
                )
                # reason/rule already set from enforcer
                decision.trust_after = decision.trust_after if decision.trust_after is not None else agent["trust_score"]
                decision.status = decision.status or agent["status"]
                return decision
            
            # Step 8: Trust already applied inside enforcer.decide for penalties
            if vstr in ("ALLOW", "FLAG"):
                if decision.trust_after is None:
                    decision.trust_after = agent["trust_score"]
                if decision.status is None:
                    decision.status = agent["status"]
            
            # Step 9: Response ladder only if enforcer did not already move trust
            if vstr == "BLOCK" and (decision.trust_after is None or decision.trust_after == agent.get("trust_score")):
                new_score, new_status = apply_response_ladder(
                    event["agent_id"], vstr, response, agent, policy,
                    decision.reason, decision.rule
                )
                decision.trust_after = new_score
                decision.status = new_status
            
            # Step 10: Execute tool (only ALLOW/FLAG)
            if vstr in ("ALLOW", "FLAG"):
                if runtime_mode == "dry-run":
                    # Dry-run: checks already ran; do NOT execute tool. Keep would_* from enforcer.
                    if not isinstance(decision.evidence, dict):
                        decision.evidence = {}
                    decision.evidence.update({
                        "dry_run": True,
                        "tool": tool,
                        "args": event.get("args", {}),
                    })
                else:
                    # Normal mode: execute tool
                    tool_result = execute_tool(tool, event.get("args", {}), event.get("event_id"), api_key)
                    if not tool_result["success"]:
                        decision.verdict = Verdict.BLOCK
                        decision.response = "blocked"
                        decision.reason = tool_result["result"]
                        decision.rule = "tool.execution_error"
                    if not isinstance(decision.evidence, dict):
                        decision.evidence = {}
                    decision.evidence.update({
                        "tool_result": tool_result.get("redacted_args") if isinstance(tool_result, dict) else tool_result
                    })
            
            return decision
    
    except Exception as exc:
        # Fail-closed: any exception results in BLOCK
        import traceback
        traceback.print_exc()  # Print traceback for debugging
        decision.verdict = Verdict.BLOCK
        decision.response = "blocked"
        decision.reason = "internal_error"
        decision.rule = "pipeline.exception"
        decision.evidence = {"error_type": type(exc).__name__, "error_message": str(exc)}
        return decision
    
    finally:
        # Measure latency
        latency_ms = (time.perf_counter() - start_time) * 1000
        decision.latency_ms = latency_ms

        # ── ALWAYS print final verdict to terminal (demo visibility) ──
        try:
            glog.verdict_box(
                str(decision.verdict.value if hasattr(decision.verdict, "value") else decision.verdict),
                decision.reason or "",
                decision.trust_before,
                decision.trust_after,
                decision.latency_ms,
            )
        except Exception:
            pass
        
        # Insert event record for EVERY decision
        try:
            db.insert_event({
                "event_id": event.get("event_id"),
                "ts": event.get("ts"),
                "agent_id": event.get("agent_id"),
                "type": event.get("type"),
                "tool": event.get("tool"),
                "args": event.get("args"),
                "context": event.get("context"),
                "nonce": event.get("nonce"),
                "signature": event.get("signature"),
                "verdict": getattr(decision.verdict, "value", decision.verdict),
                "response": decision.response,
                "reason": decision.reason,
                "rule": decision.rule,
                "severity": getattr(decision.severity, "value", decision.severity) if decision.severity else None,
                "trust_before": decision.trust_before,
                "trust_after": decision.trust_after,
                "status": getattr(decision.status, "value", decision.status) if decision.status else None,
                "evidence": decision.evidence,
                "latency_ms": decision.latency_ms
            })
        except Exception as exc:
            print(f"Failed to insert event record: {exc}")
        
        # Step 11: Append audit record for EVERY decision
        try:
            # Add timestamp for audit record
            decision_dict = decision.model_dump()
            decision_dict["ts"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            append_record(decision_dict, event)
        except Exception as exc:
            # If audit fails, log but don't crash
            print(f"Failed to append audit record: {exc}")
        
        # Step 12: Publish to WebSocket (decision + trust if score moved)
        try:
            payload = decision.model_dump(exclude={"evidence"})
            # Ensure agent_id present for dashboard cards
            if not payload.get("agent_id"):
                payload["agent_id"] = event.get("agent_id")
            if not payload.get("event_id"):
                payload["event_id"] = event.get("event_id")
            manager.publish_sync("decision", payload)
            tb = payload.get("trust_before")
            ta = payload.get("trust_after")
            if tb is not None and ta is not None and tb != ta:
                manager.publish_sync("trust", {
                    "agent_id": payload.get("agent_id"),
                    "trust_before": tb,
                    "trust_after": ta,
                    "reason": payload.get("reason") or "",
                })
            st = payload.get("status")
            if st:
                manager.publish_sync("status", {
                    "agent_id": payload.get("agent_id"),
                    "status": st if not hasattr(st, "value") else st.value,
                    "reason": payload.get("reason") or "",
                })
        except Exception as exc:
            print(f"Failed to publish WebSocket message: {exc}")


def load_agent_policy(agent_id: str) -> Dict[str, Any]:
    """Load agent policy from YAML file (anchored to project root, not CWD)."""
    import yaml
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent  # gateway/ -> project root
    policy_path = root / "policies" / f"{agent_id}.yaml"
    if not policy_path.exists():
        # Fallback for alternate layouts / tests
        alt = Path("policies") / f"{agent_id}.yaml"
        if alt.exists():
            policy_path = alt
        else:
            return None

    with open(policy_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# Export load_agent_policy for use in main.py
__all__ = ["run_pipeline", "load_agent_policy"]
