"""Detection benchmark: does the check flag the one-culprit lines that are truly unfair, and only those?

The product's job is not to rank players; it is to decide whether a line that blames one player is
fair. Here that decision is scored against the synthetic ground truth (every mistake replayed 100
times with and without it), on matches the ledger's settings were never chosen on:

  - the 60 benchmark matches are split by match: settings are chosen on 30, results reported on 30;
  - the pundit line blames the last defender to lose the ball, alone (what a one-culprit story does);
  - it is truly unfair when its Scapegoat Index against the true causes is above 0.40;
  - the check flags it when its Scapegoat Index against the ledger is above 0.40.

Also reports the negative control against the truth: when one player truly caused 60 percent or
more, how often is a line blaming that player alone wrongly flagged.

Usage:
    uv run python benchmarks/synthetic/detection.py
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages"))

from ledger_core import responsibility  # noqa: E402
from ledger_core.responsibility import last_touch_ranking, ranking  # noqa: E402
from narrative_core.scapegoat import scapegoat_index  # noqa: E402

DATA_DIR = ROOT / ".data" / "synthetic" / "bench"
OUT = Path(__file__).resolve().parent / "results" / "detection.json"
UNFAIR = 0.40
WATCH = 0.20
JUSTIFIED = 0.60
DRAWS = 1000
SEED = 7
GRID = list(itertools.product([0.0, 0.2, 0.4], [False, True], [1.0, 2.0, 4.0, 8.0]))
DEFAULTS = (responsibility.MIN_FRACTION, responsibility.ONLY_FAILURES, responsibility.LAST_TURNOVER_BOOST)


def tv(a: dict, b: dict) -> float:
    return 0.5 * sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in set(a) | set(b))


def load() -> list[dict]:
    rated = pd.read_parquet(DATA_DIR / "rated.parquet")
    by_game = {g: a.reset_index(drop=True) for g, a in rated.groupby("game_id")}
    cases = []
    for m in json.loads((DATA_DIR / "moments.json").read_text()):
        if not m["truth"]:
            continue
        a = by_game[m["game_id"]]
        chain = a[(a.action_id >= m["window_start_action_id"]) & (a.action_id <= m["shot_action_id"])]
        last = last_touch_ranking(chain.iloc[:-1], m["conceding_team_id"])
        cases.append({"game_id": m["game_id"], "chain": chain, "team": m["conceding_team_id"],
                      "truth": m["truth"], "last": last[0] if last else None})
    return cases


def shares(case: dict, config: tuple) -> dict:
    min_fraction, only_failures, boost = config
    return responsibility.onball_blame(case["chain"], case["team"], min_fraction=min_fraction,
                                       only_failures=only_failures, last_turnover_boost=boost)


def rows(cases: list[dict], config: tuple) -> pd.DataFrame:
    out = []
    for c in cases:
        ours = shares(c, config)
        top = ranking(c["truth"])[0]
        row = {"game_id": c["game_id"], "tv": tv(ours, c["truth"])}
        # As in the product: with no counted mistake the verdict is Watch (a person decides), never Unfair.
        if c["last"]:  # the pundit's line: the last player to lose the ball, alone
            line = {c["last"]: 1.0}
            si = scapegoat_index(line, ours) if ours else None
            row["truly_unfair"] = scapegoat_index(line, c["truth"]) > UNFAIR
            row["flagged"] = si is not None and si > UNFAIR
            row["to_person"] = si is None or si > WATCH
        if c["truth"][top] >= JUSTIFIED:  # deserved blame: a line naming the true main cause alone
            row["justified_flagged"] = bool(ours) and scapegoat_index({top: 1.0}, ours) > UNFAIR
            row["justified_flagged_last"] = bool(c["last"]) and scapegoat_index({top: 1.0}, {c["last"]: 1.0}) > UNFAIR
        out.append(row)
    return pd.DataFrame(out)


def rate(df: pd.DataFrame, num: pd.Series, den: pd.Series) -> dict:
    """A ratio with a 95 percent bootstrap interval over matches."""
    g = pd.DataFrame({"game_id": df["game_id"], "num": num.astype(float), "den": den.astype(float)})
    per = g.groupby("game_id")[["num", "den"]].sum()
    rng = np.random.default_rng(SEED)
    draws = []
    for _ in range(DRAWS):
        pick = per.loc[rng.choice(per.index, size=len(per), replace=True)]
        if pick["den"].sum():
            draws.append(pick["num"].sum() / pick["den"].sum())
    return {"value": round(float(per["num"].sum() / per["den"].sum()), 3), "n": int(per["den"].sum()),
            "hits": int(per["num"].sum()),
            "ci95": [round(float(np.percentile(draws, 2.5)), 3), round(float(np.percentile(draws, 97.5)), 3)]}


def main() -> None:
    cases = load()
    games = sorted({c["game_id"] for c in cases})
    tune_games, test_games = set(games[0::2]), set(games[1::2])
    tune = [c for c in cases if c["game_id"] in tune_games]
    test = [c for c in cases if c["game_id"] in test_games]

    tune_tv = {cfg: rows(tune, cfg)["tv"].mean() for cfg in GRID}
    chosen = min(tune_tv, key=tune_tv.get)
    df = rows(test, DEFAULTS)  # report what the product ships
    p = df.dropna(subset=["truly_unfair"])
    tu, fl, tp = p["truly_unfair"].astype(bool), p["flagged"].astype(bool), p["to_person"].astype(bool)
    j = df.dropna(subset=["justified_flagged"])
    summary = {
        "split": {"tune_matches": len(tune_games), "test_matches": len(test_games),
                  "tune_moments": len(tune), "test_moments": len(test)},
        "chosen_on_tune_half": {"min_fraction": chosen[0], "only_failures": chosen[1], "last_turnover_boost": chosen[2]},
        "product_defaults": {"min_fraction": DEFAULTS[0], "only_failures": DEFAULTS[1], "last_turnover_boost": DEFAULTS[2]},
        "tune_half_distance": {"chosen": round(float(tune_tv[chosen]), 4),
                               "product_defaults": round(float(tune_tv[tuple(DEFAULTS)]), 4)},
        "reported_on_test_half": "product defaults",
        "test_half": {
            "pundit_lines": int(len(p)),
            "truly_unfair_lines": int(tu.sum()),
            "called_unfair": {
                "recall": rate(p, tu & fl, tu),
                "precision": rate(p, tu & fl, fl),
                "fair_lines_called_unfair": rate(p, ~tu & fl, ~tu),
                "accuracy": rate(p, tu == fl, pd.Series(True, index=p.index)),
            },
            "sent_to_a_person": {  # Watch or Unfair: not aired automatically
                "recall": rate(p, tu & tp, tu),
                "precision": rate(p, tu & tp, tp),
                "fair_lines_sent": rate(p, ~tu & tp, ~tu),
            },
            "baseline_last_touch_flags_nothing": {"recall": 0.0, "accuracy": round(float((~tu).mean()), 3)},
            "justified_blame_wrongly_flagged": rate(j, j["justified_flagged"].astype(bool), pd.Series(True, index=j.index)),
            "justified_blame_wrongly_flagged_last_touch": rate(
                j, j["justified_flagged_last"].astype(bool), pd.Series(True, index=j.index)),
            "distance_to_truth": round(float(df["tv"].mean()), 3),
        },
    }
    OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
