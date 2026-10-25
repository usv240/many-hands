"""Download StatsBomb Open Data, convert it to SPADL actions, and extract labelled errors.

Only competitions outside the Premier League are used, and only to validate our model.
Raw JSON is never written to disk: each match is converted in memory and only compact
Parquet tables are kept under .data/ (git-ignored).

Data provided by StatsBomb (https://github.com/statsbomb/open-data).

Usage:
    uv run python benchmarks/external_statsbomb/prepare.py --split all
"""

from __future__ import annotations

import argparse
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import socceraction.spadl as spadl
from socceraction.data.statsbomb import StatsBombLoader
from tqdm import tqdm

warnings.filterwarnings("ignore", category=UserWarning)  # statsbomb credential warnings

DATA_DIR = Path(__file__).resolve().parents[2] / ".data" / "statsbomb"

# Training competitions (club football) and test competitions (international tournaments)
# never overlap, so the action value model is never evaluated on matches it was trained on.
TRAIN = [
    ("Serie A", "2015/2016"),
    ("1. Bundesliga", "2015/2016"),
]
TEST = [
    ("FIFA World Cup", "2018"),
    ("FIFA World Cup", "2022"),
    ("UEFA Euro", "2020"),
    ("UEFA Euro", "2024"),
    ("Copa America", "2024"),
    ("African Cup of Nations", "2023"),
    ("Women's World Cup", "2019"),
    ("Women's World Cup", "2023"),
    ("UEFA Women's Euro", "2022"),
    ("UEFA Women's Euro", "2025"),
]
EXCLUDED_COMPETITIONS = {"Premier League"}

# An error is linked to the first opposition shot within this many events after it.
SHOT_LOOKAHEAD_EVENTS = 40


def _shot_outcome(extra: object) -> tuple[str | None, float | None]:
    if not isinstance(extra, dict):
        return None, None
    shot = extra.get("shot", {})
    return shot.get("outcome", {}).get("name"), shot.get("statsbomb_xg")


def process_game(loader: StatsBombLoader, game: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (SPADL actions, labelled errors) for one match."""
    events = loader.events(game.game_id)
    actions = spadl.statsbomb.convert_to_actions(events, home_team_id=game.home_team_id)
    actions = spadl.add_names(actions)

    # Carry the StatsBomb possession number onto each action, for chain building.
    poss = events[["event_id", "possession"]].rename(columns={"event_id": "original_event_id"})
    actions = actions.merge(poss, on="original_event_id", how="left")

    ev = events.reset_index(drop=True)
    rows = []
    for i in ev.index[ev["type_name"] == "Error"]:
        err = ev.loc[i]
        shot_id, outcome, xg = None, None, None
        for j in range(i + 1, min(i + 1 + SHOT_LOOKAHEAD_EVENTS, len(ev))):
            nxt = ev.loc[j]
            if nxt["type_name"] == "Shot" and nxt["team_id"] != err["team_id"]:
                shot_id = nxt["event_id"]
                outcome, xg = _shot_outcome(nxt.get("extra"))
                break
        rows.append(
            {
                "game_id": game.game_id,
                "error_event_id": err["event_id"],
                "error_player_id": err["player_id"],
                "error_team_id": err["team_id"],
                "error_possession": err["possession"],
                "period_id": err["period_id"],
                "shot_event_id": shot_id,
                "shot_outcome": outcome,
                "shot_xg": xg,
            }
        )
    return actions, pd.DataFrame(rows)


def prepare(split: str, comps: list[tuple[str, str]], workers: int) -> None:
    loader = StatsBombLoader(getter="remote", creds={"user": None, "passwd": None})
    all_comps = loader.competitions()
    out_dir = DATA_DIR / split
    out_dir.mkdir(parents=True, exist_ok=True)

    for comp_name, season in comps:
        if comp_name in EXCLUDED_COMPETITIONS:
            raise ValueError(f"{comp_name} is excluded by design")
        slug = f"{comp_name}_{season}".replace(" ", "_").replace("/", "-").replace("'", "")
        target = out_dir / f"{slug}.actions.parquet"
        if target.exists():
            print(f"skip {slug} (already prepared)")
            continue
        sel = all_comps[
            (all_comps.competition_name == comp_name) & (all_comps.season_name == season)
        ]
        if sel.empty:
            print(f"not found: {comp_name} {season}")
            continue
        row = sel.iloc[0]
        games = loader.games(row.competition_id, row.season_id)

        actions_parts, error_parts = [], []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(process_game, loader, g): g.game_id for g in games.itertuples()}
            for fut in tqdm(as_completed(futures), total=len(futures), desc=slug):
                try:
                    a, e = fut.result()
                except Exception as exc:  # one bad match must not stop the run
                    print(f"  failed game {futures[fut]}: {exc}")
                    continue
                actions_parts.append(a)
                error_parts.append(e)

        actions = pd.concat(actions_parts, ignore_index=True)
        errors = pd.concat(error_parts, ignore_index=True) if error_parts else pd.DataFrame()
        games.to_parquet(out_dir / f"{slug}.games.parquet")
        errors.to_parquet(out_dir / f"{slug}.errors.parquet")
        actions.to_parquet(target)
        print(f"  {slug}: {len(games)} games, {len(actions)} actions, {len(errors)} errors")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["train", "test", "all"], default="all")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.split in ("test", "all"):
        prepare("test", TEST, args.workers)
    if args.split in ("train", "all"):
        prepare("train", TRAIN, args.workers)


if __name__ == "__main__":
    main()
