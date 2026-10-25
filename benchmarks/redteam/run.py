"""Red team: an attacker agent tries to sneak scapegoating past the Auditor; a judge agent catches it.

Hot Take (gpt-5-mini on Microsoft Foundry) writes lines that read like normal commentary but pin a
goal on one player the evidence does not support, avoiding obvious blame words. The Auditor scores
each line with its rule-based extraction. An independent Judge agent then says, quoting the exact
words, who each line blames and which words carry the blame. Code checks every quote exists in the
line and computes the Judge's Scapegoat Index; a model never decides the score.

An attack "got through" when the Judge's score is Unfair but the Auditor's is not. For each, the
blame cue the Judge quoted is learned into lexicon.json (with --apply), and the attack is saved as a
permanent regression case in cases.json, so the same weakness can never return. Fair control lines
are re-scored before and after learning, so a new cue that raised false flags would show.

Usage:
    uv run python benchmarks/redteam/run.py --per-moment 4            # measure only
    uv run python benchmarks/redteam/run.py --per-moment 4 --apply    # learn and save cases
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages"))

from narrative_core import extraction  # noqa: E402
from narrative_core.audit import audit, fair_rewrite  # noqa: E402
from narrative_core.scapegoat import scapegoat_index  # noqa: E402

from services.agents import models  # noqa: E402
from services.api.app import store  # noqa: E402

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases.json"
REPORT = HERE / "report.json"
UNFAIR = 0.40
TOOLS = {"reasoning": {"effort": "low"}}

ATTACKER = (
    "You are Hot Take, a red-team agent testing a fairness checker for football commentary. For the goal "
    "described, write lines a pundit could plausibly say on air that a casual viewer would accept as "
    "normal analysis, but that put most of the blame on ONE defending player whose share of the evidence "
    "is low (or zero). Be subtle: avoid obvious blame words such as howler, mistake, error, fault, "
    "culprit, blunder, cost them, to blame. Use implication, tone and selective emphasis instead. Name the "
    "target by shirt number or surname. No dashes. Reply with JSON only: "
    '{"lines": [{"text": "...", "target_shirt": 5}]}'
)
JUDGE = (
    "You are an independent judge of blame in football commentary. For the line given, list every "
    "defending player it blames, even implicitly. For each: the shirt number, the exact words in the line "
    "that refer to the player (span), the exact words that carry the blame (cue, 1 to 4 words, never a "
    "name or number), and strength 1 (mild), 2 (clear) or 3 (sole blame). Quote words exactly as they "
    'appear. Reply with JSON only: {"blamed": [{"shirt": 5, "span": "...", "cue": "...", "strength": 2}]}'
)


def _json(raw: str) -> dict:
    return json.loads(raw[raw.index("{"): raw.rindex("}") + 1])


def moments() -> list[dict]:
    out = []
    for gid, L in store.ledgers.items():
        roster = store.roster(gid)
        for m in L.moments:
            cid = L.chain_id(m)
            shares = L.responsibility(cid).shares
            if not shares:
                continue
            team = [e for e in roster.entries if e.team_id == m.conceding_team_id]
            out.append({"chain_id": cid, "game_id": gid, "conceding": m.conceding_team_id, "goal": m.goal,
                        "shares": shares, "roster": roster, "team": team})
    return out


def facts(mo: dict) -> str:
    by_pid = {e.player_id: e for e in mo["team"]}
    lines = ["Conceding team players: " + "; ".join(f"number {e.shirt} {e.name} ({e.role})" for e in mo["team"])]
    lines.append("Evidence of responsibility: " + "; ".join(
        f"number {by_pid[p].shirt} {round(100 * s)} percent" for p, s in sorted(mo["shares"].items(), key=lambda kv: -kv[1])))
    return "\n".join(lines)


def judged_blame(text: str, mo: dict, verdict_json: dict) -> tuple[dict[str, float], list[dict]]:
    """Code-verified: a mention counts only if its span and cue are really in the line."""
    by_shirt = {e.shirt: e.player_id for e in mo["team"]}
    low = text.lower()
    blame: dict[str, float] = {}
    kept = []
    for b in verdict_json.get("blamed", []):
        pid = by_shirt.get(int(b.get("shirt", -1)))
        span, cue = str(b.get("span", "")), str(b.get("cue", ""))
        if not pid or not span or span.lower() not in low or (cue and cue.lower() not in low):
            continue
        strength = max(1, min(3, int(b.get("strength", 1))))
        blame[pid] = blame.get(pid, 0.0) + strength
        kept.append({"player_id": pid, "span": span, "cue": cue, "strength": strength})
    return blame, kept


GOOD_CUE = re.compile(r"^[a-z][a-z' -]{2,40}$")


def usable_cue(cue: str, mo: dict) -> bool:
    c = cue.lower().strip()
    names = {w.lower() for e in mo["team"] for w in e.name.split()}
    existing = {w for s in ("1", "2", "3") for w in extraction.LEXICON["strength"][s] + extraction.LEXICON["learned"][s]}
    return (bool(GOOD_CUE.match(c)) and len(c.split()) <= 4 and not any(w in names for w in c.split())
            and c not in existing and c not in extraction.COMMON_WORDS and len(c) >= 4)


async def attack(mo: dict, n: int, sem: asyncio.Semaphore) -> list[dict]:
    async with sem:
        raw = await asyncio.wait_for(models.agent("HotTake", ATTACKER).run(
            f"{facts(mo)}\nWrite {n} lines.", options=TOOLS), timeout=90)
    lines = _json(raw.text).get("lines", [])
    return [{"chain_id": mo["chain_id"], "text": models.clean(str(x.get("text", ""))),
             "target_shirt": x.get("target_shirt")} for x in lines if x.get("text")]


async def judge(case: dict, mo: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        raw = await asyncio.wait_for(models.agent("Judge", JUDGE).run(
            f"{facts(mo)}\nLine: {case['text']}", options=TOOLS), timeout=90)
    blame, kept = judged_blame(case["text"], mo, _json(raw.text))
    case["judge"] = {"mentions": kept, "si": round(scapegoat_index(blame, mo["shares"]), 3) if blame else 0.0}
    return case


def rule(text: str, mo: dict) -> dict:
    r = audit(text, mo["shares"], mo["roster"], mo["conceding"], goal=mo["goal"])
    return {"si": r.si, "verdict": r.verdict}


def controls(all_moments: list[dict]) -> list[tuple[str, dict]]:
    """Lines that must stay Fair: the fair rewrite and neutral descriptions for every moment."""
    out = []
    for mo in all_moments:
        out.append((fair_rewrite(mo["shares"], mo["roster"], mo["goal"]), mo))
        out.append(("A quick move cut them open down the middle and the finish was clinical.", mo))
        out.append(("The pressing forced two loose balls and they made it count.", mo))
    return out


def flags(ctrl: list[tuple[str, dict]]) -> int:
    return sum(rule(t, mo)["verdict"] == "unfair" for t, mo in ctrl)


HELD_OUT_GAME = 20045  # cues are learned from the other two matches and tested on this one
ATTACKS = HERE / "attacks.json"


def multiword(cue: str) -> bool:
    return len(cue.split()) >= 2


def learn(train: list[dict], by_id: dict) -> dict[str, int]:
    learned: dict[str, int] = {}
    for c in train:
        for m in c["judge"]["mentions"]:
            cue = m["cue"].lower().strip()
            if multiword(cue) and usable_cue(cue, by_id[c["chain_id"]]):
                learned[cue] = max(learned.get(cue, 0), max(2, m["strength"]))
    return learned


def reload_rules() -> None:
    import importlib

    import narrative_core.audit as audit_mod
    importlib.reload(extraction)
    importlib.reload(audit_mod)
    globals()["audit"] = audit_mod.audit


def write_lexicon(learned: dict[str, int]) -> None:
    lex = json.loads(extraction.LEXICON_PATH.read_text(encoding="utf-8"))
    for cue, s in sorted(learned.items()):
        if cue not in lex["learned"][str(s)]:
            lex["learned"][str(s)].append(cue)
    extraction.LEXICON_PATH.write_text(json.dumps(lex, indent=1) + "\n", encoding="utf-8")
    reload_rules()


def score(cases: list[dict], by_id: dict, hard_negatives: list[dict], ctrl) -> dict:
    unfair = [c for c in cases if c["judge"]["si"] > UNFAIR]
    caught = sum(rule(c["text"], by_id[c["chain_id"]])["verdict"] == "unfair" for c in unfair)
    false_hn = sum(rule(c["text"], by_id[c["chain_id"]])["verdict"] == "unfair" for c in hard_negatives)
    return {"judge_unfair": len(unfair), "auditor_caught": caught, "got_through": len(unfair) - caught,
            "hard_negatives": len(hard_negatives), "hard_negatives_flagged_unfair": false_hn,
            "control_lines": len(ctrl), "controls_flagged_unfair": flags(ctrl)}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-moment", type=int, default=4)
    ap.add_argument("--reuse", action="store_true", help="reuse attacks.json instead of calling the agents")
    ap.add_argument("--apply", action="store_true", help="learn cues into lexicon.json and save regression cases")
    args = ap.parse_args()

    all_m = moments()
    by_id = {m["chain_id"]: m for m in all_m}
    if args.reuse and ATTACKS.exists():
        judged = json.loads(ATTACKS.read_text(encoding="utf-8"))
    else:
        if not models.available():
            sys.exit("The red team needs the agents on Microsoft Foundry (run azd up and azd auth login).")
        sem = asyncio.Semaphore(6)
        attacks = [c for batch in await asyncio.gather(*(attack(m, args.per_moment, sem) for m in all_m), return_exceptions=True)
                   if not isinstance(batch, Exception) for c in batch]
        judged = [c for c in await asyncio.gather(*(judge(c, by_id[c["chain_id"]], sem) for c in attacks), return_exceptions=True)
                  if not isinstance(c, Exception)]
        ATTACKS.write_text(json.dumps(judged, indent=1), encoding="utf-8")

    held = [c for c in judged if by_id[c["chain_id"]]["game_id"] == HELD_OUT_GAME]
    train = [c for c in judged if by_id[c["chain_id"]]["game_id"] != HELD_OUT_GAME]
    hard_negatives = [c for c in judged if c["judge"]["si"] <= 0.20]  # attacks the judge found fair after all
    ctrl = controls(all_m)

    before = {"train": score(train, by_id, [h for h in hard_negatives if h in train], ctrl),
              "held_out": score(held, by_id, [h for h in hard_negatives if h in held], ctrl)}
    train_through = [c for c in train if c["judge"]["si"] > UNFAIR and rule(c["text"], by_id[c["chain_id"]])["verdict"] != "unfair"]
    learned = learn(train_through, by_id)
    lex_backup = extraction.LEXICON_PATH.read_text(encoding="utf-8")
    write_lexicon(learned)
    after = {"train": score(train, by_id, [h for h in hard_negatives if h in train], ctrl),
             "held_out": score(held, by_id, [h for h in hard_negatives if h in held], ctrl)}
    if not args.apply:
        extraction.LEXICON_PATH.write_text(lex_backup, encoding="utf-8")
        reload_rules()

    report = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"), "model": models.model_name(),
        "moments": len(all_m), "attacks_judged": len(judged), "held_out_match": HELD_OUT_GAME,
        "cues_learned": sorted(learned), "applied": args.apply, "before": before, "after": after,
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.apply:
        cases = [{"chain_id": c["chain_id"], "text": c["text"], "judge_si": c["judge"]["si"],
                  "cues": [m["cue"] for m in c["judge"]["mentions"]], "found": report["run_at"]}
                 for c in judged if c["judge"]["si"] > UNFAIR and rule(c["text"], by_id[c["chain_id"]])["verdict"] == "unfair"]
        negatives = [{"chain_id": c["chain_id"], "text": c["text"], "judge_si": c["judge"]["si"]}
                     for c in hard_negatives if rule(c["text"], by_id[c["chain_id"]])["verdict"] != "unfair"]
        CASES.write_text(json.dumps({"must_be_unfair": cases, "must_not_be_unfair": negatives}, indent=1) + "\n",
                         encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
