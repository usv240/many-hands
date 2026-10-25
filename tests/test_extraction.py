import pytest
from narrative_core.extraction import Extraction, Mention, Roster, RosterEntry, RuleExtractor
from narrative_core.scapegoat import scapegoat_index, verdict

ROSTER = Roster([
    RosterEntry("cor-1", "Ari Varen", 1, "cor", "GK"),
    RosterEntry("cor-2", "Bram Oskiro", 2, "cor", "RB"),
    RosterEntry("cor-5", "Cal Belard", 5, "cor", "RCB"),
    RosterEntry("cor-6", "Dario Torovic", 6, "cor", "LCB"),
    RosterEntry("cor-3", "Eli Makane", 3, "cor", "LB"),
    RosterEntry("cor-4", "Femi Drenesh", 4, "cor", "DM"),
    RosterEntry("cor-9", "Gus Halow", 9, "cor", "ST"),
    RosterEntry("nor-9", "Ivo Belard", 9, "nor", "ST"),
])
EVIDENCE = {"cor-5": 0.19, "cor-4": 0.34, "cor-2": 0.27, "cor-6": 0.20}


def test_sole_blame_by_shirt_number():
    x = RuleExtractor(ROSTER, "cor").extract("Number 5's howler cost them the game.")
    b = x.blame()
    assert b == {"cor-5": 3}
    assert verdict(scapegoat_index(b, EVIDENCE)).value == "unfair"


def test_shared_blame_scores_fair():
    x = RuleExtractor(ROSTER, "cor").extract(
        "A misplaced pass from Drenesh, Oskiro out of position and a heavy touch by Belard let them in.")
    b = x.blame()
    assert set(b) == {"cor-4", "cor-2", "cor-5"}
    assert verdict(scapegoat_index(b, EVIDENCE)).value != "unfair"


def test_neutral_line_blames_no_one():
    x = RuleExtractor(ROSTER, "cor").extract("A move of six passes cut through the middle.")
    assert x.blame() == {}
    assert scapegoat_index(x.blame(), EVIDENCE) == 0.0


def test_group_blame_spreads_over_defenders():
    x = RuleExtractor(ROSTER, "cor").extract("The defence switched off completely.")
    b = x.blame()
    assert set(b) == {"cor-2", "cor-5", "cor-6", "cor-3"}
    assert len({round(v, 6) for v in b.values()}) == 1


def test_role_reference():
    x = RuleExtractor(ROSTER, "cor").extract("The keeper should have done better.")
    assert x.blame() == {"cor-1": 2}


def test_surname_on_wrong_team_is_ignored_and_ambiguity_reported():
    # Belard exists on both teams; the conceding team's Belard is the only one considered.
    x = RuleExtractor(ROSTER, "cor").extract("Belard was sloppy.")
    assert x.blame() == {"cor-5": 2}


def test_unknown_name_is_unresolved_not_guessed():
    x = RuleExtractor(ROSTER, "cor").extract("Zed was at fault.")
    assert x.blame() == {}
    assert "Zed" in x.unresolved


def test_credit_is_not_blame():
    x = RuleExtractor(ROSTER, "cor").extract("Halow scored a brilliant goal.")
    assert x.blame() == {}
    assert x.mentions and x.mentions[0].polarity == "credit"


def test_invented_span_is_rejected():
    with pytest.raises(ValueError):
        Extraction(text="Number 5 lost it.", mentions=[
            Mention(player_id="cor-5", span="Number 7", strength=3, polarity="blame")])
