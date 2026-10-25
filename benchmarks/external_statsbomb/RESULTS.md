# External benchmark: results (updated Oct 17 2026)

Data provided by StatsBomb. Premier League excluded. On-ball responsibility only, because public event data has no player positions. Ledger defaults are the ones chosen on the synthetic ground truth (count only actions that lost the ball; final turnover weighted double).

## Setup
- **Action value model (VAEP):** trained on 414 club matches (Serie A and Bundesliga 2015/16). On 492 held-out international matches it scores AUROC 0.81 for "scores soon" and 0.80 for "concedes soon".
- **Cases:** 275 provider-labelled errors. 178 evaluated, 57 of them goals.
- **Excluded:** 30 with no opposition shot linked to the error; 67 where no defending action in the chain lost the ball (the "Error" label is not itself an action in SPADL, so the mistake is only visible when it appears as a failed pass or touch).

## Numbers (95 percent bootstrap intervals over matches)
| Metric | Many Hands | Last-touch baseline |
|---|---|---|
| Labelled player ranked first | 75.8% (69 to 82) | 89.9% (85 to 94) |
| Labelled player in top three | 79.8% (73 to 86) | 92.1% (88 to 96) |
| Labelled player's share of responsibility | mean 74.7% (68 to 81), median 100% | 100% by definition |

**Negative control (justified blame):** in 130 of 178 cases the labelled player holds at least 60 percent and is ranked first. A line blaming that player alone was flagged Unfair in **0 of 130**.

**A line blaming only the labelled player, scored against the evidence:**
| Verdict | Cases | Share |
|---|---|---|
| Fair | 124 | 70% |
| Watch | 6 | 3% |
| Unfair | 48 | 27% |

## What this means, honestly
1. **The expert label is usually right.** The median labelled player carries all of the on-ball responsibility. "The blamed player was innocent" is not supported, and we do not claim it.
2. **Fair both ways holds.** Deserved blame was never flagged as unfair (0 of 130).
3. **About 1 in 4 single-culprit stories would be unfair** (48 of 178), because a teammate's lost ball in the same move mattered as much or more.
4. **Last-touch names the culprit more often.** It is the right baseline, and on *who* it wins. It is wrong on *how much* in those 48 cases, because it gives 100 percent every time.
5. **This understates shared blame.** Without positions, off-ball causes are invisible here.

## Headline
> On 178 real, provider-labelled errors, Many Hands never flagged deserved blame as unfair (0 of 130), and caught the 1 in 4 where a single-culprit story would have been.
