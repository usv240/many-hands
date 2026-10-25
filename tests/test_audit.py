from narrative_core.audit import audit, fair_rewrite
from narrative_core.extraction import Roster, RosterEntry

ROSTER = Roster([
    RosterEntry("cor-5", "Cal Belard", 5, "cor", "RCB"),
    RosterEntry("cor-4", "Femi Drenesh", 4, "cor", "DM"),
    RosterEntry("cor-2", "Bram Oskiro", 2, "cor", "RB"),
])
SHARED = {"cor-5": 0.19, "cor-4": 0.34, "cor-2": 0.27}
SOLE = {"cor-5": 0.85, "cor-4": 0.15}


def test_unfair_line_gets_reasons_and_rewrite():
    r = audit("Number 5's howler cost them the game.", SHARED, ROSTER, "cor")
    assert r.verdict == "unfair" and r.fair_rewrite and "number 4" in r.fair_rewrite
    assert any("times the blame" in x for x in r.reasons)
    assert "number 4" in r.contrastive and not r.justified


def test_justified_sole_blame_is_fair():
    r = audit("Number 5 lost the ball and that was that.", SOLE, ROSTER, "cor")
    assert r.verdict == "fair" and r.justified and r.fair_rewrite is None


def test_neutral_line():
    r = audit("Six passes cut them open.", SHARED, ROSTER, "cor")
    assert r.si == 0.0 and r.verdict == "fair"


def test_rewrite_names_contributors_in_order():
    assert fair_rewrite(SHARED, ROSTER).startswith("Mistakes by number 4, number 2 and number 5")
