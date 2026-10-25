# Synthetic benchmark: results (Oct 17 2026)

The only data in football where the true cause of a goal is known, because we built it that way.

## Setup
- **League:** 8 fictional clubs, 88 players, all invented and seeded. 80 training matches, 60 benchmark matches.
- **Calibration:** 12 of 13 per-match statistics within 15 percent of 906 real matches (StatsBomb Open Data, non Premier League). Table: `results_calibration.csv`.
- **Ground truth:** for each of 824 decisive moments, every defending mistake in the build-up (a lost ball, or a defender out of position) was replayed 100 times with and without that one mistake, using paired random numbers. The drop in danger is that player's true contribution. 483 moments had at least one measurable cause.
- **The ledger never sees the truth.** It only sees actions and positions, as a data provider would supply them. The action value model (VAEP) was trained on the separate 80 training matches.

## Numbers (95 percent bootstrap intervals over matches)
| Metric | Many Hands | Last-touch baseline |
|---|---|---|
| Distance from the true blame distribution (0 is perfect) | 0.148 (0.13 to 0.17) | 0.148 (0.13 to 0.17) |
| Main culprit ranked first | 78.9% (75 to 82) | 85.1% (82 to 88) |
| Main culprit in top three | 83.0% (79 to 87) | 92.8% (90 to 95) |
| False Unfair flags when one player truly held 60%+ (441 cases) | 18.6% (15 to 22) | 6.2% (4 to 8) |

### When blame is genuinely shared (42 moments where no player held 60 percent)
| Metric | Many Hands | Last-touch |
|---|---|---|
| Distance from the truth | **0.367** | 0.517 |
| Main culprit ranked first | 59.5% | 61.9% |
| False Unfair flags | 0 | 0 |
| A "blame the last touch" story, scored against the truth | | **0.517, Unfair** |

## What this means, honestly
1. **Most conceded chances have one dominant cause.** 441 of 483 moments (91 percent) had one player holding 60 percent or more of the true responsibility. The real data said the same (median labelled share 100 percent). The product must say this plainly.
2. **The simple rule is a strong baseline for *who*.** Last-touch names the main culprit more often than our ledger. We publish that rather than hide it.
3. **The ledger's value is *how much*.** When blame really is shared, Many Hands is markedly closer to the truth (0.37 vs 0.52), and a last-touch story would be Unfair in every one of those cases. That is 1 moment in 7 here, and about 1 in 3.7 on real data.
4. **Off-ball positional blame did not help.** At every weight it moved results further from the truth, so the default weight is 0. Only 86 moments had a measurable off-ball cause, and our position-based method is too crude to find them. This is a measured limit, not a feature.
5. **The benchmark improved the ledger.** Grid-searching on the ground truth (`tune_ledger.py`) showed that counting only actions that lost the ball, with the final turnover weighted double, cut the distance to the truth from 0.228 to 0.148 and false flags from 30 to 19 percent. Those are now the defaults.

## Rerun
```
uv run python benchmarks/synthetic/generate.py --train 80 --bench 60
uv run python benchmarks/synthetic/evaluate.py
uv run python benchmarks/synthetic/tune_ledger.py
```
