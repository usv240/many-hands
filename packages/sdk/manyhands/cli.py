"""The `manyhands` command line.

    manyhands matches                       list demo matches
    manyhands chains 20003                  decisive moments in a match
    manyhands audit 20003-150 "Number 5's howler cost them the game."
    manyhands verify --suite synthetic      rerun a benchmark and check it against the published numbers
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import typer

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages"))

app = typer.Typer(help="Fair match intelligence from the command line.", no_args_is_help=True)

TOLERANCE = 0.02  # absolute tolerance on each published mean


def _store():
    from services.api.app import native, store
    return store, native


@app.command()
def matches() -> None:
    """List the fictional matches in the demo pack."""
    from services.api.app import matches as m
    for g in m():
        typer.echo(f"{g['game_id']}  {g['home']['name']} {g['score'][0]} - {g['score'][1]} "
                   f"{g['away']['name']}  ({g['goals']} goals, {g['decisive_moments']} moments)")


@app.command()
def chains(game_id: int) -> None:
    """Decisive moments in a match, with who was responsible for how much."""
    from services.api.app import chains as c
    for s in c(game_id):
        who = ", ".join(f"#{r['shirt']} {r['share']:.0%}" for r in s["responsibility"]) or "no defending loss"
        typer.echo(f"{s['chain_id']:12} {'GOAL ' if s['goal'] else 'chance'} {s['minute']:3d}'  {who}")


@app.command()
def audit(chain_id: str, text: str, watch_above: float = 0.20, unfair_above: float = 0.40) -> None:
    """Score a line for scapegoating and print a fair rewrite if needed."""
    from narrative_core.audit import audit as a
    from narrative_core.scapegoat import Policy
    store, native = _store()
    L = store.ledger_for_chain(chain_id)
    m = L.moment(chain_id)
    r = L.responsibility(chain_id)
    res = a(text, r.shares, store.roster(int(L.game_id)), m.conceding_team_id,
            Policy(watch_above, unfair_above), goal=m.goal)
    typer.echo(f"Scapegoat Index {res.si:.2f}  verdict: {res.verdict.upper()}")
    for reason in res.reasons:
        typer.echo(f"  {reason}")
    typer.echo(f"  {res.contrastive}")
    if res.fair_rewrite:
        typer.echo(f"  Fair version: {res.fair_rewrite}")


@app.command()
def verify(suite: str = typer.Option("synthetic", help="synthetic or external"),
           rerun: bool = typer.Option(True, help="rerun the evaluator before comparing")) -> None:
    """Rerun a benchmark and compare every published mean with the fresh result."""
    folder = ROOT / "benchmarks" / ("synthetic" if suite == "synthetic" else "external_statsbomb")
    published = json.loads((folder / "results" / "summary.json").read_text())
    if rerun:
        typer.echo(f"Rerunning {folder.name}/evaluate.py (needs the data prepared, see its README)")
        code = subprocess.call([sys.executable, "-W", "ignore", str(folder / "evaluate.py")],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if code != 0:
            typer.echo("evaluate.py failed; prepare the data first", err=True)
            raise typer.Exit(2)
    fresh = json.loads((folder / "results" / "summary.json").read_text())
    failures = 0
    for name, pub in published["metrics"].items():
        new = fresh["metrics"][name]["mean"]
        ok = abs(new - pub["mean"]) <= TOLERANCE
        failures += not ok
        typer.echo(f"{'PASS' if ok else 'FAIL'}  {name:28} published {pub['mean']:.3f}  fresh {new:.3f}")
    typer.echo("All published numbers reproduced." if not failures else f"{failures} metrics differ.")
    raise typer.Exit(1 if failures else 0)


if __name__ == "__main__":
    app()
