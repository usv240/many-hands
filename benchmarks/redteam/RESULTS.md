# Red team: results (Oct 25 2026)

**The question:** can a determined attacker get scapegoating past the Auditor?

## Setup
- **Hot Take** (attacker, gpt-5-mini on Microsoft Foundry) wrote 120 lines across 21 goals in 3 fictional matches. Each line reads like ordinary punditry, but pins the goal on a player the evidence does not support, and avoids obvious blame words.
- **Judge** (a separate agent, gpt-5-mini) said who each line blames and quoted the exact words. Code drops any quote that is not in the line, then computes the Judge's Scapegoat Index. 83 lines were rated Unfair and 36 Fair; the Fair ones are kept as hard negatives.
- **Auditor**, measured two ways: its word rules alone, and its rules plus a **gpt-5-mini reader** for implied blame. The score is computed in code either way, and the reader can add blame but never remove it.
- **Held-out match:** match 20045 was set aside before anything was learned.

## Numbers
| | Rules only | Rules plus reader |
|---|---|---|
| Held-out match: Judge-Unfair lines caught | 1 of 23 | **23 of 23** |
| All matches: Judge-Unfair lines caught | 7 of 83 | **79 of 83** (77 on a rerun) |
| Hard negatives (attacker lines the Judge rated Fair) flagged Unfair | 2 of 36 | 7 of 36 |
| Fair control lines (fair rewrites and neutral descriptions) flagged Unfair | 0 of 63 | **0 of 63** |

## What we tried first, and why we dropped it
Learning the attackers' phrasing into the word list caught 46 of 60 on the matches it learned from, but only **5 of 23 on the held-out match**. It memorised; it did not generalise. Some phrases it learned would also have flagged credit ("creates the gap"). We kept the experiment (`run.py --reuse`) and did not apply it.

## Honest limits
- The Judge and the reader are separate agents with different instructions, but both run on gpt-5-mini. Agreement between them is not independent human labelling.
- Model output varies: the same 83 attacks were caught 79 and then 77 times. The live regression test asserts at least 90 percent.
- The reader adds false flags on borderline lines (7 of 36 hard negatives versus 2 for rules). A producer still decides, and the line can air with a typed reason.
- The browser engine and `POST /v1/audit` without `deep` use the rules only, so they work with no AI at all. They catch explicit blame; implied blame needs the reader (`deep: true`, the Studio's AI desk, the live feed, and the GitHub Action by default).

## Every attack is a permanent test
`cases.json` holds all 83 attacks with their verified readings and the 36 hard negatives.
- `tests/test_redteam.py` re-scores every recorded attack on every commit, offline.
- With `MANYHANDS_LIVE=1` it also checks that the live reader still catches at least 90 percent.

## Rerun
```
uv run python benchmarks/redteam/run.py --per-moment 6        # new attacks, judged; writes attacks.json
uv run python benchmarks/redteam/eval_reader.py               # Auditor with and without the reader
MANYHANDS_LIVE=1 uv run pytest tests/test_redteam.py
```
