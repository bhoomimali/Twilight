# tests/test_m2_scenarios.py (Owner: M2)
# End-to-end for M2's chain (policy -> enforcer -> trust -> incidents) with a fake clock.
# These mirror the attack scripts D1-D4, D8, D9, so M2 can prove each rule BEFORE M4's scripts exist.
from scripts.m2_sim import SimGateway, d2_injection, d4_spike, d9_honeytoken, normal_traffic


def test_D1_clean_traffic_has_no_false_alarms():
    gw = SimGateway()
    decisions = normal_traffic(gw, rounds=5)
    assert all(d.verdict == "ALLOW" for d in decisions)
    assert all(a.score == 100 and a.status == "HEALTHY" for a in gw.agents.values())
    assert gw.incidents == []


def test_D2_injection():
    r = d2_injection(SimGateway())
    assert r["refund_9000"].verdict == "BLOCK" and r["refund_9000"].rule == "constraints.issue_refund.max_amount"
    assert r["refund_400"].verdict == "HOLD"          # FR14
    assert r["refund_50"].verdict == "ALLOW"          # FR14
    assert r["databot_send"].rule == "allow_tools.tool_not_allowed"
    assert r["leak_card"].rule == "leak_filter.card_number"


def test_D4_spike_throttles_then_halts():
    ds = d4_spike(SimGateway())
    verdicts = [d.verdict for d in ds]
    assert verdicts[:20] == ["ALLOW"] * 20 and verdicts[20] == "THROTTLE"
    assert "HALT" in verdicts and ds[-1].status == "HALTED"
    assert ds[20].trust_after < ds[20].trust_before                  # FR15: lowers trust


def test_D9_honeytoken_is_critical_and_drops_trust_in_one_step():
    d = d9_honeytoken(SimGateway())
    assert d.rule == "honeytoken.touched" and d.severity == "CRITICAL" and d.trust_before - d.trust_after >= 60


def test_D3_config_tamper_quarantines():
    gw = SimGateway()
    d = gw.submit("supportbot", "read_ticket", {"ticket_id": "T1"}, config_mismatch=("good", "bad"))
    assert d.verdict == "QUARANTINE" and gw.agents["supportbot"].status == "QUARANTINED"
    again = gw.submit("supportbot", "read_ticket", {"ticket_id": "T2"})
    assert again.response == "blocked" and again.rule == "status.quarantined"


def test_FR8_halted_agent_is_rejected():
    gw = SimGateway()
    d4_spike(gw)
    d = gw.submit("supportbot", "read_ticket", {"ticket_id": "T9"})
    assert d.response == "halted"


def test_FR7_ladder_in_order():
    gw, seen = SimGateway(), []
    for _ in range(3):
        seen.append(gw.submit("supportbot", "delete_database", {}).status)
    assert seen == ["FLAGGED", "THROTTLED", "QUARANTINED"]


def test_D8_recovery_probation_and_replay_blocked():
    gw = SimGateway()
    for _ in range(3):
        gw.submit("supportbot", "delete_database", {}); gw.advance(1)
    gw.admin_resume("supportbot")
    a = gw.agents["supportbot"]
    assert (a.score, a.status) == (50, "FLAGGED")                     # FR18: starts FLAGGED
    for i in range(gw.s.probation_clean_actions):
        gw.advance(5); gw.submit("supportbot", "read_ticket", {"ticket_id": f"R{i}"})
    assert (a.score, a.status) == (80, "HEALTHY")                     # back to healthy after N clean actions
    assert gw.submit("supportbot", "issue_refund", {"customer": "c", "amount": 9000}, taint="untrusted").verdict == "BLOCK"


def test_clean_time_recovers_a_flagged_agent_but_only_with_hysteresis():
    gw = SimGateway()
    gw.submit("supportbot", "issue_refund", {"customer": "c", "amount": 9000}); gw.advance(1)   # 100 -> 75
    gw.submit("supportbot", "issue_refund", {"customer": "c", "amount": 9000}); gw.advance(1)   # 75 -> 50 FLAGGED
    a = gw.agents["supportbot"]
    assert (a.score, a.status) == (50, "FLAGGED")
    gw.advance(60 * 24); gw.submit("supportbot", "read_ticket", {"ticket_id": "x"})            # +24 -> 74, still FLAGGED
    assert a.status == "FLAGGED"
    gw.advance(60 * 2); gw.submit("supportbot", "read_ticket", {"ticket_id": "y"})             # >= 75
    assert a.status == "HEALTHY"
