import { Switch } from "@fluentui/react-components";
import { useState } from "react";
import { Info, Term } from "../components/Info";
import { PageHeader } from "../components/Layout";
import { loadResults, type Metric, useAsync } from "../state/data";
import { L } from "../state/prefs";

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
const ci = (m: Metric, f = pct) => `${f(m.mean)} (${f(m.ci95_low)} to ${f(m.ci95_high)})`;
const dist = (x: number) => x.toFixed(3);

/** Paired horizontal bars, ours versus baseline, with a table toggle. */
function Compare({ title, rows, lowerIsBetter, labels = ["Many Hands", "Last-touch blame"] }:
  { title: string; lowerIsBetter?: boolean; labels?: [string, string];
  rows: { label: string; ours: number; base: number; fmt: (x: number) => string }[] }) {
  const [table, setTable] = useState(false);
  return (
    <figure className="mh-compare">
      <figcaption className="mh-row mh-between">
        <strong>{title}</strong>
        <Switch label="Show as table" checked={table} onChange={(_, d) => setTable(d.checked)} />
      </figcaption>
      <div className="mh-legend">
        <span className="mh-legend-item"><span className="mh-swatch mh-series-ours" aria-hidden />{labels[0]}</span>
        <span className="mh-legend-item"><span className="mh-swatch mh-series-base" aria-hidden />{labels[1]}</span>
        {lowerIsBetter && <span className="mh-legend-item">Lower is better</span>}
      </div>
      {table ? (
        <table className="mh-table">
          <thead><tr><th>Metric</th><th>{labels[0]}</th><th>{labels[1]}</th></tr></thead>
          <tbody>{rows.map((r) => <tr key={r.label}><td>{r.label}</td><td>{r.fmt(r.ours)}</td><td>{r.fmt(r.base)}</td></tr>)}</tbody>
        </table>
      ) : rows.map((r) => (
        <div key={r.label} className="mh-cmp-row">
          <div className="mh-cmp-label">{r.label}</div>
          <div className="mh-cmp-bars">
            <div className="mh-bar-track"><div className="mh-bar-fill mh-series-ours" style={{ width: `${Math.min(100, r.ours * 100)}%` }} /><span className="mh-bar-value">{r.fmt(r.ours)}</span></div>
            <div className="mh-bar-track"><div className="mh-bar-fill mh-series-base" style={{ width: `${Math.min(100, r.base * 100)}%` }} /><span className="mh-bar-value">{r.fmt(r.base)}</span></div>
          </div>
        </div>
      ))}
    </figure>
  );
}

export default function Results() {
  const { data } = useAsync(loadResults, []);
  if (!data) return <div className="mh-page"><div className="mh-skeleton" style={{ height: 400 }} /></div>;
  const e = data.external;
  const s = data.synthetic;
  const m = s.multi_cause.metrics;
  const within = data.calibration.filter((c) => Math.abs(c.difference_pct) <= 15).length;
  return (
    <div className="mh-page">
      <PageHeader title="Results" purpose="What we measured, how, against what, and where Many Hands is weaker. Every number can be rerun." />

      <section className="mh-headline-card">
        <p>
          On <strong>{e.cases}</strong> real, provider-labelled errors, Many Hands never flagged deserved blame as unfair
          (<strong>{e.justified_false_unfair} of {e.justified_cases}</strong>), and caught the <strong>{e.verdicts_if_blamed_alone.unfair}</strong> cases
          (about 1 in 4) where a single-culprit story would have been unfair. On a synthetic league where the true cause of every goal is known,
          it is much closer to the truth when blame is shared (<strong>{m["tv_lam0.0"].toFixed(2)}</strong> versus <strong>{m.tv_last.toFixed(2)}</strong>).
        </p>
      </section>

      <section className="mh-section" aria-labelledby="ext">
        <h2 id="ext"><Term id="external">External benchmark: real public data</Term></h2>
        <p><L s={`StatsBomb marks an "Error" when a player's mistake leads to a shot. We checked our method on ${e.cases} of those, from ${e.matches} matches in international tournaments. Premier League data was excluded.`}
              d={`Action value model trained on 414 club matches (Serie A and Bundesliga 2015/16), tested on ${e.matches} international matches it never saw. ${e.cases} labelled errors evaluated, ${e.goals} of them goals.`}
              t={e.note} /></p>
        <Compare title="Finding the player the data company labelled" rows={[
          { label: "Labelled player ranked first", ours: e.metrics.ours_top1.mean, base: e.metrics.last_top1.mean, fmt: pct },
          { label: "Labelled player in top three", ours: e.metrics.ours_top3.mean, base: e.metrics.last_top3.mean, fmt: pct },
        ]} />
        <ul className="mh-facts">
          <li><Term id="negativeControl">Negative control</Term>: <strong>{e.justified_false_unfair} false Unfair flags in {e.justified_cases}</strong> cases where the labelled player really carried 60 percent or more.</li>
          <li>Labelled player's share of responsibility: {ci(e.metrics.labelled_share)}, median {pct(e.labelled_share_median)}. <Info id="ci" /></li>
          <li>A line blaming only the labelled player would be: Fair {e.verdicts_if_blamed_alone.fair}, Watch {e.verdicts_if_blamed_alone.watch}, Unfair {e.verdicts_if_blamed_alone.unfair}.</li>
          <li>Not evaluated: {Object.entries(e.excluded).map(([k, v]) => `${v} ${k.replaceAll("_", " ")}`).join("; ")}.</li>
        </ul>
      </section>

      <section className="mh-section" aria-labelledby="syn">
        <h2 id="syn"><Term id="synthetic">Synthetic benchmark: known causes</Term></h2>
        <p><L s={`We built ${s.bench_games} fictional matches where we know the true cause of every goal, because we replay each attack 100 times with and without each mistake.`}
              t={`${s.moments} decisive moments with measured causes, paired random numbers for both arms of every replay, VAEP trained on ${s.train_games} separate matches; the ledger never sees the truth.`} /> <Info id="groundTruth" /></p>
        <Compare title="All moments" lowerIsBetter rows={[
          { label: "Distance from the true blame", ours: s.metrics["tv_lam0.0"].mean, base: s.metrics.tv_last.mean, fmt: dist },
        ]} />
        <Compare title={`When blame is genuinely shared (${s.multi_cause.n} moments)`} lowerIsBetter rows={[
          { label: "Distance from the true blame", ours: m["tv_lam0.0"], base: m.tv_last, fmt: dist },
        ]} />
        <ul className="mh-facts">
          <li>Main culprit ranked first: Many Hands {ci(s.metrics["top1_lam0.0"])}, last-touch {ci(s.metrics.top1_last)}.</li>
          <li>On shared-blame moments, a last-touch story scores {m.last_touch_story_si.toFixed(2)} on the Scapegoat Index: Unfair. Many Hands raised 0 false flags there.</li>
          <li>{s.justified_cases} of {s.moments} moments ({pct(s.justified_cases / s.moments)}) had one player holding 60 percent or more of the true responsibility.</li>
        </ul>
      </section>

      {data.redteam && (
        <section className="mh-section" aria-labelledby="redteam">
          <h2 id="redteam"><Term id="redTeam">Red team: can an attacker sneak scapegoating past the Auditor?</Term></h2>
          <p><L s={`An attacker agent wrote ${data.redteam.attacks} lines that sound like normal punditry but quietly pin a goal on one player. A separate judge agent said which were unfair. We then checked how many our Auditor caught.`}
                t={`Hot Take and Judge are separate gpt-5-mini agents. Judge quotes are verified in code; the Scapegoat Index is computed in code. Match ${"20045"} was held out before anything was learned.`} /></p>
          <Compare title="Subtle scapegoating caught, on a match held out in advance"
            labels={["Rules plus gpt-5-mini reader", "Word rules alone"]} rows={[
            { label: "Share of the judge's unfair lines caught", ours: data.redteam.held_out.caught_with_reader / data.redteam.held_out.judge_unfair,
              base: data.redteam.held_out.caught_rules / data.redteam.held_out.judge_unfair, fmt: pct },
          ]} />
          <ul className="mh-facts">
            <li>Held-out match: <strong>{data.redteam.held_out.caught_with_reader} of {data.redteam.held_out.judge_unfair}</strong> caught with the reader, {data.redteam.held_out.caught_rules} with word rules alone.</li>
            <li>All matches: {data.redteam.all.caught_with_reader} of {data.redteam.all.judge_unfair} caught with the reader (77 on a rerun), {data.redteam.all.caught_rules} with rules alone.</li>
            <li>Fair control lines flagged Unfair: <strong>{data.redteam.controls.unfair_with_reader} of {data.redteam.controls.lines}</strong>.</li>
            <li>The cost: borderline attacker lines the judge rated fair were flagged Unfair {data.redteam.all.hard_negatives_unfair_with_reader} of {data.redteam.all.hard_negatives} times with the reader, {data.redteam.all.hard_negatives_unfair_rules} with rules alone. A producer still decides.</li>
            <li>Learning the attackers' phrasing into the word list did not generalise (5 of 23 on the held-out match), so we did not use it.</li>
            <li>Every attack is now a permanent test that runs on every commit. {data.redteam.caveat}</li>
          </ul>
        </section>
      )}

      <section className="mh-section" aria-labelledby="limits">
        <h2 id="limits">Measured limits</h2>
        <ul className="mh-facts">
          <li><strong>Last-touch names the main culprit more often</strong>: {pct(e.metrics.last_top1.mean)} versus {pct(e.metrics.ours_top1.mean)} on real data. Our edge is how much, not who.</li>
          <li><strong>On synthetic moments with one dominant cause, we raise more false Watch or Unfair flags</strong> than last-touch: {pct(s.metrics["justified_unfair_lam0.0"].mean)} versus {pct(s.metrics.justified_unfair_last.mean)}.</li>
          <li><strong>Off-ball blame did not help.</strong> Weighting positional blame moved results further from the truth at every weight we tried, so its weight is 0.</li>
          <li><strong>Blame extraction is rule-based offline.</strong> It misses sarcasm and unusual phrasing; unknown names are reported, never guessed.</li>
        </ul>
      </section>

      <section className="mh-section" aria-labelledby="cal">
        <h2 id="cal"><Term id="calibration">How realistic the fictional matches are</Term></h2>
        <p>{within} of {data.calibration.length} per-match statistics are within 15 percent of 906 real matches.</p>
        <div className="mh-table-wrap">
          <table className="mh-table">
            <thead><tr><th>Statistic per match</th><th>Real</th><th>Our league</th><th>Difference</th></tr></thead>
            <tbody>{data.calibration.map((c) => (
              <tr key={c.statistic}><td>{c.statistic.replaceAll("_", " ")}</td><td>{c.real}</td><td>{c.simulated}</td>
                <td className={Math.abs(c.difference_pct) <= 15 ? "mh-ok" : "mh-bad"}>{c.difference_pct > 0 ? "+" : ""}{c.difference_pct}%</td></tr>
            ))}</tbody>
          </table>
        </div>
      </section>

      <section className="mh-section" aria-labelledby="rerun">
        <h2 id="rerun"><Term id="cli">Rerun every number</Term></h2>
        <pre className="mh-code">{`uv sync
uv run python benchmarks/external_statsbomb/prepare.py
uv run python benchmarks/external_statsbomb/train_vaep.py
uv run python packages/sdk/manyhands/cli.py verify --suite external
uv run python benchmarks/synthetic/generate.py --train 80 --bench 60
uv run python packages/sdk/manyhands/cli.py verify --suite synthetic`}</pre>
      </section>
    </div>
  );
}
