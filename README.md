# Many Hands

**Microsoft Foundry agents trace every goal back through every player who caused it, catch scapegoating lines before they air, and rewrite them fairly, about 4 seconds after the goal.**

**Live:** https://ca-manyhands-7kzrrno7qr6zo.orangedune-9d42108b.eastus2.azurecontainerapps.io · Judges: open **Judges start here** in the header for a three-minute path.

| On a match day | |
|---|---|
| **4.0 s median** (5.1 s p95) | from a goal reaching Azure Event Hubs to a fair, checked line and five audience versions, measured live on every goal |
| **About 51 a season** | moments in a 380-match season where a one-culprit story would be unfair (0.5 provider-labelled errors per match, 27% of them shared), estimated from real tournament data |
| **0 of 130** | real cases where one player truly was to blame that it wrongly called unfair: fair both ways |

Built for the Inside the Game Developer Hackathon (Microsoft and the Premier League). All match data in the product is synthetic and fictional.

## Why
July 2021, the Euro 2020 final: England lose on penalties, and within hours the three young players who missed are racially abused online. Football is a team game, but its stories name one culprit. Reporters' ratings are biased by the result (Kausel et al. 2019), and online abuse of Premier League players peaks right after key moments, with 68 percent of players abused in half a season (Alan Turing Institute for Ofcom, 2022). AI recaps now write those stories at scale. Platforms remove abuse after it is posted. Many Hands works earlier, on the story itself.

## Try it in three minutes
1. **Home:** press "Fix it with the agents, live". A pundit's one-culprit line goes to the agents on Microsoft Foundry and comes back fair, with every agent step and its timing.
2. **Studio:**
   - **Evidence check:** the agent replays the one action the verdict depends on and asks you a single question.
   - **AI desk:** send any line to the agents.
   - **Live feed:** kick off a match through Azure Event Hubs and watch goals wake the agents by themselves.
   - **Pre-air queue:** an Unfair line needs a typed reason to air, and the hash-chained log shows Verify and Tamper.
3. **Results:** two benchmarks, a named baseline, a negative control, a red team, and the limits, as numbers.

## What it does: the five stages the brief requires
| Stage | Many Hands |
|---|---|
| Ingest | Match events stream through **Azure Event Hubs** (from the calibrated simulator, or your own file) |
| Interpret | Every action valued with VAEP (Decroos et al. 2019); each player's share of every goal |
| Explain | Why this player and not that one; the unsung attacker; an evidence check a person settles in seconds |
| Render | Timed graphics: chain replay, responsibility bars, a lower third that only shows approved lines |
| Personalize | Analyst, casual fan of each club, featured player and Spanish versions, each checked separately |

**The check** is the Scapegoat Index: the gap between who a line blames and who the evidence says contributed, from 0 (fair) to 1 (fully misplaced). Fair below 0.20, Watch to 0.40, Unfair above. **The score is always computed in code, never by a model**, so text that tries to instruct the AI cannot change it.

## The agents (Microsoft Agent Framework on Microsoft Foundry, gpt-5-mini)
```
goal on Azure Event Hubs ──> Investigator ──> Narrator <──> Auditor ──> Personalizer ──> Producer (a person)
                              ledger tools     writes        rules + gpt-5-mini reader,   5 versions,    approves; Unfair
                              (also over MCP)  and rewrites  score in code, max 2         each audited   needs a reason
                                                             revisions, fails closed
```
- **Investigator** gathers evidence with the same ledger tools the MCP server exposes.
- **Narrator** writes or rewrites from the facts only; the Auditor also checks every scoreline against the real score.
- **Auditor** reads with rules plus a gpt-5-mini reader whose quotes are verified in code. It sends unfair lines back with reasons, at most twice, then uses a template that is fair by construction. If it cannot run, nothing airs.
- **Personalizer** writes five audience versions, and every one is audited again.
- **The agent directs the producer:** before airing, it chooses the deciding action, replays it, and asks one question. "No" removes a data error and recomputes; "Can't tell" makes any line blaming that player need a typed reason.
- **Hot Take and Judge** form a red team: an attacker tries to sneak scapegoating past the Auditor, and a separate judge decides. Every attack is now a permanent test.

## Evidence
| Benchmark | Cases | Result |
|---|---|---|
| [External](benchmarks/external_statsbomb/RESULTS.md): StatsBomb Open Data, provider-labelled errors, Premier League excluded | 178 | 0 of 130 false Unfair flags on justified blame; 1 in 4 single-culprit lines would be unfair; last-touch names the culprit more often (90% vs 76%) |
| [Synthetic](benchmarks/synthetic/RESULTS.md): 60 fictional matches with counterfactual ground truth (each mistake replayed 100 times with and without it) | 483 moments | Shared-blame moments: 0.37 vs 0.52 distance to truth against last-touch, 0 false flags; calibration 12 of 13 statistics within 15% of 906 real matches |
| [Red team](benchmarks/redteam/RESULTS.md): 120 attacker lines, judged by a separate agent | 83 unfair | Held-out match 23 of 23 caught with the reader (1 of 23 with rules alone); 0 of 63 fair controls flagged; 7 of 36 borderline lines flagged |

**Measured limits:**
- Last-touch names the main culprit more often than our ledger. Our edge is how much, not who.
- Off-ball positional blame did not help at any weight, so its weight is 0.
- The reader and the judge share a base model, and catch rates vary between runs (77 to 79 of 83).
- Rules alone miss most implied blame.

**Rerun every number:** `uv run python packages/sdk/manyhands/cli.py verify --suite synthetic` (and `--suite external`), plus the commands in each RESULTS file.

## Microsoft technologies, and what each one does here
| Technology | Job |
|---|---|
| **Microsoft Foundry** | gpt-5-mini deployment for the Narrator, Personalizer, Auditor's reader and the red team; project tracing to Application Insights |
| **Microsoft Agent Framework** | The workflow graph: Investigator, Narrator and Auditor loop, Personalizer, fallbacks, fail-closed |
| **Azure Event Hubs** | The live match feed; a goal on the stream wakes the agents (Entra ID only, no connection strings) |
| **Azure Container Apps** | One app serving the website, REST API and live stream; always one warm replica |
| **Azure Container Registry** | Images built in the cloud |
| **Managed identity, Entra ID** | No keys anywhere: Foundry, Event Hubs and the registry all use identities |
| **Application Insights, Log Analytics** | Monitoring and traces |
| **MCP** | The ledger as 8 typed tools for GitHub Copilot or any MCP client |
| **GitHub Actions** | CI on every push, plus a **fairness gate** action that fails a pull request when a generated line scapegoats |
| **Azure Developer CLI and Bicep** | `azd up` provisions and deploys everything |

## Use it
- **REST API:** `POST /v1/audit` (`deep: true` adds the reader), `POST /v1/broadcast` (the full agent workflow), `POST /v1/matches/{id}/kickoff`, `GET /v1/matches/{id}/live` (Server-Sent Events), `GET /v1/metrics`. OpenAPI at `/docs`.
- **MCP server:** `uv run python services/api/mcp_server.py` (stdio) or `--http`.
- **GitHub Action:**
  ```yaml
  - uses: usv240/many-hands/actions/fairness-gate@main
    with:
      files: out/recaps/*.json
  ```
- **Command line:** `uv run python packages/sdk/manyhands/cli.py audit 20003-300 "Number 8's howler cost them the goal."`
- **Bring your own:** match files (rated SPADL CSV) in the browser, your own sentences, and your own fairness limits.

## Run it yourself
```
uv sync
uv run uvicorn services.api.app:app --port 8000          # API, website (after building apps/web) and live feed
cd apps/web && npm ci && npm run dev                       # the website alone, works with no server
azd up                                                     # everything on Azure
```
Tests: **141 Python** (unit, property-based, API, agent workflow, live feed, and 83 red-team regressions) and **159 web**, including 154 cases where the browser engine must match the Python engine exactly. CI runs them on every push.

## Repository
```
apps/web                  website: React, Fluent UI 9, browser engine identical to the server's
services/agents           Agent Framework workflow, Foundry client, the Auditor's reader
services/api              FastAPI, live feed (Event Hubs), MCP server
packages/ledger_core      action values, responsibility, chains, the match ledger
packages/narrative_core   blame extraction, shared lexicon, Scapegoat Index, audit
packages/simulator        calibrated fictional league with counterfactual ground truth
actions/fairness-gate     the GitHub Action
benchmarks/               external, synthetic and red-team benchmarks with results
infra/                    Bicep for azd
docs/                     design pack and audits
```

## Data and licences
Product and demo data are synthetic, generated by `packages/simulator`, with fictional clubs and players. External validation uses StatsBomb Open Data (data provided by StatsBomb) from non-Premier League competitions; it is downloaded by script and never committed. Libraries: socceraction (MIT), kloppy (BSD), FastAPI (MIT), Fluent UI (MIT), Microsoft Agent Framework (MIT). This project: MIT.
