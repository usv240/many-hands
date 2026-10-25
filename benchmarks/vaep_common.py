"""Shared helpers for training and applying the action value model (VAEP) on SPADL actions."""

from __future__ import annotations

import pandas as pd
from socceraction.vaep import VAEP
from tqdm import tqdm


def game_actions(actions: pd.DataFrame, game_id) -> pd.DataFrame:
    a = actions[actions["game_id"] == game_id]
    return a.sort_values(["period_id", "action_id"]).reset_index(drop=True)


def train_vaep(games: pd.DataFrame, actions: pd.DataFrame, val_size: float = 0.2) -> VAEP:
    model = VAEP(nb_prev_actions=3)
    xs, ys = [], []
    for game in tqdm(games.itertuples(index=False), total=len(games), desc="features"):
        g = pd.Series(game._asdict())
        a = game_actions(actions, g.game_id)
        if a.empty:
            continue
        xs.append(model.compute_features(g, a))
        ys.append(model.compute_labels(g, a))
    model.fit(pd.concat(xs, ignore_index=True), pd.concat(ys, ignore_index=True),
              learner="xgboost", val_size=val_size)
    return model


def rate_all(model: VAEP, games: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for game in tqdm(games.itertuples(index=False), total=len(games), desc="rating"):
        g = pd.Series(game._asdict())
        a = game_actions(actions, g.game_id)
        if a.empty:
            continue
        parts.append(pd.concat([a, model.rate(g, a).reset_index(drop=True)], axis=1))
    return pd.concat(parts, ignore_index=True)
