import { Button } from "@fluentui/react-components";
import { Live20Regular } from "@fluentui/react-icons";
import { useEffect, useRef, useState } from "react";
import type { MatchData } from "../engine/types";
import { type AgentResult, kickoff, LIVE_URL } from "../state/api";
import { Info } from "./Info";
import { ScoreBadge } from "./viz";

interface LiveGoal { chainId: string; latency: number; result: AgentResult; minute: number }

/**
 * Plays the match through Azure Event Hubs. Nobody presses a button when a goal goes in: the
 * goal arriving on the stream wakes the agents, and their fair line lands here.
 */
export function LiveFeed({ data, live }: { data: MatchData; live: boolean }) {
  const [running, setRunning] = useState(false);
  const [transport, setTransport] = useState<string | null>(null);
  const [events, setEvents] = useState(0);
  const [last, setLast] = useState<string>("");
  const [waking, setWaking] = useState<string | null>(null);
  const [goals, setGoals] = useState<LiveGoal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const source = useRef<EventSource | null>(null);
  const gameId = data.match.game_id;

  useEffect(() => () => source.current?.close(), []);
  useEffect(() => { source.current?.close(); setRunning(false); setGoals([]); setEvents(0); }, [gameId]);

  const name = (pid: string) => {
    const r = data.roster.find((x) => x.player_id === pid);
    return r ? `#${r.shirt} ${r.name}` : pid;
  };
  const team = (tid: string) => (tid === data.match.home.team_id ? data.match.home.name : data.match.away.name);

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
      if (msg.type === "agent") {
        const minute = data.chains.find((c) => c.chain_id === msg.chain_id)?.minute ?? 0;
        setGoals((g) => [{ chainId: msg.chain_id, latency: msg.latency_s, result: msg.result, minute }, ...g]);
        setWaking(null);
      }
      if (msg.type === "full-time") { setRunning(false); es.close(); }
    };
    es.onerror = () => { if (es.readyState === EventSource.CLOSED) setRunning(false); };
    try {
      const k = await kickoff(gameId);
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
      {error && <p className="mh-bad" role="alert">{error}</p>}
      {running && (
        <p className="mh-live-ticker" aria-live="off">
          <span className="mh-tabular">{events}</span> events received. {last}
        </p>
      )}
      {waking && <p className="mh-live-waking" role="status">Goal at {waking} reached Event Hubs. The agents are writing the line.</p>}
      <ol className="mh-live-goals" aria-live="polite">
        {goals.map((g) => (
          <li key={g.chainId} className="mh-live-goal">
            <div className="mh-row mh-between">
              <strong>{g.minute}'</strong>
              <span className="mh-live-latency">ready {g.latency.toFixed(1)} s after the goal</span>
            </div>
            <p>"{g.result.line}"</p>
            {g.result.audit && <ScoreBadge si={g.result.audit.si} verdict={g.result.audit.verdict} size="small" />}
          </li>
        ))}
      </ol>
      <p className="mh-small mh-muted">A fictional match, sped up: a minute of play every couple of seconds. Nobody presses anything when a goal goes in.</p>
    </div>
  );
}
