import { Switch } from "@fluentui/react-components";
import { useState } from "react";
import { Info, Term } from "../components/Info";
import { PageHeader } from "../components/Layout";
import { loadResults, type Metric, useAsync } from "../state/data";
import { L } from "../state/prefs";

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
// Plain names for the realism table's statistics.
const STAT_NAMES: Record<string, string> = {
  actions: "actions (everything players do)", passes: "passes", carries: "carries (running with the ball)",
  crosses: "crosses", take_ons: "dribbles past a player", shots: "shots", tackles: "tackles",
  interceptions: "interceptions", clearances: "clearances", keeper_saves: "goalkeeper saves", goals: "goals",
  pass_completion: "share of passes that reach a teammate", pass_length_m: "average pass length (metres)",
};
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
  const d = data.detection.test_half;
  const r = (x: { hits: number; n: number }) => `${x.hits} of ${x.n}`;
  const within = data.calibration.filter((c) => Math.abs(c.difference_pct) <= 15).length;
  return (
    <div className="mh-page">
      <PageHeader title="Results" purpose="What we measured, how, against what, and where Many Hands is weaker. Every number can be rerun." />

      <section className="mh-plain-summary" aria-labelledby="plain">
        <h2 id="plain">In plain words</h2>
        <ul>
          <li><strong>When it says a line is Unfair, it is usually right:</strong> {pct(d.called_unfair.precision.value)} of the time, on matches where we know the true cause.</li>
          <li><strong>It rarely accuses a fair line:</strong> only {pct(d.called_unfair.fair_lines_called_unfair.value)} of fair lines were called Unfair.</li>
          <li><strong>It is careful, not complete:</strong> it calls about a quarter of truly unfair lines Unfair by itself, and sends about six in ten to a person. That is why a person always has the last word on anything not clearly fair.</li>
          <li><strong>It does not excuse real mistakes:</strong> when one player really caused a goal, it wrongly objects less often than the simple rule of blaming whoever lost the ball last.</li>
        </ul>
      </section>

      <section className="mh-headline-card">
        <p>
          On held-out matches where the true cause of every goal is known, <strong>{pct(d.called_unfair.precision.value)}</strong> of the
          check's Unfair calls were right, and it wrongly called deserved blame Unfair less often than the last-touch rule
          (<strong>{pct(d.justified_blame_wrongly_flagged.value)}</strong> versus {pct(d.justified_blame_wrongly_flagged_last_touch.value)}).
          It is cautious: it calls only {r(d.called_unfair.recall)} truly unfair lines Unfair outright, and sends {r(d.sent_to_a_person.recall)} to a person.
          When blame is shared it is much closer to the truth (<strong>{m["tv_lam0.0"].toFixed(2)}</strong> versus <strong>{m.tv_last.toFixed(2)}</strong>).
        </p>
      </section>

      <section className="mh-section" aria-labelledby="ext">
        <h2 id="ext"><Term id="external">External benchmark: real public data</Term></h2>
        <p><L s={`StatsBomb marks an "Error" when a player's mistake leads to a shot. We checked our method on ${e.cases} of those, from ${e.matches} matches in international tournaments. Premier League data was excluded.`}
              d={`Action value model trained on 414 club matches (Serie A and Bundesliga 2015/16), tested on ${e.matches} international matches it never saw. ${e.cases} labelled errors evaluated, ${e.goals} of them goals.`}
              t={e.note} /></p>
        <Compare title="Finding the player the data company labelled" rows={[
          { label: "Labelled player has the largest share", ours: e.metrics.ours_top1.mean, base: e.metrics.last_top1.mean, fmt: pct },
          { label: "Labelled player in top three", ours: e.metrics.ours_top3.mean, base: e.metrics.last_top3.mean, fmt: pct },
        ]} />
        <ul className="mh-facts">
          <li>Consistency check: in the {e.justified_cases} cases where our ledger gives the labelled player 60 percent or more, a line blaming them
            alone is never called Unfair ({e.justified_false_unfair} flags). That follows from how the score works, so it is not evidence on its own;
            the negative control against a known truth is in the synthetic benchmark below.</li>
          <li>Labelled player's share of responsibility: {ci(e.metrics.labelled_share)}, median {pct(e.labelled_share_median)}. <Info id="ci" /></li>
          <li>A line blaming only the labelled player would be: Fair {e.verdicts_if_blamed_alone.fair}, Watch {e.verdicts_if_blamed_alone.watch}, Unfair {e.verdicts_if_blamed_alone.unfair}.</li>
          <li>Not tested: {e.excluded.no_onball_blame ?? 0} errors with no lost ball to measure, and {e.excluded.no_linked_shot ?? 0} with no shot linked to them.</li>
        </ul>
      </section>

      <section className="mh-section" aria-labelledby="syn">
        <h2 id="syn"><Term id="synthetic">Synthetic benchmark: known causes</Term></h2>
        <p><L s={`We built ${s.bench_games} fictional matches where we know the true cause of every goal, because we replay each attack 100 times with and without each mistake. We tune on half of them and report results on the other half, the held-out matches (${data.detection.split.test_matches} with a measurable cause).`}
              t={`${s.moments} decisive moments with measured causes, paired random numbers for both arms of every replay, VAEP trained on ${s.train_games} separate matches; the ledger never sees the truth.`} /> <Info id="groundTruth" /></p>
        <p className="mh-small">Over all moments the two methods tie: most goals have one clear cause, and both find it. The difference shows when the
          blame is genuinely shared, below.</p>
        <Compare title="All moments" lowerIsBetter rows={[
          { label: "Distance from the true blame", ours: s.metrics["tv_lam0.0"].mean, base: s.metrics.tv_last.mean, fmt: dist },
        ]} />
        <Compare title={`When blame is genuinely shared (${s.multi_cause.n} moments)`} lowerIsBetter rows={[
          { label: "Distance from the true blame", ours: m["tv_lam0.0"], base: m.tv_last, fmt: dist },
        ]} />
        <ul className="mh-facts">
          <li>Main culprit ranked first: Many Hands {ci(s.metrics["top1_lam0.0"])}, last-touch {ci(s.metrics.top1_last)}.</li>
          <li>On shared-blame moments, a last-touch story scores {m.last_touch_story_si.toFixed(2)} on the Scapegoat Index against the truth: Unfair.</li>
          <li>{s.justified_cases} of {s.moments} moments ({pct(s.justified_cases / s.moments)}) had one player holding 60 percent or more of the true responsibility.</li>
        </ul>
      </section>

      <section className="mh-section" aria-labelledby="detect">
        <h2 id="detect">Does the check catch truly unfair lines?</h2>
        <p className="mh-small"><strong>What this means:</strong> on {data.detection.split.test_matches} <Term id="heldOut">held-out matches</Term>, three in four of its Unfair
          calls were right and almost no fair line was accused. It lets most borderline lines through to a person rather than guessing.</p>
        <p><L s="A pundit blames the last defender to lose the ball. We know whether that was fair, because we know the true cause. Does the check agree?"
              t={`Settings chosen on ${data.detection.split.tune_matches} benchmark matches; every number here is from the other ${data.detection.split.test_matches}, held out. A line is truly unfair when its Scapegoat Index against the true causes is above 0.40. 95 percent intervals by bootstrap over matches.`} /> <Info id="ci" /></p>
        <div className="mh-table-wrap">
          <table className="mh-table">
            <thead><tr><th>On {d.pundit_lines} held-out one-culprit lines ({d.truly_unfair_lines} truly unfair)</th><th>Result</th><th>95% interval</th></tr></thead>
            <tbody>
              <tr><td>Unfair calls that were right</td><td><strong>{pct(d.called_unfair.precision.value)}</strong> ({r(d.called_unfair.precision)})</td><td>{pct(d.called_unfair.precision.ci95[0])} to {pct(d.called_unfair.precision.ci95[1])}</td></tr>
              <tr><td>Fair lines called Unfair</td><td><strong>{pct(d.called_unfair.fair_lines_called_unfair.value)}</strong> ({r(d.called_unfair.fair_lines_called_unfair)})</td><td>{pct(d.called_unfair.fair_lines_called_unfair.ci95[0])} to {pct(d.called_unfair.fair_lines_called_unfair.ci95[1])}</td></tr>
              <tr><td>Deserved blame called Unfair (last-touch rule: {pct(d.justified_blame_wrongly_flagged_last_touch.value)})</td><td><strong>{pct(d.justified_blame_wrongly_flagged.value)}</strong> ({r(d.justified_blame_wrongly_flagged)})</td><td>{pct(d.justified_blame_wrongly_flagged.ci95[0])} to {pct(d.justified_blame_wrongly_flagged.ci95[1])}</td></tr>
              <tr><td>Truly unfair lines called Unfair outright</td><td>{pct(d.called_unfair.recall.value)} ({r(d.called_unfair.recall)})</td><td>{pct(d.called_unfair.recall.ci95[0])} to {pct(d.called_unfair.recall.ci95[1])}</td></tr>
              <tr><td>Truly unfair lines sent to a person (Watch or Unfair)</td><td>{pct(d.sent_to_a_person.recall.value)} ({r(d.sent_to_a_person.recall)})</td><td>{pct(d.sent_to_a_person.recall.ci95[0])} to {pct(d.sent_to_a_person.recall.ci95[1])}</td></tr>
              <tr><td>Fair lines sent to a person</td><td>{pct(d.sent_to_a_person.fair_lines_sent.value)} ({r(d.sent_to_a_person.fair_lines_sent)})</td><td>{pct(d.sent_to_a_person.fair_lines_sent.ci95[0])} to {pct(d.sent_to_a_person.fair_lines_sent.ci95[1])}</td></tr>
            </tbody>
          </table>
        </div>
        <p className="mh-note">The last-touch rule gives the blamed player 100 percent, so it never flags a one-culprit line and catches none of them.
          The check is precise but cautious: most unfair lines it misses look fair to the evidence too. That is why it explains, routes and asks,
          and a person decides. One rule matters: where the ledger counts no lost ball at all, it now says the evidence cannot tell, instead of calling the
          line Unfair. Checked on the tuning half first, that cut wrong Unfair calls on deserved blame from 21 to 6 percent.</p>
      </section>

      {data.foundry_eval && (() => {
        const g = data.foundry_eval.groups;
        const agents = g["agents' line"], pundit = g["pundit line"];
        const code = "Scapegoat Index (code): passed", judge = "Independent fairness judge (model): passed";
        return (
          <section className="mh-section" aria-labelledby="foundry-eval">
            <h2 id="foundry-eval">Checked in Microsoft Foundry Evaluations</h2>
            <p>Every goal's lines went into one Foundry evaluation run with two graders: our Scapegoat Index as a
              code grader, and a separate model judge, with its own instructions, that sees only the line and the evidence, never our score.</p>
            <div className="mh-table-wrap">
              <table className="mh-table">
                <thead><tr><th>Lines</th><th>Fair by our score, worked out in code</th><th>Fair by a separate AI judge</th></tr></thead>
                <tbody>
                  <tr><td>The agents' lines</td><td>{agents[code]} of {agents.lines}</td><td>{agents[judge]} of {agents.lines}</td></tr>
                  <tr><td>A pundit's one-culprit line</td><td>{pundit[code]} of {pundit.lines}</td><td>{pundit[judge]} of {pundit.lines}</td></tr>
                </tbody>
              </table>
            </div>
            <p className="mh-note">The two graders agree. The pundit's line was fair whenever one player really did cause the goal,
              and unfair only where blame was shared. The judge is a separate gpt-5-mini agent with its own instructions, not a person.{" "}
              <a href={data.foundry_eval.portal_url} target="_blank" rel="noreferrer">Open the run in Microsoft Foundry</a> (needs project access).</p>
          </section>
        );
      })()}

      {data.operations && (
        <section className="mh-section" aria-labelledby="ops">
          <h2 id="ops">Time and cost on a match day</h2>
          <p>The full agent workflow ran on every one of the {data.operations.moments} goals in the demo matches, through
            Microsoft Foundry ({data.operations.model}). {data.operations.all_ready} of {data.operations.moments} produced a fair line.</p>
          <div className="mh-table-wrap">
            <table className="mh-table">
              <thead><tr><th>Measured</th><th>Typical (median)</th><th>Slowest 1 in 20</th></tr></thead>
              <tbody>
                <tr><td>Fair line ready for the lower third (agent time)</td><td>{data.operations.line_ready_s.p50.toFixed(1)} s</td><td>{data.operations.line_ready_s.p95.toFixed(1)} s</td></tr>
                <tr><td>All five audience versions ready</td><td>{data.operations.all_versions_s.p50.toFixed(1)} s</td><td>{data.operations.all_versions_s.p95.toFixed(1)} s</td></tr>
              </tbody>
            </table>
          </div>
          <ul className="mh-facts">
            <li><strong>${data.operations.cost_per_goal_usd.toFixed(4)}</strong> per goal: {data.operations.model_calls_per_goal} AI calls and about {data.operations.tokens_per_goal.toLocaleString()} <Term id="tokens">tokens</Term>.</li>
            <li><strong>${data.operations.cost_per_match_usd.toFixed(3)}</strong> per match ({data.operations.decisive_moments_per_match} decisive moments), so about <strong>${data.operations.cost_per_season_usd.toFixed(2)}</strong> for a 380-match season.</li>
            <li>Measured from this computer to the AI service in Microsoft's US data centre. The live Studio also shows the time for every goal it handles.</li>
          </ul>
        </section>
      )}

      {data.redteam && (
        <section className="mh-section" aria-labelledby="redteam">
          <h2 id="redteam"><Term id="redTeam">Red team: can an attacker sneak scapegoating past the Auditor?</Term></h2>
          <p><L s={`An attacker agent wrote ${data.redteam.attacks} lines that sound like normal punditry but quietly pin a goal on one player. A separate judge agent said which were unfair. We then checked how many our Auditor caught.`}
                t={`Hot Take and Judge are separate gpt-5-mini agents. Judge quotes are verified in code; the Scapegoat Index is computed in code. Match ${"20045"} was held out before anything was learned.`} /></p>
          <p className="mh-small mh-term">The reader is <Term id="reader">an AI that spots hinted blame</Term>; word rules alone look only for blaming words.</p>
          <Compare title="Subtle scapegoating caught, on a match held out in advance (latest run)"
            labels={["Rules plus gpt-5-mini reader", "Word rules alone"]} rows={[
            { label: "Share of the judge's unfair lines caught", ours: data.redteam.held_out.caught_with_reader / data.redteam.held_out.judge_unfair,
              base: data.redteam.held_out.caught_rules / data.redteam.held_out.judge_unfair, fmt: pct },
          ]} />
          <ul className="mh-facts">
            <li>Held-out match: <strong>{data.redteam.held_out.caught_with_reader} of {data.redteam.held_out.judge_unfair}</strong> caught with the reader, {data.redteam.held_out.caught_rules} with word rules alone.</li>
            <li>All matches: {data.redteam.all.caught_with_reader} of {data.redteam.all.judge_unfair} caught with the reader in the latest run (77 to 79 across three runs; 21 to 23 of 23 on the held-out match), {data.redteam.all.caught_rules} with rules alone.</li>
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
          <li><strong>Most truly unfair lines are not called Unfair outright</strong>: {r(d.called_unfair.recall)} on held-out matches; {r(d.sent_to_a_person.recall)} reach a person. The check informs a producer; it does not replace one.</li>
          <li><strong>Half the lines sent to a person turn out to be fair</strong> ({d.sent_to_a_person.precision.hits} of the {d.sent_to_a_person.precision.n} are truly unfair). That is the cost of caution: a few seconds of a producer's attention.</li>
          <li><strong>Off-ball blame did not help.</strong> Weighting positional blame moved results further from the truth at every weight we tried, so its weight is 0.</li>
          <li><strong>Without the AI reader, it reads lines with word rules only.</strong> Those miss sarcasm and unusual phrasing; a name it does not recognise is reported, never guessed.</li>
        </ul>
      </section>

      <section className="mh-section" aria-labelledby="cal">
        <h2 id="cal"><Term id="calibration">How realistic the fictional matches are</Term></h2>
        <p>{within} of {data.calibration.length} per-match statistics are within 15 percent of 906 real matches.</p>
        <div className="mh-table-wrap">
          <table className="mh-table">
            <thead><tr><th>Statistic per match</th><th>Real</th><th>Our league</th><th>Difference</th></tr></thead>
            <tbody>{data.calibration.map((c) => (
              <tr key={c.statistic}><td>{STAT_NAMES[c.statistic] ?? c.statistic.replaceAll("_", " ")}</td><td>{c.real}</td><td>{c.simulated}</td>
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
