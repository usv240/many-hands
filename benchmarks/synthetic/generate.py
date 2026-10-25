"""Generate the synthetic league: a training split (no ground truth) and a benchmark split
(with counterfactual ground truth for every decisive moment).

Everything is seeded, so the same command always produces the same matches.

Usage:
    uv run python benchmarks/synthetic/generate.py --train 80 --bench 60
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages"))

from simulator.league import league  # noqa: E402
from simulator.match import simulate  # noqa: E402

DATA_DIR = ROOT / ".data" / "synthetic"


def fixture(k: int, n_teams: int) -> tuple[int, int]:
    h, a = k % n_teams, (k // n_teams + k + 1) % n_teams
    return (h, a) if h != a else (h, (a + 1) % n_teams)


def one(args: tuple[str, int, int]) -> dict:
    split, game_id, seed = args
    teams = league()
    h, a = fixture(game_id, len(teams))
    r = simulate(teams[h], teams[a], game_id, seed, ground_truth=(split == "bench"))
    return {"split": split, "game": r.game, "actions": r.actions, "positions": r.positions,
            "moments": r.moments}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=int, default=80)
    parser.add_argument("--bench", type=int, default=60)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    jobs = [("train", 10_000 + k, 50_000 + k) for k in range(args.train)]
    jobs += [("bench", 20_000 + k, 60_000 + k) for k in range(args.bench)]
    out: dict[str, dict[str, list]] = {s: {"games": [], "actions": [], "positions": [], "moments": []}
                                       for s in ("train", "bench")}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(one, j) for j in jobs]
        for f in tqdm(as_completed(futures), total=len(futures), desc="simulating"):
            r = f.result()
            o = out[r["split"]]
            o["games"].append(r["game"])
            o["actions"].append(r["actions"])
            o["positions"].append(r["positions"])
            o["moments"].extend(r["moments"])

    for split, o in out.items():
        d = DATA_DIR / split
        d.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(o["games"]).to_parquet(d / "games.parquet")
        pd.concat(o["actions"], ignore_index=True).to_parquet(d / "actions.parquet")
        pd.concat(o["positions"], ignore_index=True).to_parquet(d / "positions.parquet")
        (d / "moments.json").write_text(json.dumps(o["moments"], indent=1))
        n_truth = sum(1 for m in o["moments"] if m["truth"])
        print(f"{split}: {len(o['games'])} games, {len(o['moments'])} decisive moments, "
              f"{n_truth} with at least one measured cause")

    teams = league()
    roster = [dict(team_id=t.tid, team=t.name, short=t.short, player_id=p.pid, name=p.name,
                   shirt=p.shirt, role=p.role) for t in teams for p in t.players]
    pd.DataFrame(roster).to_parquet(DATA_DIR / "roster.parquet")


if __name__ == "__main__":
    main()
