import { Badge } from "@fluentui/react-components";
import { Link } from "react-router-dom";
import { Term } from "../components/Info";
import { PageHeader } from "../components/Layout";
import { loadResults, useAsync } from "../state/data";

type Status = "live" | "in progress";

const PATH = [
  { t: "0:00 to 0:30", what: "On the home page, press Fix it with the agents, live.", see: "Agents on Microsoft Foundry catch a one-culprit line and rewrite it fairly, with every step timed.", to: "/" },
  { t: "0:30 to 1:15", what: "Open Check a sentence. The first example is already filled in.", see: "An Unfair score, the reasons, story versus evidence, and a fair rewrite.", to: "/check" },
  { t: "1:15 to 2:15", what: "Open the Studio. Answer the evidence check. Press Fix it with the agents. In the live feed, untick Air Fair lines automatically, kick off, and air a line yourself.", see: "The five versions the model wrote, each audited; goals arriving on Azure Event Hubs; a producer queue on the server and its hash-chained log.", to: "/studio" },
  { t: "2:15 to 3:00", what: "Open Results.", see: "Held-out detection against known causes, real public data, a red team, measured limits and the rerun commands.", to: "/results" },
];

const CRITERIA: { name: string; asks: string; evidence: { text: string; to?: string; status: Status }[] }[] = [
  { name: "Technological Implementation", asks: "Optimised synthetic data; quality engineering; hero technologies; maintainable code.",
    evidence: [
      { text: "Calibrated fictional league: most statistics within 15 percent of 906 real matches; counterfactual ground truth", to: "/results#cal", status: "live" },
      { text: "Same engine in Python and in the browser, checked case for case by 154 parity tests; 322 tests in total", status: "live" },
      { text: "Microsoft Foundry (gpt-5-mini), Agent Framework workflow, Azure Event Hubs in and out, Container Apps, managed identity, deployed with azd", to: "/studio", status: "live" },
    ] },
  { name: "Agentic Design and Innovation", asks: "Creative agent patterns; orchestration, MCP, multi-agent; novelty.",
    evidence: [
      { text: "A new metric, the Scapegoat Index, with ground truth no real data set can provide", to: "/how-it-works#score", status: "live" },
      { text: "MCP server with 8 typed tools that our own agents use", to: "/developers#mcp", status: "live" },
      { text: "Write, audit, revise loop with a fail-closed Auditor; red-team agent whose wins become regression tests", to: "/results#redteam", status: "live" },
      { text: "A goal on Event Hubs wakes the workflow; the approved line goes back out before the audience versions are written", to: "/studio", status: "live" },
    ] },
  { name: "Real-World Impact and Applicability", asks: "Significance; production readiness; impact on users.",
    evidence: [
      { text: "The problem, with sources: abuse peaks after key moments; outcome bias in ratings", to: "/#problem", status: "live" },
      { text: "Held out against known causes: 77 percent of Unfair calls right; deserved blame wrongly flagged 6.1 percent, versus 7.5 for last-touch", to: "/results#detect", status: "live" },
      { text: "Tested on real provider-labelled errors, not only our own data", to: "/results#ext", status: "live" },
      { text: "Ways in: API, MCP server, command line, Bring Your Own data, text and policy", to: "/developers", status: "live" },
    ] },
  { name: "User Experience and Presentation", asks: "Intuitive UX; clear demo; balanced front and back end.",
    evidence: [
      { text: "An i on every non-obvious term; reading-level switch; plain-language copy; glossary", to: "/learn", status: "live" },
      { text: "Light and dark, phone and desktop; keyboard paths; table views for charts; works offline", status: "live" },
      { text: "Studio with Explain this screen and Broadcast preview", to: "/studio", status: "live" },
    ] },
  { name: "Adherence to category (Best Enterprise Solution)", asks: "Reliability, transparency and controls for production in global organisations.",
    evidence: [
      { text: "A producer queue on the server: Fair airs, anything else needs a named producer and a typed reason; a stricter policy makes every line wait", to: "/studio", status: "live" },
      { text: "Hash-chained decision log on the server, verifiable at /v1/log and copied to Event Hubs; a browser log you can try to break", to: "/studio", status: "live" },
      { text: "Fails closed when the check is down; transparency note with measured limits", to: "/trust", status: "live" },
    ] },
];

export default function Judges() {
  const { data } = useAsync(loadResults, []);
  return (
    <div className="mh-page">
      <PageHeader title="Judges start here" info="judges" purpose="Everything a judge needs in about three minutes, mapped to each judging criterion. Status labels are honest: live means you can use it now." />

      {data && (
        <section className="mh-headline-card">
          <p><strong>The result in one sentence.</strong> On held-out matches where the true cause of every goal is known,{" "}
            {Math.round(data.detection.test_half.called_unfair.precision.value * 100)} percent of the check's Unfair calls were right, and it wrongly called
            deserved blame Unfair less often than the last-touch rule ({Math.round(data.detection.test_half.justified_blame_wrongly_flagged.value * 100)} versus{" "}
            {Math.round(data.detection.test_half.justified_blame_wrongly_flagged_last_touch.value * 100)} percent). It is cautious, so a person decides.
            Where it falls short, the Results page says by how much.</p>
        </section>
      )}

      <section className="mh-section" aria-labelledby="path">
        <h2 id="path">The three-minute path</h2>
        <ol className="mh-path">
          {PATH.map((p, i) => (
            <li key={p.t}>
              <span className="mh-path-time">{p.t}</span>
              <div><p><strong>{i + 1}. </strong>{p.what}</p><p className="mh-muted">You will see: {p.see}</p></div>
              <Link to={p.to} className="mh-btn">Go</Link>
            </li>
          ))}
        </ol>
      </section>

      <section className="mh-section" aria-labelledby="criteria">
        <h2 id="criteria">Each criterion, and where the evidence is</h2>
        {CRITERIA.map((c) => (
          <article key={c.name} className="mh-card mh-criterion">
            <h3>{c.name} <span className="mh-small mh-muted">20 percent</span></h3>
            <p className="mh-muted">The rules ask for: {c.asks}</p>
            <ul>
              {c.evidence.map((e) => (
                <li key={e.text}>
                  <Badge appearance="tint" color={e.status === "live" ? "success" : "warning"}>{e.status}</Badge>{" "}
                  {e.to ? <Link to={e.to}>{e.text}</Link> : e.text}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </section>

      <section className="mh-section" aria-labelledby="rules">
        <h2 id="rules">The five required stages, and where to see them</h2>
        <div className="mh-table-wrap">
          <table className="mh-table">
            <thead><tr><th>Stage the rules require</th><th>In Many Hands</th></tr></thead>
            <tbody>
              <tr><td>Ingest</td><td>Event streams from the fictional league, or your own file on <Link to="/byo">Bring your own</Link></td></tr>
              <tr><td>Interpret</td><td>Every action valued; responsibility per player in the <Link to="/studio">Studio</Link></td></tr>
              <tr><td>Explain</td><td>Reasons, contrastive comparison and fair rewrite on <Link to="/check">Check a sentence</Link></td></tr>
              <tr><td>Render</td><td>Broadcast preview, chain replay and Unsung card in the <Link to="/studio">Studio</Link></td></tr>
              <tr><td>Personalize</td><td>Five audience versions, each checked, in the <Link to="/studio">Studio</Link>; reading levels across this site</td></tr>
            </tbody>
          </table>
        </div>
        <p className="mh-note">Data: all product data is <Term id="synthetic_data">fictional</Term>. Real public data from non-Premier League competitions was used only to test the model.</p>
      </section>
    </div>
  );
}
