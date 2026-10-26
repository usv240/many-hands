"""House-style clean-up of model output, checked in code."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.agents.models import clean, leaked_fields  # noqa: E402

RIGHT_QUOTE, LEFT_DQ, RIGHT_DQ, EM_DASH = chr(0x2019), chr(0x201C), chr(0x201D), chr(0x2014)


def test_curly_quotes_become_straight():
    assert clean(f"Rafe Quilian{RIGHT_QUOTE}s goal") == "Rafe Quilian's goal"
    assert clean(f"{LEFT_DQ}A fair line{RIGHT_DQ}") == "A fair line"


def test_dashes_and_newlines_removed():
    assert clean(f"A goal {EM_DASH} a fine one\nreally") == "A goal, a fine one really"


def test_a_scoreline_dash_stays_a_scoreline():
    assert clean("Corran Vale lead 3–2 now") == "Corran Vale lead 3-2 now"
    assert clean("Kilnworth 2 – 3 Corran") == "Kilnworth 2-3 Corran"


def test_field_name_leaks_are_found():
    assert leaked_fields("Goal for Corran Vale. Score_after: Kilnworth 2 Corran 3") == ["score_after"]
    assert leaked_fields("Corran Vale lead 3-2 after a loose ball from number 8.") == []


def test_fictional_league_avoids_known_real_player_surnames():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))
    from simulator.league import league

    known_real = {"Varane", "Torres", "Kane", "Saka", "Rashford", "Sancho", "Salah", "Haaland", "Rice"}
    surnames = {p.name.split()[-1] for t in league() for p in t.players}
    assert not surnames & known_real
