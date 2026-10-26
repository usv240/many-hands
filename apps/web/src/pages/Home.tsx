import { Accordion, AccordionHeader, AccordionItem, AccordionPanel, Button, Tab, TabList } from "@fluentui/react-components";
import { ArrowRight16Regular, PersonSupport20Regular } from "@fluentui/react-icons";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AgentTrace } from "../components/AgentDesk";
import { SpeakButton } from "../components/SpeakButton";
import { Info, Term } from "../components/Info";
import { PitchReplay } from "../components/Pitch";
import { ResponsibilityBars, ScaleMeter, ScoreBadge } from "../components/viz";
import { FAQ } from "../content/learn";
import { audit } from "../engine/audit";
import { Roster } from "../engine/extraction";
import { type AgentResult, broadcast, getMetrics, liveAi, useHealth } from "../state/api";
import { loadMatch, loadResults, SHOWCASE, useAsync } from "../state/data";
import { L } from "../state/prefs";

const STEPS = [
  { n: 1, name: "Ingest",
    s: "It watches the match as a list of events: every pass, tackle and shot.",
    d: "Events arrive live from our match simulator, or from your own data files.",
    t: "Events in the open SPADL format; provider files are converted with kloppy. Azure Event Hubs carries the live stream." },
  { n: 2, name: "Interpret",
    s: "It gives every action a value: did it make a goal more or less likely?",
    d: "A model trained on thousands of matches estimates how each action changes both teams' chances of scoring.",
    t: "VAEP: gradient-boosted models of P(score) and P(concede) within 10 actions; value is the change in their difference." },
  { n: 3, name: "Explain",
    s: "For every goal or big chance, it works out who contributed, and how much.",
    d: "It answers why this player and not that one, and finds the unsung player who created the chance.",
    t: "Material losses of value by the conceding side, counting lost balls only, final turnover weighted double. Tuned on ground truth." },
  { n: 4, name: "Render",
    s: "It turns that into graphics that can sit next to the match.",
    d: "Timed graphics: the chain of actions, responsibility bars and a card for the unsung contributor.",
    t: "Overlays as timed JSON a broadcaster's graphics system can render in its own style." },
  { n: 5, name: "Personalize",
    s: "It tells the story differently for different fans, and checks every version is still fair.",
    d: "Versions for analysts and casual fans, for each club, for one featured player, and in other languages.",
    t: "Personalizer fan-out; the Auditor scores each variant; failing variants never air." },
];

export default function Home() {
  const match = useAsync(() => loadMatch(SHOWCASE.gameId), []);
  const results = useAsync(loadResults, []);
  const [story, setStory] = useState<"tv" | "evidence">("tv");
  const { health } = useHealth();
  const live = liveAi(health);
  const [agentRun, setAgentRun] = useState<{ busy: boolean; result?: AgentResult; error?: string }>({ busy: false });
  // Measured live on every goal: the fair line ready for air, and all five audience versions ready.
  const [timing, setTiming] = useState<{ line: number | null; all: number | null; n: number }>({ line: null, all: null, n: 0 });
  useEffect(() => { getMetrics().then((m) => setTiming({ line: m?.line_p50_s ?? null, all: m?.p50_s ?? null, n: m?.goals_processed ?? 0 })); }, []);

  const showcase = useMemo(() => {
    const data = match.data;
    if (!data) return null;
    const chain = data.chains.find((c) => c.chain_id === SHOWCASE.chainId)!;
    const roster = new Roster(data.roster);
    const last = data.roster.find((r) => r.player_id === chain.last_touch[0])!;
    const tvLine = `Number ${last.shirt}'s howler cost them the goal.`;
    const examples = [
      tvLine,
      `Number ${last.shirt} lost it, and the defence could not recover.`,
      `Two loose balls in a row, from ${chain.responsibility.map((c) => `number ${c.shirt}`).join(" and ")}, let them through.`,
    ].map((t) => ({ text: t, r: audit(t, chain.shares, roster, chain.conceding_team_id, undefined, chain.goal) }));
    const fairSi = audit(examples[0].r.fairRewrite ?? "", chain.shares, roster, chain.conceding_team_id, undefined, chain.goal);
    return { data, chain, last, examples, fairSi };
  }, [match.data]);

  const ext = results.data?.external;
  const syn = results.data?.synthetic;
  const det = results.data?.detection.test_half;
  const pc = (x: number) => `${Number((x * 100).toFixed(1))}%`; // one decimal, so 7.5 percent does not read as 8

  return (
    <div className="mh-home">
      {/* 1. Hero */}
      <section className="mh-hero">
        <div className="mh-hero-text">
          <h1>Nobody concedes alone.</h1>
          <p className="mh-lead mh-lead-strong">
            <Term id="foundry">Microsoft Foundry</Term> agents trace every goal back through every player who contributed to it, catch scapegoating
            lines before they air, and rewrite them fairly, seconds after the goal.
          </p>
          <p className="mh-lead">
            <L s="When a goal goes in, TV and AI recaps often blame one player. A line can get every fact right and still make one player the scapegoat. Many Hands shows who really contributed, tells the story for every kind of fan, and stops unfair blame before it reaches the screen."
               d="Many Hands is an AI match insights engine. It measures each player's real share of every key moment, explains it on screen, personalises it for every fan, and checks every sentence for scapegoating before it airs."
               t="An event-driven engine that values every action with a published model (VAEP), attributes responsibility for each decisive moment, and runs a write, audit and revise loop that blocks scapegoating lines, measured by our Scapegoat Index." />
          </p>
          <div className="mh-cta-row">
            <Link to="/check" className="mh-btn mh-btn-primary">Check a sentence <ArrowRight16Regular aria-hidden /></Link>
            <Link to="/studio" className="mh-btn">See the live Studio</Link>
          </div>
          <p className="mh-hint"><Info id="judges" /> Look for the <strong>i</strong> next to any term: hover to preview, click to keep it open. Judging? <Link to="/judges">Start here</Link>.</p>
        </div>
        <div className="mh-hero-card" data-ui aria-label="Example: the same goal, two lines">
          {showcase ? (
            <>
              <p className="mh-card-title">A pundit is about to say this about a goal:</p>
              <div className="mh-hero-line">
                <p>"{showcase.examples[0].text}"</p>
                <ScoreBadge si={showcase.examples[0].r.si} verdict={showcase.examples[0].r.verdict} />
              </div>
              {agentRun.result?.line ? (
                <div className="mh-hero-line is-fixed">
                  <p>"{agentRun.result.line}"</p>
                  {agentRun.result.audit && <ScoreBadge si={agentRun.result.audit.si} verdict={agentRun.result.audit.verdict} />}
                </div>
              ) : !live ? (
                <div className="mh-hero-line is-fixed">
                  <p>"{showcase.examples[0].r.fairRewrite}"</p>
                  <ScoreBadge si={showcase.fairSi.si} verdict={showcase.fairSi.verdict} />
                </div>
              ) : null}
              {live && !agentRun.result && (
                <Button appearance="primary" disabled={agentRun.busy}
                  onClick={async () => {
                    setAgentRun({ busy: true });
                    try { setAgentRun({ busy: false, result: await broadcast({ chain_id: SHOWCASE.chainId, text: showcase.examples[0].text }) }); }
                    catch (e) { setAgentRun({ busy: false, error: (e as Error).message }); }
                  }}>
                  {agentRun.busy ? "The agents are rewriting it" : "Fix it with the agents, live"}
                </Button>
              )}
              {agentRun.error && <p className="mh-small mh-bad">{agentRun.error}</p>}
              {agentRun.result?.line && agentRun.result.audit?.verdict !== "unfair" && (
                <SpeakButton text={agentRun.result.line} withInfo />
              )}
              {agentRun.result && <AgentTrace result={agentRun.result} />}
              <p className="mh-small mh-muted">
                <Term id="si">Scored with the Scapegoat Index</Term>
                {live ? " Rewritten by gpt-5-mini on Microsoft Foundry; the score is computed in code." : " Fictional match."}
              </p>
            </>
          ) : <div className="mh-skeleton" style={{ height: 180 }} />}
        </div>
      </section>

      {/* 2. Problem */}
      <section className="mh-section" aria-labelledby="problem">
        <h2 id="problem">Football is a team game. The blame usually is not.</h2>
        <p className="mh-statement">
          July 2021, the Euro 2020 final. England lose on penalties, and within hours the three young players who
          missed are racially abused online. The FA condemns it before dawn.{" "}
          <a href="https://www.aljazeera.com/sports/2021/7/12/fa-condemns-racist-abuse-of-england-players-after-euro-2020-final" target="_blank" rel="noreferrer">Al Jazeera, 2021</a>
        </p>
        <div className="mh-facts-row">
          <article className="mh-fact">
            <p className="mh-fact-num">68%</p>
            <p>of Premier League players received abusive posts on Twitter in the first half of the 2021 to 2022 season.</p>
            <a className="mh-source" href="https://www.turing.ac.uk/news/publications/tracking-abuse-twitter-against-football-players-2021-22-premier-league-season" target="_blank" rel="noreferrer">Alan Turing Institute for Ofcom, 2022</a>
          </article>
          <article className="mh-fact">
            <p className="mh-fact-num">Peaks</p>
            <p>Abuse peaks right after key moments in a match, and half of it was aimed at just 12 players.</p>
            <a className="mh-source" href="https://www.ofcom.org.uk/online-safety/online-abuse/seven-in-ten-premier-league-footballers-face-twitter-abuse" target="_blank" rel="noreferrer">Ofcom, 2022</a>
          </article>
          <article className="mh-fact">
            <p className="mh-fact-num">Biased</p>
            <p>Reporters rate players higher when their team wins a penalty shoot-out, even players who never took a penalty. The result changes the story.</p>
            <a className="mh-source" href="https://doi.org/10.1016/j.joep.2018.12.006" target="_blank" rel="noreferrer">Kausel, Ventura and Rodriguez, 2019</a>
          </article>
        </div>
        <p className="mh-callout">
          <L s="Platforms remove abuse after it is posted. Nobody fixes the story that starts it. That is what Many Hands does."
             d="Leagues, unions and FIFA run moderation that works after abuse is posted; FIFA verified 240,000 abusive posts during the 2026 World Cup. Many Hands works earlier, on the story itself." />
        </p>
      </section>

      {/* 3. One goal, two stories */}
      <section className="mh-section mh-band" aria-labelledby="two-stories">
        <h2 id="two-stories">One goal. Two ways to tell it.</h2>
        <p className="mh-section-lead">Press the switch. Same goal, same data: only the story changes.</p>
        {showcase ? (
          <div className="mh-two-stories">
            <div>
              <TabList selectedValue={story} onTabSelect={(_, d) => setStory(d.value as "tv" | "evidence")} aria-label="Choose a story">
                <Tab value="tv">How TV usually tells it</Tab>
                <Tab value="evidence">What actually happened</Tab>
              </TabList>
              <div className="mh-story-panel" aria-live="polite">
                {story === "tv" ? (
                  <>
                    <p className="mh-quote">"{showcase.examples[0].text}"</p>
                    <ResponsibilityBars team="a" caption="Blame in the TV line"
                      rows={[{ id: showcase.last.player_id, label: `#${showcase.last.shirt} ${showcase.last.name}`, share: 1, note: "The last player to lose the ball gets all of it." }]} />
                    <ScoreBadge si={showcase.examples[0].r.si} verdict={showcase.examples[0].r.verdict} size="large" />
                  </>
                ) : (
                  <>
                    <p className="mh-quote">"{showcase.examples[0].r.fairRewrite}"</p>
                    <ResponsibilityBars team="a" caption="Responsibility in the evidence"
                      rows={showcase.chain.responsibility.map((c) => ({ id: c.player_id, label: `#${c.shirt} ${c.name}`, share: c.share, note: c.reason }))} />
                    <p className="mh-small"><Term id="responsibility">Shares from the Responsibility Ledger</Term></p>
                  </>
                )}
              </div>
              <p className="mh-note">
                Honest context: most goals have one clear cause, and then Many Hands says so. About 1 in 4 real
                cases look like this one. <Link to="/results">See the numbers</Link>.
              </p>
            </div>
            <div>
              <p className="mh-small mh-muted"><Term id="chain">The {showcase.chain.n_actions} actions behind this goal</Term>. Press Play to
                watch them in order; rings mark the lost balls that count as blame.</p>
              <PitchReplay actions={showcase.chain.actions} data={showcase.data}
                           highlight={showcase.chain.responsibility.map((c) => c.player_id)} compact />
            </div>
          </div>
        ) : <div className="mh-skeleton" style={{ height: 320 }} />}
      </section>

      {/* 4. How it works */}
      <section className="mh-section" aria-labelledby="how">
        <h2 id="how"><Term id="pipeline">How it works, in five steps</Term></h2>
        <ol className="mh-steps">
          {STEPS.map((s) => (
            <li key={s.n} className="mh-step">
              <div>
                <h3><span className="mh-step-n">{s.n}</span> {s.name}</h3>
                <p><L s={s.s} d={s.d} t={s.t} /></p>
              </div>
            </li>
          ))}
        </ol>
        <Link to="/how-it-works" className="mh-link-arrow">The full explanation <ArrowRight16Regular aria-hidden /></Link>
      </section>

      {/* 5. The score */}
      <section className="mh-section mh-band" aria-labelledby="score">
        <h2 id="score"><Term id="si">A fairness score for every sentence</Term></h2>
        <p className="mh-section-lead">
          <L s="We compare who a sentence blames with who the evidence says contributed. Close to 0 means fair. Close to 1 means one player is being blamed for something the evidence spreads across others."
             d="The Scapegoat Index measures the gap between the blame in a sentence and the responsibility in the evidence. 0.20 or below is Fair, up to 0.40 is Watch, above 0.40 is Unfair. Broadcasters can set their own limits."
             t="SI is the total variation distance between the sentence's blame distribution (extracted with verified spans) and the ledger's responsibility distribution. A sentence with no blame scores 0." />
        </p>
        <ScaleMeter />
        {showcase && (
          <ul className="mh-examples">
            {showcase.examples.map((e) => (
              <li key={e.text}><ScoreBadge si={e.r.si} verdict={e.r.verdict} /> <span>"{e.text}"</span></li>
            ))}
          </ul>
        )}
        <Link to="/check" className="mh-btn mh-btn-primary">Try your own sentence <ArrowRight16Regular aria-hidden /></Link>
      </section>

      {/* 6. Proof */}
      <section className="mh-section" aria-labelledby="proof">
        <h2 id="proof">What it means on a match day</h2>
        <dl className="mh-outcomes">
          <div>
            {timing.line ? (<>
              <dt>{timing.line.toFixed(1)} s</dt>
              <dd>from a goal reaching Azure Event Hubs to a fair, checked line ready for the <Term id="lowerThird">lower third</Term>
                {timing.all ? `; all five audience versions follow by ${timing.all.toFixed(1)} s` : ""}. Median of the {timing.n} live goals since the server last started.</dd>
            </>) : (<>
              <dt>{results.data ? `${results.data.operations.line_ready_s.p50.toFixed(1)} s` : "Seconds"}</dt>
              <dd>from a goal to a fair, checked line ready for the <Term id="lowerThird">lower third</Term>; all five audience versions
                follow by {results.data ? `${results.data.operations.all_versions_s.p50.toFixed(1)} s` : "a few seconds more"}. Median
                of {results.data?.operations.moments ?? 22} goals in our benchmark. Kick off the live feed in the Studio to measure it yourself.</dd>
            </>)}
          </div>
          <div>
            <dt>{results.data ? `$${results.data.operations.cost_per_season_usd.toFixed(0)}` : "About $5"}</dt>
            <dd>to check every goal of a 380-match season with the agents on Microsoft Foundry: about {results.data ? `${(results.data.operations.cost_per_match_usd * 100).toFixed(1)} cents` : "1 cent"} a match. Measured from real <Term id="tokens">token</Term> use on {results.data?.operations.moments ?? 22} goals.</dd>
          </div>
          <div>
            <dt>{det ? pc(det.called_unfair.precision.value) : "3 in 4"}</dt>
            <dd>of its Unfair calls were right{det ? ` (${det.called_unfair.precision.hits} of ${det.called_unfair.precision.n})` : ""}, on{" "}
              <Term id="heldOut">held-out matches</Term> where the true cause of every goal is known.
              Fair lines were called Unfair {det ? pc(det.called_unfair.fair_lines_called_unfair.value) : "2%"} of the time.</dd>
          </div>
          <div>
            <dt>51</dt>
            <dd>one-culprit stories in a 380-match season that the check would call Unfair. Our estimate from real tournament data:
              about one error a data company marks in every two matches, and 27 percent of the stories blaming one player for it are Unfair.</dd>
          </div>
        </dl>
        <h3 className="mh-subhead">The evidence behind those numbers</h3>
        <div className="mh-facts-row">
          <article className="mh-stat">
            <p className="mh-stat-num">{det ? `${pc(det.justified_blame_wrongly_flagged.value)} vs ${pc(det.justified_blame_wrongly_flagged_last_touch.value)}` : "..."}</p>
            <p><Term id="negativeControl">Deserved blame wrongly called Unfair</Term>: Many Hands versus blaming whoever lost the ball last, scored against the known true cause. Fair both ways.</p>
            <p className="mh-small mh-muted"><Term id="synthetic">Synthetic league</Term>, matches held out from tuning.</p>
          </article>
          <article className="mh-stat">
            <p className="mh-stat-num">{ext ? `${ext.verdicts_if_blamed_alone.unfair} of ${ext.cases}` : "..."}</p>
            <p>real errors where the check calls a single-culprit story Unfair, because a teammate's lost ball mattered as much or more.</p>
            <p className="mh-small mh-muted"><Term id="external">Real public data</Term>, provider-labelled errors, Premier League excluded.</p>
          </article>
          <article className="mh-stat">
            <p className="mh-stat-num">{syn ? `${syn.multi_cause.metrics["tv_lam0.0"].toFixed(2)} vs ${syn.multi_cause.metrics.tv_last.toFixed(2)}` : "..."}</p>
            <p><Term id="distance">distance from the true blame</Term> when blame is shared: Many Hands versus blaming whoever lost the ball last. Lower is better.</p>
            <p className="mh-small mh-muted"><Term id="synthetic">Synthetic league</Term> with known causes.</p>
          </article>
        </div>
        <p className="mh-note">
          The limits, measured: last-touch blame names the main culprit more often than we do (90 versus 76 percent on real data), and the
          check calls only {det ? `${det.called_unfair.recall.hits} of ${det.truly_unfair_lines}` : "1 in 4"} truly unfair lines Unfair outright;
          {det ? ` ${det.sent_to_a_person.recall.hits} of ${det.truly_unfair_lines}` : " 6 in 10"} at least go to a person. That is why a person
          decides. <Link to="/results">Full results and method</Link>.
        </p>
      </section>

      {/* 7. Who it is for, and how they use it */}
      <section className="mh-section mh-band" aria-labelledby="who">
        <h2 id="who">Who uses it, and how</h2>
        <ul className="mh-uses">
          {[
            { t: "Broadcasters and streamers", d: "Every line is checked before it airs. Clearly fair lines go out at once; anything else waits for a person.", to: "/studio", cta: "Open the Studio" },
            { t: "Editors and pundits", d: "Paste any line about a goal and see how fair it is, and why.", to: "/check", cta: "Check a line" },
            { t: "AI developers", d: "Add the check to any recap engine through the REST API or the command line.", to: "/developers", cta: "Read the API" },
            { t: "AI assistants", d: "GitHub Copilot or any MCP client can use the 8 tools that read our Responsibility Ledger.", to: "/developers#mcp", cta: "Connect over MCP" },
            { t: "Clubs and leagues", d: "See which players are being over-blamed, with a tamper-evident record.", to: "/trust", cta: "How it stays honest" },
            { t: "Anyone with match files", d: "Bring your own data, sentences and fairness limits. Files never leave your browser.", to: "/byo", cta: "Bring your own" },
          ].map((c) => (
            <li key={c.t}>
              <div><h3>{c.t}</h3><p>{c.d}</p></div>
              <Link to={c.to} className="mh-link-arrow">{c.cta} <ArrowRight16Regular aria-hidden /></Link>
            </li>
          ))}
        </ul>
        <div className="mh-fairboth">
          <h3><Term id="justified">Fair both ways</Term></h3>
          <p>Many Hands is not here to excuse mistakes. When the evidence shows one player was mostly responsible, it says so plainly. It also finds the players who did the most to create a goal but never make the headline, and gives them credit.</p>
        </div>
      </section>

      {/* 9. Trust */}
      <section className="mh-section mh-band" aria-labelledby="trust">
        <h2 id="trust">Built to be trusted</h2>
        <ul className="mh-trust-list">
          <li><strong><Term id="failClosed">Fails closed.</Term></strong> If the fairness check is down, nothing airs.</li>
          <li><strong><Term id="approve">Human in control.</Term></strong> A producer can always approve, edit or reject.</li>
          <li><strong><Term id="auditLog">Tamper-evident log.</Term></strong> Every decision is fingerprinted and chained.</li>
          <li><strong><Term id="synthetic_data">Synthetic data.</Term></strong> The product runs on fictional matches only.</li>
          <li><strong>Measured limits.</strong> We publish where it is weaker, with numbers. <Link to="/trust">Transparency note</Link></li>
        </ul>
      </section>

      {/* 10. FAQ */}
      <section className="mh-section" aria-labelledby="faq">
        <h2 id="faq">Questions people ask</h2>
        <Accordion collapsible multiple>
          {FAQ.map((f) => (
            <AccordionItem key={f.q} value={f.q}>
              <AccordionHeader>{f.q}</AccordionHeader>
              <AccordionPanel><p>{f.a}</p></AccordionPanel>
            </AccordionItem>
          ))}
        </Accordion>
        <p className="mh-note"><PersonSupport20Regular aria-hidden /> New to football data? Read <Link to="/learn">the basics and the glossary</Link>. Every claim on this site has a source in <Link to="/learn#references">Research and references</Link>.</p>
      </section>
    </div>
  );
}
