

def test_decide_worst_wins_policy_block_over_drift_flag():
    """Regression: policy BLOCK must not be replaced by drift FLAG."""
    from engine.enforcer import decide
    from engine.findings import Finding

    policy_block = Finding("BLOCK", "constraints.issue_refund.max_amount", "Amount too high", "HIGH", penalty_key="constraint_violated")
    drift_flag = Finding("FLAG", "drift.rate_zscore", "Unusual rate", "MEDIUM", penalty_key="drift_anomaly")
    d = decide([policy_block, drift_flag], "on", "HEALTHY", trust_score=100, event={"tool": "issue_refund", "args": {"amount": 9000}}, policy={})
    assert d.verdict == "BLOCK"
