"""Compare simulated match statistics with real football (StatsBomb Open Data, 906 matches).

Usage:
    uv run python benchmarks/synthetic/calibrate.py --matches 20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages"))

from simulator.league import league  # noqa: E402
from simulator.match import simulate  # noqa: E402

TARGETS = json.loads((Path(__file__).parent / "real_targets.json").read_text())
SPADL_TO_SIM = {"dribble": "carries", "pass": "passes", "shot": "shots", "cross": "crosses",
                "take_on": "take_ons", "tackle": "tackles", "interception": "interceptions",
                "clearance": "clearances", "keeper_save": "keeper_saves"}


def match_stats(actions: pd.DataFrame) -> dict[str, float]:
    out = {"actions": float(len(actions))}
    for spadl_name, key in SPADL_TO_SIM.items():
        out[key] = float((actions.type_name == spadl_name).sum())
    passes = actions[actions.type_name == "pass"]
    out["pass_completion"] = float((passes.result_name == "success").mean())
    out["pass_length_m"] = float(np.hypot(passes.end_x - passes.start_x,
                                          passes.end_y - passes.start_y).mean())
    shots = actions[actions.type_name == "shot"]
    out["goals"] = float((shots.result_name == "success").sum())
    return out


def run(n: int, seed0: int = 1000) -> pd.DataFrame:
    teams = league()
    rows = []
    for k in range(n):
        h, a = k % len(teams), (k * 3 + 1) % len(teams)
        if h == a:
            a = (a + 1) % len(teams)
        r = simulate(teams[h], teams[a], game_id=k, seed=seed0 + k, ground_truth=False)
        rows.append(match_stats(r.actions))
    return pd.DataFrame(rows)


def report(sim: pd.DataFrame) -> pd.DataFrame:
    table = []
    for key, real in TARGETS["per_match"].items():
        s = float(sim[key].mean())
        table.append({"statistic": key, "real": real, "simulated": round(s, 3),
                      "difference_pct": round(100 * (s - real) / real, 1)})
    return pd.DataFrame(table)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", type=int, default=20)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    table = report(run(args.matches))
    print(table.to_string(index=False))
    within = (table.difference_pct.abs() <= 15).sum()
    print(f"\n{within} of {len(table)} statistics within 15 percent of real football")
    if args.out:
        args.out.write_text(table.to_csv(index=False))


if __name__ == "__main__":
    main()
