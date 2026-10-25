"""Grid-search the ledger's on-ball settings against the synthetic ground truth.

This is how the benchmark earns its keep: every setting is scored on cases whose true causes
are known, and the chosen defaults are written into the ledger with the numbers that justify them.

Usage:
    uv run python benchmarks/synthetic/tune_ledger.py
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages"))

from ledger_core import responsibility  # noqa: E402
from ledger_core.responsibility import last_touch_ranking, ranking  # noqa: E402
from narrative_core.scapegoat import Verdict, scapegoat_index, verdict  # noqa: E402

DATA_DIR = ROOT / ".data" / "synthetic" / "bench"
JUSTIFIED = 0.60


def tv(a: dict, b: dict) -> float:
    keys = set(a) | set(b)
    return 0.5 * sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys)


def main() -> None:
    rated = pd.read_parquet(DATA_DIR / "rated.parquet")
    moments = [m for m in json.loads((DATA_DIR / "moments.json").read_text()) if m["truth"]]
    by_game = {g: a.reset_index(drop=True) for g, a in rated.groupby("game_id")}
    chains = []
    for m in moments:
        a = by_game[m["game_id"]]
        c = a[(a.action_id >= m["window_start_action_id"]) & (a.action_id <= m["shot_action_id"])]
        chains.append((c, m["conceding_team_id"], m["truth"]))

    grid = itertools.product([0.0, 0.2, 0.4], [False, True], [1.0, 2.0, 4.0, 8.0])
    rows = []
    for min_fraction, only_failures, boost in grid:
        tvs, top1, top3, just_unfair, n_just = [], [], [], 0, 0
        for c, d, truth in chains:
            shares = responsibility.onball_blame(c, d, min_fraction=min_fraction, only_failures=only_failures,
                                    last_turnover_boost=boost)
            t_rank = ranking(truth)
            r = ranking(shares)
            tvs.append(tv(shares, truth))
            top1.append(bool(r) and r[0] == t_rank[0])
            top3.append(t_rank[0] in r[:3])
            if truth[t_rank[0]] >= JUSTIFIED:
                n_just += 1
                si = scapegoat_index({t_rank[0]: 1.0}, shares) if shares else 1.0
                just_unfair += verdict(si) is Verdict.UNFAIR
        rows.append(dict(min_fraction=min_fraction, only_failures=only_failures, boost=boost,
                         tv=sum(tvs) / len(tvs), top1=sum(top1) / len(top1),
                         top3=sum(top3) / len(top3), justified_unfair=just_unfair / n_just))
    # Baseline row.
    tvs, top1, ju, nj = [], [], 0, 0
    for c, d, truth in chains:
        last = last_touch_ranking(c.iloc[:-1], d)
        dist = {last[0]: 1.0} if last else {}
        t_rank = ranking(truth)
        tvs.append(tv(dist, truth))
        top1.append(bool(last) and last[0] == t_rank[0])
        if truth[t_rank[0]] >= JUSTIFIED:
            nj += 1
            ju += verdict(scapegoat_index({t_rank[0]: 1.0}, dist) if dist else 1.0) is Verdict.UNFAIR
    rows.append(dict(min_fraction="last-touch", only_failures="", boost="", tv=sum(tvs) / len(tvs),
                     top1=sum(top1) / len(top1), top3=float("nan"), justified_unfair=ju / nj))
    df = pd.DataFrame(rows).sort_values("tv")
    pd.set_option("display.width", 160)
    print(df.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
