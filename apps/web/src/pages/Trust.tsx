import { Link } from "react-router-dom";
import { Term } from "../components/Info";
import { PageHeader } from "../components/Layout";

export default function Trust() {
  return (
    <div className="mh-page mh-prose">
      <PageHeader title="Trust and safety" purpose="How Many Hands is meant to be used, what it cannot do, how it was tested, and how people stay in control. Written in the style of a Microsoft Responsible AI transparency note." />
      <section className="mh-section"><h2>Intended uses</h2>
        <ul>
          <li>Checking graphics, scripts and AI-written recaps for scapegoating before they air.</li>
          <li>Showing fans and analysts who contributed to a goal, and how much.</li>
          <li>Helping clubs and leagues see which players are being over-blamed over time.</li>
        </ul>
      </section>
      <section className="mh-section"><h2>Not intended for</h2>
        <ul>
          <li>Judging a player's ability, value or contract. Responsibility for one moment is not a rating.</li>
          <li>Moderating or blocking what fans say. It suggests and explains; people decide.</li>
          <li>Proving that a story will or will not cause abuse. It measures fairness of the story, nothing more.</li>
        </ul>
      </section>
      <section className="mh-section"><h2>Known limits, measured</h2>
        <p>The full list with numbers is on <Link to="/results#limits">Results</Link>. In short: the simple last-touch rule names the main culprit more often than we do; our positional blame did not help and is switched off; offline blame extraction uses rules and misses sarcasm.</p>
      </section>
      <section className="mh-section"><h2>How it was tested</h2>
        <p>On real, provider-labelled errors we did not create, and on a fictional league with known causes, both against a named baseline and with a <Term id="negativeControl">negative control</Term>. The browser engine matches the server engine case for case.</p>
      </section>
      <section className="mh-section"><h2>People stay in control</h2>
        <ul>
          <li><Term id="approve">A producer approves every line.</Term> An Unfair line can only air with a typed reason.</li>
          <li><Term id="failClosed">Fails closed.</Term> If the check is unavailable, nothing airs.</li>
          <li><Term id="auditLog">Tamper-evident log.</Term> Every decision is fingerprinted and chained; anyone can verify it.</li>
          <li><Term id="policy">Configurable limits.</Term> Each organisation sets where Watch and Unfair begin.</li>
        </ul>
      </section>
      <section className="mh-section"><h2>Data and privacy</h2>
        <ul>
          <li>The product uses only fictional matches, clubs and players from our simulator.</li>
          <li>Real public data (StatsBomb Open Data, data provided by StatsBomb), excluding the Premier League, was used only to test the model. It is not stored in the product or the code repository.</li>
          <li>Files you load on Bring your own stay in your browser tab and are deleted when you close it.</li>
          <li>The score is computed in code, not by an AI model, so text that tries to instruct the AI cannot change it.</li>
        </ul>
      </section>
    </div>
  );
}
