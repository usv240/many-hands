import { Button, Spinner } from "@fluentui/react-components";
import { DocumentText20Regular } from "@fluentui/react-icons";
import { useState } from "react";
import { type Recap, recap } from "../state/api";
import { Info } from "./Info";
import { ScoreBadge } from "./viz";

const AUDIENCES = [
  { id: "casual", label: "Casual fan" },
  { id: "analyst", label: "Analyst" },
  { id: "es", label: "Spanish" },
] as const;

/** The whole match as a short recap, written by the Recapper and checked sentence by sentence. */
export function MatchRecap({ gameId, live }: { gameId: number; live: boolean }) {
  const [audience, setAudience] = useState<(typeof AUDIENCES)[number]["id"]>("casual");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Recap | null>(null);
  const [error, setError] = useState<string | null>(null);

  const go = async () => {
    setBusy(true); setError(null);
    try { setResult(await recap(gameId, audience)); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  if (!live) return <p className="mh-small mh-muted">The recap is written by the agents on the hosted version.</p>;

  return (
    <div className="mh-recap">
      <div className="mh-row mh-wrap" role="radiogroup" aria-label="Recap for">
        {AUDIENCES.map((a) => (
          <label key={a.id} className="mh-check-inline">
            <input type="radio" name="recap-audience" checked={audience === a.id} onChange={() => setAudience(a.id)} />
            {a.label}
          </label>
        ))}
      </div>
      <div>
        <Button icon={busy ? <Spinner size="tiny" /> : <DocumentText20Regular />} onClick={go} disabled={busy}>
          {busy ? "Writing the recap" : "Write the match recap"}
        </Button>
      </div>
      {error && <p className="mh-bad" role="alert">{error}</p>}
      {result && (
        <article className="mh-recap-body" aria-live="polite" lang={result.audience === "es" ? "es" : undefined}>
          <h4>{result.title}</h4>
          <ol className="mh-recap-lines">
            {result.sentences.map((s, i) => (
              <li key={`${i}-${s.text}`} className={s.replaced ? "is-replaced" : undefined}>
                <p>{s.text}</p>
                {s.chain_id && s.si !== null && <ScoreBadge si={s.si} verdict={s.verdict} size="small" />}
                {s.replaced && (
                  <p className="mh-recap-note" lang="en">
                    The Auditor replaced: "{s.replaced}". {s.reasons[0]}
                  </p>
                )}
              </li>
            ))}
          </ol>
          <p className="mh-small mh-muted" lang="en">
            {result.model_used ? `Written by ${result.model} on Microsoft Foundry. ` : "The model was unavailable, so the recap is built from the fair lines. "}
            Every sentence about a goal was scored against that goal's evidence, in code
            {result.replaced ? `; ${result.replaced} replaced` : "; none needed replacing"}. {result.seconds.toFixed(1)} s.
            <Info id="recap" />
          </p>
        </article>
      )}
    </div>
  );
}
