import { Accordion, AccordionHeader, AccordionItem, AccordionPanel, SearchBox } from "@fluentui/react-components";
import { useState } from "react";
import { PageHeader } from "../components/Layout";
import { BASICS, FAQ, GLOSSARY, REFERENCES } from "../content/learn";

export default function Learn() {
  const [q, setQ] = useState("");
  const terms = GLOSSARY.filter((g) => (g.term + g.simply).toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="mh-page">
      <PageHeader title="Learn" purpose="Football data basics, every term on this site in plain words, the research behind the product, and common questions." />
      <section className="mh-section" aria-labelledby="basics">
        <h2 id="basics">Football data in five ideas</h2>
        <ol className="mh-basics">
          {BASICS.map((b) => <li key={b.title}><h3>{b.title}</h3><p>{b.body}</p></li>)}
        </ol>
      </section>
      <section className="mh-section" aria-labelledby="glossary">
        <h2 id="glossary">Glossary</h2>
        <SearchBox placeholder="Search terms" value={q} onChange={(_, d) => setQ(d.value)} aria-label="Search the glossary" />
        <dl className="mh-glossary">
          {terms.map((g) => <div key={g.term}><dt>{g.term}</dt><dd>{g.simply}</dd></div>)}
          {!terms.length && <p className="mh-muted">No term matches "{q}".</p>}
        </dl>
      </section>
      <section className="mh-section" id="references" aria-labelledby="refs">
        <h2 id="refs">Research and references</h2>
        <ol className="mh-refs">
          {REFERENCES.map((r) => (
            <li key={r.href}><a href={r.href} target="_blank" rel="noreferrer">{r.cite}</a><p className="mh-muted">Why it matters to us: {r.why}</p></li>
          ))}
        </ol>
      </section>
      <section className="mh-section" aria-labelledby="faq">
        <h2 id="faq">Questions people ask</h2>
        <Accordion collapsible multiple>
          {FAQ.map((f) => (
            <AccordionItem key={f.q} value={f.q}><AccordionHeader>{f.q}</AccordionHeader><AccordionPanel><p>{f.a}</p></AccordionPanel></AccordionItem>
          ))}
        </Accordion>
      </section>
    </div>
  );
}
