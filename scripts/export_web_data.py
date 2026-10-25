"""Export the demo data pack and benchmark results as static JSON for the website.

The site ships with this data so every page works even when the API is unreachable.
It also writes parity fixtures: the Python audit's answers for a set of sentences, which the
site's browser-side engine must reproduce exactly (checked by the web test suite).

Usage:
    uv run python scripts/export_web_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages"))

from narrative_core.audit import audit  # noqa: E402
from services.api.app import chain, chains, matches, native, roster, store  # noqa: E402

OUT = ROOT / "apps" / "web" / "public" / "data"
FIXTURES = ROOT / "apps" / "web" / "src" / "engine" / "__fixtures__"


def results() -> dict:
    ext = json.loads((ROOT / "benchmarks/external_statsbomb/results/summary.json").read_text())
    syn = json.loads((ROOT / "benchmarks/synthetic/results/summary.json").read_text())
    import pandas as pd
    cal = pd.read_csv(ROOT / "benchmarks/synthetic/results_calibration.csv")
    return {
        "external": {
            "cases": ext["cases_evaluated"], "matches": ext["matches"], "goals": ext["goals"],
            "excluded": ext["excluded_by_reason"], "metrics": ext["metrics"],
            "verdicts_if_blamed_alone": ext["si_if_blamed_alone_verdicts"],
            "justified_cases": ext["justified_cases"],
            "justified_false_unfair": ext["justified_cases_unfair_flags"],
            "labelled_share_median": ext["labelled_share_median"], "note": ext["method_note"],
        },
        "synthetic": {
            "bench_games": syn["bench_games"], "train_games": syn["train_games"],
            "moments": syn["moments_with_truth"], "goals": syn["goals"],
            "justified_cases": syn["justified_cases"],
            "metrics": {k: v for k, v in syn["metrics"].items()
                        if k.endswith(("lam0.0", "last")) or k == "last_touch_story_si"},
            "multi_cause": syn["subsets"]["multi_cause_moments"],
            "last_touch_story_unfair_share": syn["last_touch_story_unfair_share"],
        },
        "calibration": cal.to_dict(orient="records"),
        "redteam": json.loads((ROOT / "benchmarks/redteam/reader_results.json").read_text()),
        "foundry_eval": json.loads((ROOT / "benchmarks/foundry_eval/results.json").read_text()),
        "operations": {k: v for k, v in json.loads((ROOT / "benchmarks/operations/results.json").read_text()).items()
                       if k != "rows"},
    }


def sample_csv() -> None:
    """A full fictional match as a rated SPADL CSV: the Bring Your Own sample download."""
    import pandas as pd
    gid = 20045
    L = store.ledgers[gid]
    a = L.actions.copy()
    r = store.roster_df.rename(columns={"name": "player_name", "team": "team_name"})
    a = a.merge(r[["player_id", "player_name", "shirt", "role", "team_name"]], on="player_id", how="left")
    cols = ["game_id", "period_id", "action_id", "time_seconds", "team_id", "team_name", "player_id",
            "player_name", "shirt", "role", "type_name", "result_name", "start_x", "start_y", "end_x",
            "end_y", "offensive_value", "defensive_value", "vaep_value"]
    a[cols].to_csv(OUT / "sample-match.csv", index=False, float_format="%.6g")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    ms = native(matches())
    (OUT / "matches.json").write_text(json.dumps(ms, indent=1))
    parity = []
    for m in ms:
        gid = m["game_id"]
        full = [chain(c["chain_id"]) for c in native(chains(gid))]
        data = {"match": m, "roster": native(roster(gid)), "chains": native(full)}
        L = store.ledgers[gid]
        for c in full:
            cid = c["chain_id"]
            resp = L.responsibility(cid)
            c["shares"] = native(resp.shares)  # full precision, for exact parity in the browser
            team = [e for e in data["roster"] if e["team_id"] == c["conceding_team_id"]]
            top = c["responsibility"][0]["shirt"] if c["responsibility"] else team[1]["shirt"]
            other = next(e for e in team if e["shirt"] != top and e["role"] != "GK")
            sentences = [
                f"Number {top}'s howler cost them the game.",
                f"Number {other['shirt']} was at fault for that goal.",
                f"{other['name'].split()[-1]} switched off and {team[0]['name'].split()[-1]} could not save it.",
                "The defence switched off completely.",
                "A lovely move of six passes cut them open.",
                "The keeper should have done better.",
                "Zed was asleep at the back.",
            ]
            for s in sentences:
                r = audit(s, resp.shares, store.roster(gid), c["conceding_team_id"], goal=c["goal"])
                parity.append({"chain_id": cid, "game_id": gid, "text": s,
                               "si": r.si, "verdict": r.verdict, "blame": r.blame,
                               "unresolved": r.unresolved})
        data["chains"] = native(full)
        (OUT / f"match-{gid}.json").write_text(json.dumps(data))
    (OUT / "results.json").write_text(json.dumps(results(), indent=1))
    sample_csv()
    (FIXTURES / "parity.json").write_text(json.dumps(parity, indent=1))
    print(f"exported {len(ms)} matches, results, and {len(parity)} parity cases")


if __name__ == "__main__":
    main()
