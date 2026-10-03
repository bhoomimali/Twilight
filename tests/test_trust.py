# tests/test_trust.py (Owner: M2)
# Covers: penalty weights, tier transitions, recovery, hysteresis, probation cap, critical override.
import pytest

from engine import trust


def test_penalty_weights_match_the_prd():
    for reason, pts in {"tool_not_allowed": 40, "sequence_violation": 40, "constraint_violated": 25,
                        "rate_exceeded": 15, "drift_anomaly": 10}.items():
        assert trust.apply_penalty(100, reason).score == 100 - pts


def test_unknown_penalty_reason_is_rejected():
    with pytest.raises(ValueError):
        trust.apply_penalty(100, "made_up_reason")


def test_score_never_goes_below_zero():
    assert trust.apply_penalty(10, "tool_not_allowed").score == 0


@pytest.mark.parametrize("score,expected", [(100, "HEALTHY"), (70, "HEALTHY"), (69, "FLAGGED"), (40, "FLAGGED"),
                                           (39, "THROTTLED"), (20, "THROTTLED"), (19, "QUARANTINED"), (0, "QUARANTINED")])
def test_band_edges(score, expected):
    assert trust.status_for_score(score) == expected


def test_repeated_violations_walk_the_whole_ladder_in_order():
    score, status, seen = 100, "HEALTHY", ["HEALTHY"]
    for _ in range(3):
        r = trust.apply_penalty(score, "tool_not_allowed", current_status=status)
        score, status = r.score, r.status
        seen.append(status)
    assert seen == ["HEALTHY", "FLAGGED", "THROTTLED", "QUARANTINED"]


def test_hysteresis_stops_flip_flopping():
    # dropped to FLAGGED at 69. At 71 the raw band is HEALTHY, but we need 75 to really go back.
    assert trust.status_for_score(71, "FLAGGED") == "FLAGGED"
    assert trust.status_for_score(74, "FLAGGED") == "FLAGGED"
    assert trust.status_for_score(75, "FLAGGED") == "HEALTHY"
    # going down is immediate
    assert trust.status_for_score(69, "HEALTHY") == "FLAGGED"
    assert trust.status_for_score(45, "THROTTLED") == "FLAGGED"
    assert trust.status_for_score(44, "THROTTLED") == "THROTTLED"


def test_quarantined_and_halted_are_sticky():
    assert trust.status_for_score(100, "QUARANTINED") == "QUARANTINED"
    assert trust.status_for_score(100, "HALTED") == "HALTED"
    assert trust.recover_clean_agent(10, 60, "QUARANTINED").score == 10


def test_recovery_is_one_point_per_clean_minute_capped_at_100():
    assert trust.recover_clean_agent(50, 10, "FLAGGED").score == 60
    assert trust.recover_clean_agent(95, 30, "HEALTHY").score == 100
    assert trust.recover_clean_agent(50, 0.5, "FLAGGED").score == 50      # whole minutes only


def test_probation_caps_the_score_below_healthy():
    _, prob = trust.start_probation()
    r = trust.recover_clean_agent(60, 120, "FLAGGED", prob)
    assert r.score == 69 and r.status == "FLAGGED"                        # cannot reach HEALTHY by waiting alone


def test_resume_starts_reduced_not_100_and_probation_ends_after_n_clean_actions():
    r, prob = trust.start_probation()
    assert (r.score, r.status) == (50, "FLAGGED") and prob.active
    score, status = r.score, r.status
    for _ in range(prob.required):
        prob, res = trust.record_clean_action(prob, score, status)
        score, status = res.score, res.status
    assert not prob.active and (score, status) == (80, "HEALTHY")


def test_probation_tightens_amount_limits():
    _, prob = trust.start_probation()
    assert trust.probation_limits_factor(prob) == 0.5
    assert trust.probation_limits_factor(None) == 1.0


def test_config_mismatch_is_a_critical_override_whatever_the_score():
    r = trust.apply_penalty(100, "config_mismatch")
    assert r.status == "QUARANTINED" and r.critical and r.score < 20


def test_honeytoken_is_a_big_one_step_drop():
    r = trust.apply_penalty(100, "honeytoken")
    assert r.score == 30 and r.status == "THROTTLED" and r.critical


def test_contract_can_override_a_penalty_number():
    assert trust.apply_penalty(100, "rate_exceeded", {"penalties": {"rate_exceeded": 5}}).score == 95


def test_settings_come_from_env(monkeypatch):
    monkeypatch.setenv("PENALTY_TOOL_NOT_ALLOWED", "10")
    assert trust.apply_penalty(100, "tool_not_allowed").score == 90
