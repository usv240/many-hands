"""Synthetic benchmark: does the responsibility model recover the true causes of each chance?

The simulator records, for every decisive moment, how much danger each mistake really added
(measured by replaying the attack with and without it). The ledger never sees that. It only
sees the same actions and positions a data provider would supply. We then compare:

  - Many Hands (on-ball action values plus off-ball positional blame)
  - on-ball only
  - last-touch blame (the simple rule that blames whoever lost the ball last)

against the truth, with 95 percent bootstrap intervals over matches.

Usage:
    uv run python benchmarks/synthetic/evaluate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "benchmarks"))

from ledger_core.offball import combine, offball_blame  # noqa: E402
from ledger_core.responsibility import last_touch_ranking, onball_blame, ranking  # noqa: E402
from narrative_core.scapegoat import Verdict, scapegoat_index, verdict  # noqa: E402
from vaep_common import rate_all, train_vaep  # noqa: E402

DATA_DIR = ROOT / ".data" / "synthetic"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
LAMBDAS = [0.0, 0.25, 0.5, 1.0, 2.0]
JUSTIFIED_SHARE = 0.60
BOOTSTRAP_DRAWS = 1000
SEED = 7


def tv(a: dict, b: dict) -> float:
    keys = set(a) | set(b)
    return 0.5 * sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys)


def evaluate(rated: pd.DataFrame, positions: pd.DataFrame, moments: list[dict]) -> pd.DataFrame:
    rows = []
    by_game = {g: a.reset_index(drop=True) for g, a in rated.groupby("game_id")}
    pos_by_game = {g: p for g, p in positions.groupby("game_id")} if "game_id" in positions else {}
    for m in moments:
        if not m["truth"]:
            continue
        a = by_game[m["game_id"]]
        chain = a[(a.action_id >= m["window_start_action_id"]) & (a.action_id <= m["shot_action_id"])]
        pos = pos_by_game.get(m["game_id"], positions)
        d = m["conceding_team_id"]
        truth = m["truth"]
        truth_rank = ranking(truth)
        on = onball_blame(chain, d)
        off = offball_blame(chain, pos, d)
        last = last_touch_ranking(chain.iloc[:-1], d)
        base = dict(game_id=m["game_id"], shot_action_id=m["shot_action_id"], goal=m["goal"],
                    xg=m["xg"], n_true_causes=len(truth), truth_top=truth_rank[0],
                    truth_top_share=truth[truth_rank[0]],
                    has_offball_truth=any(c["kind"] == "offball" and c["effect"] > 0 for c in m["causes"]))
        for lam in LAMBDAS:
            ours = combine(on, off, lam)
            r = ranking(ours)
            base[f"tv_lam{lam}"] = tv(ours, truth)
            base[f"top1_lam{lam}"] = bool(r) and r[0] == truth_rank[0]
            base[f"top3_lam{lam}"] = truth_rank[0] in r[:3]
            # Negative control: when one player truly dominates, blaming them alone must be allowed.
            # As in the product, no counted mistake means Watch (a person decides), never Unfair.
            base[f"justified_unfair_lam{lam}"] = bool(
                truth[truth_rank[0]] >= JUSTIFIED_SHARE and ours and
                verdict(scapegoat_index({truth_rank[0]: 1.0}, ours)) is Verdict.UNFAIR)
        last_dist = {last[0]: 1.0} if last else {}
        base["tv_last"] = tv(last_dist, truth)
        base["top1_last"] = bool(last) and last[0] == truth_rank[0]
        base["top3_last"] = truth_rank[0] in last[:3]
        base["justified_unfair_last"] = bool(
            truth[truth_rank[0]] >= JUSTIFIED_SHARE and last_dist and
            verdict(scapegoat_index({truth_rank[0]: 1.0}, last_dist)) is Verdict.UNFAIR)
        # Would the simple single-culprit story (blame the last touch) be unfair against the truth?
        base["last_touch_story_si"] = scapegoat_index(last_dist, truth) if last_dist else 0.0
        rows.append(base)
    return pd.DataFrame(rows)


def boot(df: pd.DataFrame, col: str) -> dict[str, float]:
    rng = np.random.default_rng(SEED)
    games = df["game_id"].unique()
    pg = df.groupby("game_id")[col].agg(["sum", "count"])
    means = []
    for _ in range(BOOTSTRAP_DRAWS):
        pick = pg.loc[rng.choice(games, size=len(games), replace=True)]
        means.append(pick["sum"].sum() / pick["count"].sum())
    return {"mean": float(df[col].astype(float).mean()),
            "ci95_low": float(np.percentile(means, 2.5)),
            "ci95_high": float(np.percentile(means, 97.5))}


def main() -> None:
    tr_games = pd.read_parquet(DATA_DIR / "train" / "games.parquet")
    b_games = pd.read_parquet(DATA_DIR / "bench" / "games.parquet")
    rated_path = DATA_DIR / "bench" / "rated.parquet"
    if rated_path.exists():  # the model and ratings only change when the data does
        rated = pd.read_parquet(rated_path)
    else:
        tr_actions = pd.read_parquet(DATA_DIR / "train" / "actions.parquet")
        model = train_vaep(tr_games, tr_actions)
        b_actions = pd.read_parquet(DATA_DIR / "bench" / "actions.parquet")
        rated = rate_all(model, b_games, b_actions)
        rated.to_parquet(rated_path)
    positions = pd.read_parquet(DATA_DIR / "bench" / "positions.parquet")
    moments = json.loads((DATA_DIR / "bench" / "moments.json").read_text())

    cases = evaluate(rated, positions, moments)
    for c in cases.columns:
        if cases[c].dtype == bool:
            cases[c] = cases[c].astype(float)
    metric_cols = [c for c in cases.columns
                   if c.startswith(("tv_", "top1_", "top3_", "justified_unfair_", "last_touch_story"))]
    metrics = {c: boot(cases, c) for c in metric_cols}
    best_lam = min(LAMBDAS, key=lambda lam: metrics[f"tv_lam{lam}"]["mean"])

    # Where the "many hands" question actually arises: the truth names more than one real cause.
    multi = cases[(cases["truth_top_share"] < JUSTIFIED_SHARE)]
    offball = cases[cases["has_offball_truth"] > 0]
    subsets = {
        "multi_cause_moments": {"n": int(len(multi)),
                                "metrics": {c: float(multi[c].mean()) for c in metric_cols}},
        "moments_with_offball_cause": {"n": int(len(offball)),
                                       "metrics": {c: float(offball[c].mean()) for c in metric_cols}},
    }
    summary = {
        "train_games": int(len(tr_games)),
        "bench_games": int(len(b_games)),
        "moments_with_truth": int(len(cases)),
        "goals": int(cases["goal"].sum()),
        "moments_with_offball_cause": int(cases["has_offball_truth"].sum()),
        "best_lambda": best_lam,
        "metrics": metrics,
        "subsets": subsets,
        "justified_cases": int((cases["truth_top_share"] >= JUSTIFIED_SHARE).sum()),
        "last_touch_story_unfair_share": float(
            (cases["last_touch_story_si"] > 0.40).mean()),
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    cases.to_csv(RESULTS_DIR / "cases.csv", index=False)
    (RESULTS_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
