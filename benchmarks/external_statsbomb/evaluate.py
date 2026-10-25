"""External benchmark: provider-labelled errors in public match data we did not create.

For every StatsBomb "Error" (an on-the-ball mistake that leads to an opposition shot):
  A. Top-1 and top-3 recall: does our ledger rank the labelled player among the most responsible?
     Baselines: last-touch blame, and a random pick among the defending players involved.
  B. The labelled player's share of the computed responsibility.
  B2. The Scapegoat Index a line would get if it blamed the labelled player alone.

Confidence intervals: 95 percent, bootstrap resampling whole matches (1,000 draws).
On public event data this uses on-ball responsibility only (no positions), and says so.

Usage:
    uv run python benchmarks/external_statsbomb/evaluate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages"))

from ledger_core.responsibility import last_touch_ranking, onball_blame, ranking  # noqa: E402
from narrative_core.scapegoat import Verdict, scapegoat_index, verdict  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[2] / ".data" / "statsbomb"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
CHAIN_FALLBACK_ACTIONS = 10
JUSTIFIED_SHARE = 0.60
BOOTSTRAP_DRAWS = 1000
SEED = 7


def build_chain(game_actions: pd.DataFrame, err: pd.Series) -> pd.DataFrame | None:
    """Actions from the start of the possession containing the error up to the shot."""
    shot_idx = game_actions.index[game_actions["original_event_id"] == err.shot_event_id]
    if len(shot_idx) == 0:
        return None
    end = int(shot_idx[0])
    same = game_actions.index[
        (game_actions["possession"] == err.error_possession)
        & (game_actions["period_id"] == err.period_id)
    ]
    start = int(same[0]) if len(same) else end - CHAIN_FALLBACK_ACTIONS
    if start > end:
        start = end - CHAIN_FALLBACK_ACTIONS
    return game_actions.loc[max(start, 0) : end]


def evaluate_cases(rated: pd.DataFrame, errors: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    rows = []
    by_game = {gid: g.reset_index(drop=True) for gid, g in rated.groupby("game_id")}
    for err in errors.itertuples(index=False):
        base = {"game_id": err.game_id, "error_event_id": err.error_event_id,
                "goal": err.shot_outcome == "Goal"}
        if pd.isna(err.shot_event_id) or err.game_id not in by_game:
            rows.append({**base, "status": "no_linked_shot"})
            continue
        chain = build_chain(by_game[err.game_id], err)
        if chain is None:
            rows.append({**base, "status": "shot_not_in_actions"})
            continue
        before_shot = chain.iloc[:-1]
        team, player = err.error_team_id, err.error_player_id
        shares = onball_blame(chain, team)
        if not shares:
            rows.append({**base, "status": "no_onball_blame"})
            continue
        ours = ranking(shares)
        last = last_touch_ranking(before_shot, team)
        involved = before_shot.loc[before_shot["team_id"] == team, "player_id"].dropna().unique()
        n = max(len(involved), 1)
        share = shares.get(player, 0.0)
        si_alone = scapegoat_index({player: 1.0}, shares)
        rows.append({
            **base,
            "status": "ok",
            "chain_actions": len(chain),
            "defenders_involved": len(involved),
            "defenders_blamed": len(shares),
            "ours_top1": ours[0] == player,
            "ours_top3": player in ours[:3],
            "last_top1": bool(last) and last[0] == player,
            "last_top3": player in last[:3],
            "random_top1": 1.0 / n,
            "random_top3": min(3, n) / n,
            "labelled_share": share,
            "max_share": max(shares.values()),
            "justified": max(shares.values()) >= JUSTIFIED_SHARE and ours[0] == player,
            "si_if_blamed_alone": si_alone,
            "verdict_if_blamed_alone": verdict(si_alone).value,
            "_tiebreak": rng.random(),
        })
    return pd.DataFrame(rows)


def bootstrap_mean(df: pd.DataFrame, col: str) -> dict[str, float]:
    rng = np.random.default_rng(SEED)
    games = df["game_id"].unique()
    per_game = df.groupby("game_id")[col].agg(["sum", "count"])
    means = []
    for _ in range(BOOTSTRAP_DRAWS):
        pick = per_game.loc[rng.choice(games, size=len(games), replace=True)]
        means.append(pick["sum"].sum() / pick["count"].sum())
    return {
        "mean": float(df[col].astype(float).mean()),
        "ci95_low": float(np.percentile(means, 2.5)),
        "ci95_high": float(np.percentile(means, 97.5)),
    }


def summarise(cases: pd.DataFrame) -> dict:
    ok = cases[cases["status"] == "ok"].copy()
    for col in ["ours_top1", "ours_top3", "last_top1", "last_top3", "justified"]:
        ok[col] = ok[col].astype(float)
    metrics = [
        "ours_top1", "ours_top3", "last_top1", "last_top3", "random_top1", "random_top3",
        "labelled_share", "si_if_blamed_alone",
    ]
    out = {
        "cases_total": int(len(cases)),
        "cases_evaluated": int(len(ok)),
        "excluded_by_reason": cases.loc[cases["status"] != "ok", "status"].value_counts().to_dict(),
        "matches": int(ok["game_id"].nunique()),
        "goals": int(ok["goal"].sum()),
        "metrics": {m: bootstrap_mean(ok, m) for m in metrics},
        "labelled_share_median": float(ok["labelled_share"].median()),
        "si_if_blamed_alone_verdicts": ok["verdict_if_blamed_alone"].value_counts().to_dict(),
        "justified_cases": int(ok["justified"].sum()),
        "justified_cases_unfair_flags": int(
            (ok["justified"].astype(bool) & (ok["verdict_if_blamed_alone"] == Verdict.UNFAIR.value)).sum()
        ),
        "goals_only": {
            m: float(ok.loc[ok["goal"], m].astype(float).mean())
            for m in ["ours_top3", "last_top3", "labelled_share"]
        },
        "method_note": (
            "On-ball responsibility only (public event data has no player positions). "
            "VAEP trained on Serie A and Bundesliga 2015/16; evaluated on international "
            "tournaments. No Premier League data used."
        ),
    }
    return out


def main() -> None:
    rated = pd.read_parquet(DATA_DIR / "test_rated.parquet")
    errors = pd.concat(
        [pd.read_parquet(p) for p in sorted((DATA_DIR / "test").glob("*.errors.parquet"))],
        ignore_index=True,
    )
    cases = evaluate_cases(rated, errors)
    summary = summarise(cases)
    RESULTS_DIR.mkdir(exist_ok=True)
    cases.drop(columns=["_tiebreak"], errors="ignore").to_csv(RESULTS_DIR / "cases.csv", index=False)
    (RESULTS_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
