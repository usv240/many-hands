# External benchmark: provider-labelled errors

**Question:** when a professional data provider labels one player's mistake as the error behind a shot, does our responsibility model agree, and how much of the danger did that player really cause?

**Data:** StatsBomb Open Data, data provided by StatsBomb. Premier League competitions are excluded by design. The data is downloaded by the script and never committed. Real data is used only to validate the model; the product itself runs on synthetic matches.

| Split | Competitions | Purpose |
|---|---|---|
| Train | Serie A 2015/16, 1. Bundesliga 2015/16 | Train the action value model (VAEP) |
| Test | FIFA World Cup 2018 and 2022, UEFA Euro 2020 and 2024, Copa America 2024, Africa Cup of Nations 2023, Women's World Cup 2019 and 2023, UEFA Women's Euro 2022 and 2025 | Every labelled error evaluated here |

No match appears in both splits.

## Run it
```
uv sync
uv run python benchmarks/external_statsbomb/prepare.py      # download and convert (about 15 minutes)
uv run python benchmarks/external_statsbomb/train_vaep.py   # train and rate
uv run python benchmarks/external_statsbomb/evaluate.py     # metrics with 95 percent intervals
```
Results land in `results/summary.json` and `results/cases.csv`.

## Metrics
- **A. Top-1 and top-3 recall:** the labelled player is ranked first, or in the top three, by our ledger. Compared with last-touch blame and a random pick.
- **B. Labelled player's share:** their share of the computed responsibility for the chain.
- **B2. Scapegoat Index if blamed alone:** what a line naming only the labelled player would score.
- **Justified cases:** where one player holds 60 percent or more and is the labelled player. Blaming them alone must never be flagged Unfair.

## Known limits
- Public event data has no player positions, so only on-ball responsibility is measured here. Off-ball responsibility is measured on synthetic matches.
- The chain starts at the possession containing the error. Errors made long before the shot are harder to attribute.
