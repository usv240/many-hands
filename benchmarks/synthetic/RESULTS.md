# Synthetic benchmark: results (updated Oct 26 2026)

The only data in football where the true cause of a goal is known, because we built it that way.

## Setup
- **League:** 8 fictional clubs, 88 players, all invented and seeded. 80 training matches, 60 benchmark matches.
- **Calibration:** 12 of 13 per-match statistics within 15 percent of 906 real matches (StatsBomb Open Data, non Premier League). Table: `results_calibration.csv`.
- **Ground truth:** for each of 824 decisive moments, every defending mistake in the build-up (a lost ball, or a defender out of position) was replayed 100 times with and without that one mistake, using paired random numbers. The drop in danger is that player's true contribution. 483 moments had at least one measurable cause.
- **The ledger never sees the truth.** It only sees actions and positions, as a data provider would supply them. The action value model (VAEP) was trained on the separate 80 training matches.

## The question that matters: does the check catch truly unfair lines? (`detection.py`)
A pundit's one-culprit line blames the last defender to lose the ball. It is **truly unfair** when, against the true causes, it scores above 0.40. The ledger's settings were chosen on 30 benchmark matches; these numbers are from the **other 29, held out**.

| On 239 held-out pundit lines (42 truly unfair) | Result | 95% interval |
|---|---|---|
| When the check calls a line **Unfair**, it is truly unfair | **77%** (10 of 13) | 53 to 100 |
| Fair lines called Unfair | **1.5%** (3 of 197) | 0 to 3 |
| Truly unfair lines called Unfair outright | 24% (10 of 42) | 11 to 41 |
| Truly unfair lines **sent to a person** (Watch or Unfair, not aired automatically) | **60%** (25 of 42) | 45 to 75 |
| Lines sent to a person that are truly unfair | 50% (25 of 50) | 36 to 64 |
| Fair lines sent to a person | 13% (25 of 197) | 8 to 17 |
| How well the score ranks unfair lines above fair ones (AUC) | 0.72 | |

**Negative control, against the truth:** when one player truly caused 60 percent or more, a line blaming that player alone was wrongly called Unfair in **6.1%** of cases (14 of 228), against 7.5% for the last-touch rule.

**Baseline:** the last-touch rule gives the blamed player 100 percent every time, so it never flags a one-culprit line: it catches none of the 42.

## Ranking players (all 60 matches, 95 percent bootstrap intervals over matches)
| Metric | Many Hands | Last-touch baseline |
|---|---|---|
| Distance from the true blame distribution (0 is perfect) | 0.148 (0.13 to 0.17) | 0.148 (0.13 to 0.17) |
| Main culprit ranked first | 78.9% (75 to 82) | 85.1% (82 to 88) |
| Main culprit in top three | 83.0% (79 to 87) | 92.8% (90 to 95) |
| Deserved blame wrongly called Unfair (441 cases) | 6.1% (27 cases) | 6.8% (30 cases) |

### When blame is genuinely shared (42 moments where no player held 60 percent)
| Metric | Many Hands | Last-touch |
|---|---|---|
| Distance from the truth | **0.367** | 0.517 |
| Main culprit ranked first | 59.5% | 61.9% |
| A "blame the last touch" story, scored against the truth | | **0.517, Unfair** |

## What this means, honestly
1. **When it says Unfair, it is usually right; it does not catch most unfair lines on its own.** Three in four Unfair calls are correct and fair lines are almost never called Unfair, but only a quarter of truly unfair lines are called Unfair outright. Six in ten are at least sent to a person. That is why the product routes, explains and asks; it does not decide alone.
2. **Most conceded chances have one dominant cause.** 441 of 483 moments (91 percent). The real data says the same (median labelled share 100 percent).
3. **The simple rule is a strong baseline for *who*.** Last-touch names the main culprit more often than our ledger. Our value is *how much*: when blame is shared, the ledger is markedly closer to the truth (0.37 vs 0.52), and a last-touch story is Unfair in every one of those cases.
4. **Missing evidence is not innocence.** In about 1 move in 10 the ledger counts no lost ball. Scoring blame there as Unfair produced most of the wrong calls (deserved blame wrongly flagged 21 percent). The product now says "the evidence cannot tell" and sends the line to a person. That rule was checked on the tuning half (18 such moments, none truly unfair) before the held-out half was scored.
5. **Off-ball positional blame did not help.** At every weight it moved results further from the truth, so its weight is 0. A measured limit.
6. **How the defaults were chosen.** Counting only actions that lost the ball, with the final turnover weighted double, was chosen by grid search on ground truth. The first search used all 60 matches; `detection.py` repeats it on half the matches only, picks a near-identical setting (distance 0.144 vs 0.145 for the shipped one), and reports the shipped setting on the other half.

## Rerun
```
uv run python benchmarks/synthetic/generate.py --train 80 --bench 60
uv run python benchmarks/synthetic/evaluate.py
uv run python benchmarks/synthetic/detection.py
uv run python benchmarks/synthetic/tune_ledger.py
```
