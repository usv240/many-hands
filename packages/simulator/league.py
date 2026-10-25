"""A fictional league: clubs and players are invented and seeded, never real."""

from __future__ import annotations

import numpy as np

from simulator.engine import ROLES, Player, Team

CLUBS = [
    ("Corran Vale", "COR"), ("Northmere Athletic", "NOR"), ("Saltreach Rovers", "SAL"),
    ("Kilnworth United", "KIL"), ("Bramhollow", "BRA"), ("Eastholm City", "EAS"),
    ("Wyrecliff Albion", "WYR"), ("Duncliffe Wanderers", "DUN"),
]
FIRST = ["Ari", "Bram", "Cal", "Dario", "Eli", "Femi", "Gus", "Hal", "Ivo", "Jory", "Kian", "Luca",
         "Milo", "Nico", "Oren", "Pax", "Quin", "Rafe", "Sami", "Teo", "Udo", "Vito", "Wes", "Yan"]
SYL_A = ["Var", "Osk", "Bel", "Tor", "Mak", "Dren", "Hal", "Quil", "Rost", "Sev", "Lun", "Ferr"]
SYL_B = ["en", "iro", "ard", "ovic", "ane", "esh", "ow", "ain", "ek", "ura", "ent", "ian"]
SHIRTS = (1, 2, 5, 6, 3, 4, 8, 10, 7, 9, 11)

# Generated surnames that collide with a well-known real player, or read like a word in commentary.
# Replaced after generation, so no random draw changes and every simulated match stays identical.
RENAME = {"Varane": "Varnow", "Seven": "Sevanko"}


def _attr(rng: np.random.Generator, mean: float, sd: float = 0.07) -> float:
    return float(np.clip(rng.normal(mean, sd), 0.4, 0.97))


def make_team(index: int, seed: int = 2026) -> Team:
    rng = np.random.default_rng(seed * 100 + index)
    name, short = CLUBS[index]
    tid = short.lower()
    quality = rng.normal(0, 0.03)
    players = []
    used: set[str] = set()
    for i, role in enumerate(ROLES):
        while True:
            surname = rng.choice(SYL_A) + rng.choice(SYL_B)
            if surname not in used:
                used.add(surname)
                break
        players.append(Player(
            pid=f"{tid}-{SHIRTS[i]}",
            name=f"{rng.choice(FIRST)} {RENAME.get(surname, surname)}",
            shirt=SHIRTS[i],
            role=role,
            passing=_attr(rng, 0.76 + quality + (0.04 if role in ("DM", "RCM", "LCM") else 0)),
            composure=_attr(rng, 0.72 + quality),
            discipline=_attr(rng, 0.78 + quality, 0.09),
            finishing=_attr(rng, 0.7 + (0.1 if role in ("ST", "RW", "LW") else -0.1)),
            pace=_attr(rng, 0.72 + (0.06 if role in ("RW", "LW", "RB", "LB") else 0)),
        ))
    return Team(tid=tid, name=name, short=short, players=tuple(players),
                tempo=float(np.clip(rng.normal(1.0, 0.25), 0.6, 1.5)))


def league(seed: int = 2026) -> list[Team]:
    return [make_team(i, seed) for i in range(len(CLUBS))]
