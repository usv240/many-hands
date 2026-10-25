"""The Responsibility Ledger as an MCP server.

Any MCP client (GitHub Copilot in VS Code, an Agent Framework agent, a newsroom assistant) can
call these tools to trace a goal, score a sentence for scapegoating and get a fair rewrite.
Our own agents use this same server, so outside users get exactly the tools we rely on.

Run (Streamable HTTP, for remote clients):
    uv run python services/api/mcp_server.py --http --port 8010
Run (stdio, for local clients such as VS Code):
    uv run python services/api/mcp_server.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn
from mcp.server.mcpserver import MCPServer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages"))

from narrative_core.audit import audit as _audit  # noqa: E402
from narrative_core.extraction import RuleExtractor  # noqa: E402
from narrative_core.scapegoat import Policy  # noqa: E402

from services.api.app import native, store  # noqa: E402

mcp = MCPServer(
    "many-hands-ledger",
    instructions=(
        "Tools for fair football match intelligence. Start with list_matches, then get_chains "
        "for a match, then responsibility or audit_line for a chain. All data is synthetic."
    ),
)


@mcp.tool()
def list_matches() -> list[dict]:
    """List the fictional matches available, with scores and the number of decisive moments."""
    from services.api.app import matches
    return native(matches())


@mcp.tool()
def get_chains(game_id: int) -> list[dict]:
    """Decisive moments (goals and big chances) in a match, each with who was responsible
    for how much, the last-touch player, and the unsung attacker who created it."""
    from services.api.app import chains
    return native(chains(game_id))


@mcp.tool()
def get_chain(chain_id: str) -> dict:
    """Every action in the build-up to one decisive moment, with its value, plus the summary."""
    from services.api.app import chain
    return native(chain(chain_id))


@mcp.tool()
def responsibility(chain_id: str, method: str = "combined") -> dict:
    """Each defending player's share of responsibility for a moment (shares sum to 1).
    method: combined (default), vaep (on-ball action values only), lasttouch (baseline)."""
    from services.api.app import responsibility as resp
    return native(resp(chain_id, method))


@mcp.tool()
def counterfactual(chain_id: str, action_id: int) -> dict:
    """How much of the danger disappears if one defending loss in the chain is removed."""
    return native(store.ledger_for_chain(chain_id).counterfactual(chain_id, action_id))


@mcp.tool()
def extract_blame(chain_id: str, text: str) -> dict:
    """Who a sentence blames, how strongly (0 to 3), and which words say so. Unknown names are
    reported, never guessed."""
    L = store.ledger_for_chain(chain_id)
    m = L.moment(chain_id)
    x = RuleExtractor(store.roster(int(L.game_id)), m.conceding_team_id).extract(text)
    return native({"blame": x.blame(), "mentions": [mm.model_dump() for mm in x.mentions],
                   "unresolved": x.unresolved})


@mcp.tool()
def audit_line(chain_id: str, text: str, watch_above: float = 0.20,
               unfair_above: float = 0.40) -> dict:
    """Score a sentence for scapegoating against the evidence for a moment. Returns the
    Scapegoat Index (0 fair, 1 fully misplaced), a verdict, reasons, a contrastive explanation
    and a fair rewrite when needed."""
    L = store.ledger_for_chain(chain_id)
    m = L.moment(chain_id)
    r = L.responsibility(chain_id)
    res = _audit(text, r.shares, store.roster(int(L.game_id)), m.conceding_team_id,
                 Policy(watch_above, unfair_above), goal=m.goal)
    return native(res.to_dict())


@mcp.tool()
def fair_rewrite_constraints(chain_id: str) -> dict:
    """The facts a fair line must keep and the blame shares it must respect, for a writer."""
    L = store.ledger_for_chain(chain_id)
    s = L.moment_summary(chain_id)
    return native({
        "must_keep": {"goal": s["goal"], "shooter": L.name(s["shooter_id"]),
                      "clock_s": s["clock_s"], "period": s["period"]},
        "responsibility": s["responsibility"], "unsung": s["unsung"],
        "rules": ["Name a single culprit only if their share is 0.6 or more.",
                  "Do not invent actions or numbers that are not in the chain.",
                  "Credit the unsung contributor when their share is 0.2 or more."],
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true", help="serve over Streamable HTTP")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    if args.http:
        uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
