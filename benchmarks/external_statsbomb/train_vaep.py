"""Train the action value model (VAEP) on club competitions and rate the test competitions.

Training and test competitions never overlap, so every rated test action comes from a match
the model has never seen.

Usage:
    uv run python benchmarks/external_statsbomb/train_vaep.py
"""

from __future__ import annotations

import json
import pickle
import warnings
from pathlib import Path

import pandas as pd
from socceraction.vaep import VAEP
from tqdm import tqdm

warnings.filterwarnings("ignore")

DATA_DIR = Path(__file__).resolve().parents[2] / ".data" / "statsbomb"
MODEL_PATH = DATA_DIR / "vaep_club.pkl"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def load_split(split: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    folder = DATA_DIR / split
    games = pd.concat([pd.read_parquet(p) for p in sorted(folder.glob("*.games.parquet"))])
    actions = pd.concat([pd.read_parquet(p) for p in sorted(folder.glob("*.actions.parquet"))])
    return games.reset_index(drop=True), actions.reset_index(drop=True)


def _game_actions(actions: pd.DataFrame, game_id: int) -> pd.DataFrame:
    a = actions[actions["game_id"] == game_id]
    return a.sort_values(["period_id", "action_id"]).reset_index(drop=True)


def train(games: pd.DataFrame, actions: pd.DataFrame) -> VAEP:
    model = VAEP(nb_prev_actions=3)
    xs, ys = [], []
    for game in tqdm(games.itertuples(index=False), total=len(games), desc="features"):
        g = pd.Series(game._asdict())
        a = _game_actions(actions, g.game_id)
        if a.empty:
            continue
        xs.append(model.compute_features(g, a))
        ys.append(model.compute_labels(g, a))
    x, y = pd.concat(xs, ignore_index=True), pd.concat(ys, ignore_index=True)
    model.fit(x, y, learner="xgboost", val_size=0.2)
    return model


def rate(model: VAEP, games: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for game in tqdm(games.itertuples(index=False), total=len(games), desc="rating"):
        g = pd.Series(game._asdict())
        a = _game_actions(actions, g.game_id)
        if a.empty:
            continue
        values = model.rate(g, a)
        parts.append(pd.concat([a, values.reset_index(drop=True)], axis=1))
    return pd.concat(parts, ignore_index=True)


def main() -> None:
    train_games, train_actions = load_split("train")
    print(f"train: {len(train_games)} games, {len(train_actions)} actions")
    model = train(train_games, train_actions)
    MODEL_PATH.write_bytes(pickle.dumps(model))

    test_games, test_actions = load_split("test")
    print(f"test: {len(test_games)} games, {len(test_actions)} actions")

    # Held-out quality of the two probability models on the test competitions.
    xs, ys = [], []
    for game in test_games.itertuples(index=False):
        g = pd.Series(game._asdict())
        a = _game_actions(test_actions, g.game_id)
        if not a.empty:
            xs.append(model.compute_features(g, a))
            ys.append(model.compute_labels(g, a))
    scores = model.score(pd.concat(xs, ignore_index=True), pd.concat(ys, ignore_index=True))
    print("held-out scores:", scores)

    rated = rate(model, test_games, test_actions)
    rated.to_parquet(DATA_DIR / "test_rated.parquet")

    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "vaep_model_quality.json").write_text(
        json.dumps(
            {
                "train_games": int(len(train_games)),
                "test_games": int(len(test_games)),
                "held_out_scores": scores,
            },
            indent=2,
            default=float,
        )
    )


if __name__ == "__main__":
    main()
