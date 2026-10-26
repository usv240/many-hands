import { Button, Field, Input } from "@fluentui/react-components";
import { Live20Regular, ShieldError20Regular } from "@fluentui/react-icons";
import { useEffect, useRef, useState } from "react";
import type { MatchData } from "../engine/types";
import { type AgentResult, decide, getLog, kickoff, LIVE_URL } from "../state/api";
import { Info } from "./Info";
import { ScoreBadge } from "./viz";

type Verdict = "fair" | "watch" | "unfair";
type Evidence = "confirmed" | "rejected" | "unclear";

interface LiveGoal {
  chainId: string; minute: number;
  line: string | null; audit: { si: number; verdict: Verdict } | null;
  lineLatency: number | null;      // goal reaching Event Hubs to the line on air, or queued for a producer
  latency: number | null;          // goal to all five audience versions
  sentTo: string | null;
  status: "aired" | "pending" | "approved" | "rejected" | "held" | "writing";
  versions: number | null; heldReason: string | null;
  check: { index: number; minute: number; question: string } | null;   // the Investigator's one question
}

/**
 * Plays the match through Azure Event Hubs. Nobody presses a button when a goal goes in: the
 * goal arriving on the stream wakes the agents. A Fair line airs at once; anything else waits
 * here for a producer, and every decision goes into the hash-chained log.
 */
export function LiveFeed({ data, live }: { data: MatchData; live: boolean }) {
  const [running, setRunning] = useState(false);
  const [transport, setTransport] = useState<string | null>(null);
  const [events, setEvents] = useState(0);
  const [last, setLast] = useState<string>("");
  const [waking, setWaking] = useState<string | null>(null);
  const [goals, setGoals] = useState<LiveGoal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [log, setLog] = useState<{ ok: boolean; entries: number } | null>(null);
  const [autoAir, setAutoAir] = useState(true);
  const source = useRef<EventSource | null>(null);
  const gameId = data.match.game_id;

  useEffect(() => () => source.current?.close(), []);
  useEffect(() => { source.current?.close(); setRunning(false); setGoals([]); setEvents(0); }, [gameId]);

  const name = (pid: string) => {
    const r = data.roster.find((x) => x.player_id === pid);
    return r ? `#${r.shirt} ${r.name}` : pid;
  };
  const team = (tid: string) => (tid === data.match.home.team_id ? data.match.home.name : data.match.away.name);
  const minuteOf = (chainId: string) => data.chains.find((c) => c.chain_id === chainId)?.minute ?? 0;
  const refreshLog = () => getLog().then((l) => l && setLog({ ok: l.verify.ok, entries: l.verify.entries }));

  const upsert = (chainId: string, patch: Partial<LiveGoal>) => setGoals((gs) => {
    const i = gs.findIndex((g) => g.chainId === chainId);
    if (i === -1) {
      return [{ chainId, minute: minuteOf(chainId), line: null, audit: null, lineLatency: null, latency: null,
                sentTo: null, status: "writing", versions: null, heldReason: null, check: null, ...patch }, ...gs];
    }
    const next = [...gs];
    next[i] = { ...next[i], ...patch };
    return next;
  });

  const start = async () => {
    setError(null); setGoals([]); setEvents(0);
    source.current?.close();
    const es = new EventSource(`/v1/matches/${gameId}/live`);
    source.current = es;
    es.onmessage = (m) => {
      const msg = JSON.parse(m.data);
      if (msg.type === "hello" || msg.type === "kickoff") setTransport(msg.transport);
      if (msg.type === "event") {
        setEvents((n) => n + 1);
        const minute = Math.floor(msg.clock_s / 60) + (msg.period === 2 ? 45 : 0);
        setLast(`${minute}' ${team(msg.team_id)}: ${name(msg.player_id)}, ${String(msg.action_type).replace("_", " ")}`);
        if (msg.decisive) setWaking(`${minute}'`);
      }
      if (msg.type === "line") {
        upsert(msg.chain_id, { line: msg.line, audit: msg.audit, lineLatency: msg.line_latency_s, sentTo: msg.graphic_sent_to, check: msg.check ?? null,
                               status: msg.queued ? "pending" : "aired" });
        setWaking(null);
        refreshLog();
      }
      if (msg.type === "agent") {
        const r: AgentResult = msg.result;
        upsert(msg.chain_id, r.status === "held"
          ? { status: "held", heldReason: r.held_reason, latency: msg.latency_s }
          : { latency: msg.latency_s, versions: r.variants.filter((v) => v.aired).length });
        setWaking(null);
        refreshLog();
      }
      if (msg.type === "decided") {
        upsert(msg.item.chain_id, { status: msg.item.status, sentTo: msg.graphic_sent_to });
        refreshLog();
      }
      if (msg.type === "full-time") { setRunning(false); es.close(); }
    };
    es.onerror = () => { if (es.readyState === EventSource.CLOSED) setRunning(false); };
    try {
      const k = await kickoff(gameId, autoAir);
      setTransport(k.transport); setRunning(true);
    } catch (e) {
      setError((e as Error).message); es.close();
    }
  };

  const stop = async () => {
    await fetch(`/v1/matches/${gameId}/stop`, { method: "POST" }).catch(() => undefined);
    source.current?.close(); setRunning(false);
  };

  if (!live) {
    return (
      <div className="mh-desk mh-desk--offline">
        <p><Live20Regular aria-hidden /> The live feed runs on the hosted version, through Azure Event Hubs.</p>
        <a className="mh-btn" href={`${LIVE_URL}/studio`}>Open the live Studio</a>
      </div>
    );
  }

  return (
    <div className="mh-live">
      <div className="mh-row mh-wrap">
        {running
          ? <Button onClick={stop}>Stop the feed</Button>
          : <Button appearance="primary" icon={<Live20Regular />} onClick={start}>Kick off the live feed</Button>}
        {transport && <span className="mh-status"><span className="mh-status-dot" aria-hidden />Through {transport}<Info id="liveFeed" /></span>}
      </div>
      <span className="mh-term">
        <label className="mh-check-inline">
          <input type="checkbox" checked={autoAir} disabled={running} onChange={(e) => setAutoAir(e.target.checked)} />
          Air Fair lines automatically. Turn off to approve every line yourself.
        </label>
        <Info id="autoAir" />
      </span>
      {error && <p className="mh-bad" role="alert">{error}</p>}
      {running && (
        <p className="mh-live-ticker" aria-live="off">
          <span className="mh-tabular">{events}</span> events received. {last}
        </p>
      )}
      {waking && <p className="mh-live-waking" role="status">Goal at {waking} reached Event Hubs. The agents are writing the line.</p>}
      <ol className="mh-live-goals" aria-live="polite">
        {goals.map((g) => <LiveGoalItem key={g.chainId} g={g} />)}
      </ol>
      {log && (
        <p className="mh-small mh-muted">
          Decision log on the server: {log.entries} {log.entries === 1 ? "entry" : "entries"}, {log.ok ? "chain intact" : "chain broken"}.
          Every record is also written to Event Hubs. <a href="/v1/log" target="_blank" rel="noreferrer">See the log</a>
        </p>
      )}
      <p className="mh-small mh-muted">A fictional match, sped up: a minute of play every couple of seconds. Nobody presses anything when a goal goes in;{" "}
        {autoAir ? "a Fair line airs on its own, and anything else waits for you." : "every line waits for you."}</p>
    </div>
  );
}

function LiveGoalItem({ g }: { g: LiveGoal }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answer, setAnswer] = useState<Evidence | null>(g.check ? null : "confirmed");
  const fair = g.audit?.verdict === "fair";
  const needsReason = !fair || answer === "unclear";

  const send = async (decision: "approve" | "reject", evidence: Evidence | null = answer) => {
    setBusy(true); setError(null);
    try { await decide(g.chainId, decision, reason.trim(), undefined, g.check ? evidence ?? undefined : undefined); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  const timing = g.lineLatency !== null
    ? `${g.status === "aired" ? "on air" : "line ready"} ${g.lineLatency.toFixed(1)} s after the goal${g.latency !== null ? `; ${g.versions ?? 0} versions by ${g.latency.toFixed(1)} s` : ""}`
    : g.latency !== null ? `${g.latency.toFixed(1)} s after the goal` : "the agents are writing";

  return (
    <li className={`mh-live-goal${g.status === "pending" ? " is-pending" : ""}`}>
      <div className="mh-row mh-between">
        <strong>{g.minute}'</strong>
        <span className="mh-live-latency">{timing}</span>
      </div>
      {g.status === "held" ? (
        <p className="mh-held"><ShieldError20Regular aria-hidden /> Held. Nothing aired. {g.heldReason}</p>
      ) : g.line && (
        <>
          <p>"{g.line}"</p>
          <div className="mh-row mh-wrap">
            {g.audit && <ScoreBadge si={g.audit.si} verdict={g.audit.verdict} size="small" />}
            {g.status === "aired" && g.sentTo && <span className="mh-small mh-muted">Aired automatically: sent to {g.sentTo}</span>}
            {g.status === "approved" && <span className="mh-small mh-muted">Approved by you{fair ? "" : " with a reason"}{g.sentTo ? `, sent to ${g.sentTo}` : ""}</span>}
            {g.status === "rejected" && <span className="mh-small mh-muted">Rejected by you. It did not air.</span>}
            {g.status === "pending" && g.check && answer === null && <span className="mh-small mh-muted">Answer the Investigator's question to air it.</span>}
          </div>
        </>
      )}
      {g.status === "pending" && (
        <div className="mh-live-decide">
          <p className="mh-small">{fair
            ? "Scored Fair, but waiting for you because automatic airing is off. Nothing airs until you decide."
            : "Not clearly fair, so it waits for you. Nothing airs until you decide."}</p>
          {g.check && (
            <div className="mh-live-check" role="group" aria-label="Evidence check from the Investigator">
              <p className="mh-small mh-term"><strong>The Investigator asks</strong><Info id="evidenceCheck" /></p>
              <p className="mh-small">{g.check.question}</p>
              <div className="mh-row mh-wrap">
                <Button size="small" appearance={answer === "confirmed" ? "primary" : "secondary"} aria-pressed={answer === "confirmed"}
                  disabled={busy} onClick={() => setAnswer("confirmed")}>Yes, it does</Button>
                <Button size="small" disabled={busy} onClick={() => { setAnswer("rejected"); send("reject", "rejected"); }}>No, the data is wrong</Button>
                <Button size="small" appearance={answer === "unclear" ? "primary" : "subtle"} aria-pressed={answer === "unclear"}
                  disabled={busy} onClick={() => setAnswer("unclear")}>Can't tell</Button>
              </div>
            </div>
          )}
          {needsReason && answer !== null && (
            <Field label={<span className="mh-term">Reason, needed to air it<Info id="reasonRequired" /></span>}>
              <Input value={reason} onChange={(_, d) => setReason(d.value)} placeholder="For example: the replay shows he was left alone" />
            </Field>
          )}
          <div className="mh-row mh-wrap">
            <Button size="small" appearance="primary" disabled={busy || answer === null || (needsReason && !reason.trim())}
              onClick={() => send("approve")}>
              {needsReason ? "Air with this reason" : "Air it"}
            </Button>
            <Button size="small" disabled={busy} onClick={() => send("reject")}>Don't air</Button>
          </div>
          {error && <p className="mh-bad mh-small" role="alert">{error}</p>}
        </div>
      )}
    </li>
  );
}
