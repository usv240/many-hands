import { Button, Spinner } from "@fluentui/react-components";
import { Bot20Regular, ShieldError20Regular } from "@fluentui/react-icons";
import { useState } from "react";
import { type AgentResult, broadcast, LIVE_URL } from "../state/api";
import { Info } from "./Info";
import { ScoreBadge } from "./viz";

const AGENT_JOB: Record<string, string> = {
  Investigator: "gathers the evidence",
  Narrator: "writes and rewrites, with gpt-5-mini",
  Auditor: "scores in code, never by AI",
  Personalizer: "writes each audience version",
  Workflow: "Microsoft Agent Framework",
};

/** The agents at work: each step in the order it ran, with its real duration. */
export function AgentTrace({ result }: { result: AgentResult }) {
  return (
    <ol className="mh-trace" aria-label="What each agent did">
      {result.trace.map((s, i) => (
        <li key={`${s.agent}-${i}`} className={`mh-trace-step${s.model ? " is-model" : ""}`} style={{ animationDelay: `${i * 90}ms` }}>
          <span className="mh-trace-agent">{s.agent}</span>
          <span className="mh-trace-action">{s.action}</span>
          <span className="mh-trace-ms">{s.ms >= 1000 ? `${(s.ms / 1000).toFixed(1)} s` : `${s.ms} ms`}</span>
          {s.detail && s.agent !== "Investigator" && <span className="mh-trace-detail">{s.detail}</span>}
        </li>
      ))}
    </ol>
  );
}

/** Send a line to the real agents on Microsoft Foundry and show their work. */
export function AgentDesk({ chainId, line, live, onResult }:
  { chainId: string; line?: string; live: boolean; onResult?: (r: AgentResult) => void }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AgentResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [outage, setOutage] = useState(false);

  const run = async () => {
    setBusy(true); setError(null); setResult(null);
    try {
      const r = await broadcast({ chain_id: chainId, text: line, simulate_auditor_outage: outage });
      setResult(r); onResult?.(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!live) {
    return (
      <div className="mh-desk mh-desk--offline">
        <p><Bot20Regular aria-hidden /> The AI agents run on the hosted version, on Microsoft Foundry.</p>
        <a className="mh-btn" href={`${LIVE_URL}/studio`}>Open the live Studio</a>
      </div>
    );
  }

  return (
    <div className="mh-desk">
      <div className="mh-row mh-wrap">
        <Button appearance="primary" icon={busy ? <Spinner size="tiny" /> : <Bot20Regular />} onClick={run} disabled={busy}>
          {busy ? "The agents are working" : line ? "Fix it with the agents" : "Have the agents write a line"}
        </Button>
        <label className="mh-check-inline">
          <input type="checkbox" checked={outage} onChange={(e) => setOutage(e.target.checked)} />
          Simulate an Auditor outage
        </label>
        <Info id="failClosed" />
      </div>
      {error && <p className="mh-bad" role="alert">{error} The browser engine still works below.</p>}
      {result && (
        <div className="mh-desk-result" aria-live="polite">
          {result.status === "held" ? (
            <p className="mh-held"><ShieldError20Regular aria-hidden /> <strong>Held. Nothing airs.</strong> {result.held_reason}</p>
          ) : (
            <>
              {result.history.length > 1 && (
                <div className="mh-before-after">
                  <div className="mh-ba-row is-before">
                    <span className="mh-ba-label">Sent in</span>
                    <p>"{result.history[0].text}"</p>
                    <ScoreBadge si={result.history[0].si} verdict={result.history[0].verdict} size="small" />
                  </div>
                  <div className="mh-ba-row is-after">
                    <span className="mh-ba-label">Ready for air</span>
                    <p>"{result.line}"</p>
                    {result.audit && <ScoreBadge si={result.audit.si} verdict={result.audit.verdict} size="small" />}
                  </div>
                </div>
              )}
              {result.history.length <= 1 && result.audit && (
                <div className="mh-ba-row is-after">
                  <span className="mh-ba-label">Ready for air</span>
                  <p>"{result.line}"</p>
                  <ScoreBadge si={result.audit.si} verdict={result.audit.verdict} size="small" />
                </div>
              )}
            </>
          )}
          <AgentTrace result={result} />
          <p className="mh-small mh-muted">
            {result.model_used ? `Written by ${result.model} on Microsoft Foundry, orchestrated by Microsoft Agent Framework.` : "The model was unavailable, so the fair template was used."}
            {" "}Every number above was measured on this run.
          </p>
        </div>
      )}
    </div>
  );
}

export { AGENT_JOB };
