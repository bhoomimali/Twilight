# tests/test_peer_trust.py (Owner: M2) [W2]  D5: a quarantined agent messages its peers.
from engine.peer_trust import blast_radius, check_peer, peer_allowed
from tests.m2_helpers import ev, hist, ts

REG = {"coordinator": {"status": "QUARANTINED", "trust": 5}, "supportbot": {"status": "HEALTHY", "trust": 100},
       "databot": {"status": "HEALTHY", "trust": 100}}


def test_peers_refuse_a_quarantined_sender():
    f = check_peer(ev("send_message", {"to": "supportbot"}, agent="coordinator"), REG)
    assert f.rule == "peer_trust.sender_untrusted" and f.verdict == "BLOCK"


def test_healthy_sender_to_healthy_peer_passes():
    assert check_peer(ev("send_message", {"to": "databot"}, agent="supportbot"), REG) is None


def test_low_trust_sender_is_refused_even_if_not_quarantined():
    reg = {**REG, "supportbot": {"status": "THROTTLED", "trust": 25}}
    assert check_peer(ev("send_message", {"to": "databot"}, agent="supportbot"), reg).rule == "peer_trust.sender_untrusted"


def test_messages_to_a_quarantined_peer_are_refused():
    assert check_peer(ev("send_message", {"to": "coordinator"}, agent="supportbot"), REG).rule == "peer_trust.recipient_quarantined"


def test_non_message_tools_are_ignored():
    assert check_peer(ev("read_ticket", agent="coordinator"), REG) is None
    assert peer_allowed("HEALTHY") and not peer_allowed("HALTED")


def test_blast_radius_lists_who_it_talked_to():
    h = [hist("send_message", -60, args={"to": "supportbot"}, agent="coordinator"),
         hist("send_message", -30, args={"to": "databot"}, agent="coordinator"),
         hist("send_message", -20, args={"to": "databot"}, agent="coordinator")]
    assert blast_radius("coordinator", h, ts(0)) == ["supportbot", "databot"]
