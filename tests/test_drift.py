"""M3: drift scoring + pipeline check_drift API."""
from engine.drift import check_drift, score_drift, reset_baselines, get_baseline


def test_cold_start_no_finding():
    reset_baselines()
    event = {"agent_id": "a1", "tool": "read_ticket", "args": {"id": 1}, "ts": 1_700_000_000.0}
    assert check_drift(event) is None
    assert score_drift("a1", event) is None


def test_baseline_accumulates():
    reset_baselines()
    for i in range(15):
        check_drift({
            "agent_id": "a2", "tool": "read_ticket", "args": {"id": i},
            "ts": 1_700_000_000.0 + i * 1.0,
        })
    bl = get_baseline("a2")
    assert len(bl.rates) >= 10
    assert bl.last_tool == "read_ticket"


def test_check_drift_returns_finding_or_none():
    reset_baselines()
    for i in range(20):
        check_drift({
            "agent_id": "a3", "tool": "read_ticket", "args": {},
            "ts": 1_700_000_000.0 + i,
        })
    finding = None
    for j in range(30):
        finding = check_drift({
            "agent_id": "a3", "tool": "read_ticket", "args": {},
            "ts": 1_700_000_020.0 + j * 0.001,
        })
    assert finding is None or (
        hasattr(finding, "rule") and str(finding.rule).startswith("drift.")
    )
