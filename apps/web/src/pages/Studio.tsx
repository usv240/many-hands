import {
  Badge, Button, Dropdown, Field, Input, MessageBar, MessageBarBody, Option, Switch, Textarea,
} from "@fluentui/react-components";
import {
  CheckmarkCircle20Regular, Dismiss20Regular, Edit20Regular, LockClosed16Regular, QuestionCircle20Regular,
  ShieldError20Regular, Wand20Regular,
} from "@fluentui/react-icons";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AgentDesk } from "../components/AgentDesk";
import { decidingAction, EvidenceCheck, type EvidenceStatus } from "../components/EvidenceCheck";
import { Info, Term } from "../components/Info";
import { LiveFeed } from "../components/LiveFeed";
import { MatchRecap } from "../components/MatchRecap";
import { PageHeader } from "../components/Layout";
import { PitchReplay } from "../components/Pitch";
import { ResponsibilityBars, ScoreBadge } from "../components/viz";
import { audit } from "../engine/audit";
import { append, type LogEntry, verifyLog } from "../engine/auditLog";
import { Roster } from "../engine/extraction";
import { onballBlame, type RatedAction } from "../engine/ledger";
import { type Chain, DEFAULT_POLICY, type MatchData } from "../engine/types";
import { audienceVersions, type Candidate, candidates, teamName } from "../engine/writer";
import { liveAi, useHealth } from "../state/api";
import { loadMatch, loadMatches, SHOWCASE, useAsync } from "../state/data";
import { getUploaded } from "../state/uploads";
import { chainLabel } from "./Check";

const REGIONS = [
  "Moments: every goal and big chance in the match. Pick one.",
  "The build-up on the pitch and who was responsible for how much.",
  "Pre-air queue: lines waiting to go on screen, each with a fairness score.",
  "Audience versions: the same moment told for different viewers, each checked.",
  "Audit log: every decision, fingerprinted and chained.",
  "AI desk: the real agents on Microsoft Foundry fix a line, and the live feed through Azure Event Hubs wakes them on every goal.",
];

function Region({ n, on, children, className }: { n: number; on: boolean; children: ReactNode; className?: string }) {
  return (
    <section className={`mh-region ${className ?? ""}`} aria-label={REGIONS[n - 1]}>
      {on && <span className="mh-region-badge" aria-hidden>{n}</span>}
      {children}
    </section>
  );
}

export default function Studio() {
  const [params, setParams] = useSearchParams();
  const matches = useAsync(loadMatches, []);
  const gameId = Number(params.get("match") ?? SHOWCASE.gameId);
  const uploaded = getUploaded(gameId);
  const loaded = useAsync(() => (uploaded ? Promise.resolve(uploaded) : loadMatch(gameId)), [gameId]);
  const data = loaded.data;
  const [chainId, setChainId] = useState<string | undefined>();
  useEffect(() => {
    if (data) setChainId(params.get("chain") ?? (gameId === SHOWCASE.gameId ? SHOWCASE.chainId : data.chains.find((c) => c.goal)?.chain_id));
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps
  const baseChain = data?.chains.find((c) => c.chain_id === chainId);
  const { health } = useHealth();
  const live = liveAi(health);

  // Evidence check: the producer's answer can remove a data error and change every score below.
  const [evidence, setEvidence] = useState<EvidenceStatus>("pending");
  const [excluded, setExcluded] = useState<number[]>([]);
  useEffect(() => { setEvidence("pending"); setExcluded([]); }, [chainId, gameId]);
  const chain: Chain | undefined = useMemo(() => {
    if (!baseChain || !data || !excluded.length) return baseChain;
    const acts = baseChain.actions.filter((a) => !excluded.includes(a.action_id)) as RatedAction[];
    const shares = onballBlame(acts, baseChain.conceding_team_id);
    const responsibility = Object.entries(shares).sort((a, b) => b[1] - a[1]).map(([pid, share]) => {
      const r = data.roster.find((x) => x.player_id === pid);
      const old = baseChain.responsibility.find((x) => x.player_id === pid);
      return { player_id: pid, name: r?.name ?? pid, shirt: r?.shirt ?? null, share, reason: old?.reason ?? "involved in the build-up" };
    });
    return { ...baseChain, shares, responsibility };
  }, [baseChain, data, excluded]);
  const deciding = baseChain ? decidingAction(baseChain) : null;
  const unconfirmed = evidence === "unclear" ? deciding?.player_id : undefined;

  const [explain, setExplain] = useState(false);
  const [outage, setOutage] = useState(false);
  const [broadcast, setBroadcast] = useState(false);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [aired, setAired] = useState<string | null>(null);
  const [verifyMsg, setVerifyMsg] = useState<string | null>(null);
  const [featured, setFeatured] = useState<string | undefined>();

  const queue = useMemo(() => (data && chain ? candidates(data, chain) : []), [data, chain]);
  const [deskLine, setDeskLine] = useState<string | undefined>();
  useEffect(() => { setDeskLine(queue.find((q) => q.result.verdict === "unfair")?.text); }, [queue]);
  const versions = useMemo(() => (data && chain ? audienceVersions(data, chain, featured) : []), [data, chain, featured]);

  const record = async (c: { text: string; si: number; verdict: string }, action: LogEntry["action"], reason?: string) => {
    if (!chain) return;
    setLog(await append(log, { chain_id: chain.chain_id, text: c.text, si: c.si, verdict: c.verdict, action, reason }));
    if (action !== "rejected") setAired(c.text);
    setVerifyMsg(null);
  };

  return (
    <div className="mh-page mh-studio">
      <PageHeader title="Studio" purpose="The screen a TV producer uses during a match: see who caused each goal, and decide which lines go on air. This one replays a fictional match.">
        <ol className="mh-howto" aria-label="How to use this screen">
          <li><strong>Pick a goal</strong> on the left. The pitch shows the moves that led to it.</li>
          <li><strong>Answer the evidence check</strong> under the pitch: one question about the action that matters most.</li>
          <li><strong>Decide each line</strong> in the pre-air queue on the right: approve, use the fair version, or reject. Below, the AI desk and live feed show the agents doing the same job by themselves.</li>
        </ol>
        <div className="mh-studio-bar">
          {matches.data && (
            <Dropdown aria-label="Match" className="mh-studio-match"
              value={data ? `${data.match.home.name} ${data.match.score[0]} - ${data.match.score[1]} ${data.match.away.name}` : ""}
              selectedOptions={[String(gameId)]}
              onOptionSelect={(_, d) => { setParams({ match: d.optionValue! }); setLog([]); setAired(null); }}>
              {matches.data.map((m) => (
                <Option key={m.game_id} value={String(m.game_id)} text={`${m.home.name} ${m.score[0]} - ${m.score[1]} ${m.away.name}`}>
                  {`${m.home.name} ${m.score[0]} - ${m.score[1]} ${m.away.name}`}
                </Option>
              ))}
            </Dropdown>
          )}
          <span className="mh-status"><span className="mh-status-dot" aria-hidden />Replay mode<Info id="replay" /></span>
          <span className="mh-status">Policy: Watch above {DEFAULT_POLICY.watch_above.toFixed(2)}, Unfair above {DEFAULT_POLICY.unfair_above.toFixed(2)}<Info id="policy" /></span>
          <Switch label="Explain this screen" checked={explain} onChange={(_, d) => setExplain(d.checked)} />
          <span className="mh-term"><Switch label="Broadcast preview" checked={broadcast} onChange={(_, d) => setBroadcast(d.checked)} /><Info id="broadcast" /></span>
          <span className="mh-term"><Switch label="Simulate fairness check outage" checked={outage} onChange={(_, d) => setOutage(d.checked)} /><Info id="failClosed" /></span>
        </div>
        {explain && (
          <ol className="mh-explain-list" aria-label="What each numbered area does">
            {REGIONS.map((r, i) => <li key={r}><span className="mh-region-badge">{i + 1}</span>{r}</li>)}
          </ol>
        )}
      </PageHeader>

      {!data || !chain ? <div className="mh-skeleton" style={{ height: 420 }} /> : (
        <div className="mh-studio-grid">
          <Region n={1} on={explain} className="mh-moments">
            <h2 className="mh-pane-title">Moments</h2>
            <p className="mh-small mh-muted">Goals and big chances in this match. <span className="mh-term">Shared<Info id="sharedTag" /></span> means no one player carried most of the blame.</p>
            <ul className="mh-moment-list">
              {data.chains.map((c) => (
                <li key={c.chain_id}>
                  <button type="button" className={`mh-moment${c.chain_id === chain.chain_id ? " is-on" : ""}`}
                          aria-pressed={c.chain_id === chain.chain_id} onClick={() => setChainId(c.chain_id)}>
                    <span className="mh-moment-min">{c.minute}'</span>
                    <span>{c.goal ? "Goal" : "Chance"}, {teamName(data, c.attacking_team_id)}</span>
                    {c.responsibility.length > 1 && <Badge size="small" appearance="tint" title="Blame is shared: no single player carried 60 percent or more">shared</Badge>}
                  </button>
                </li>
              ))}
            </ul>
          </Region>

          <Region n={2} on={explain} className="mh-evidence">
            <h2 className="mh-pane-title"><Term id="evidence">{chainLabel(data, chain.chain_id)}</Term></h2>
            <PitchReplay actions={chain.actions} data={data} highlight={chain.responsibility.map((c) => c.player_id)}
                         focusActionId={evidence === "pending" ? deciding?.action_id : undefined} />
            <EvidenceCheck chain={baseChain!} data={data} status={evidence}
              onAnswer={async (s, action) => {
                setEvidence(s);
                if (s === "rejected") setExcluded([action.action_id]);
                const pl = data.roster.find((r) => r.player_id === action.player_id);
                setLog(await append(log, { chain_id: chain.chain_id, si: 0, verdict: "evidence",
                  text: `Action ${action.action_id}: number ${pl?.shirt ?? "?"} ${action.type_name}, ${action.result_name}`,
                  action: s === "confirmed" ? "evidence confirmed" : s === "rejected" ? "evidence rejected" : "evidence unclear" }));
              }} />
            <h3 className="mh-term">Who was responsible<Info id="responsibility" /></h3>
            <ResponsibilityBars team={chain.conceding_team_id === data.match.home.team_id ? "a" : "b"} caption="Responsibility"
              rows={chain.responsibility.map((c) => ({ id: c.player_id, label: `#${c.shirt} ${c.name}`, share: c.share, note: c.reason }))} />
            {chain.unsung && (
              <div className="mh-unsung">
                <p className="mh-term"><strong>Unsung</strong><Info id="unsung" /></p>
                <p>#{chain.unsung.shirt} {chain.unsung.name}, {teamName(data, chain.attacking_team_id)}: {chain.unsung.reason}.</p>
              </div>
            )}
          </Region>

          <Region n={3} on={explain} className="mh-queue">
            <h2 className="mh-pane-title"><Term id="queue">Pre-air queue</Term></h2>
            <p className="mh-small mh-muted">Three lines someone wants to air about this goal. Each has its fairness score. Decide each one.</p>
            {outage ? (
              <MessageBar intent="error" icon={<ShieldError20Regular />}>
                <MessageBarBody>
                  <strong>Held. Nothing airs.</strong> The fairness check is unavailable, so every line is held until it is back.
                  This is what fails closed means.
                </MessageBarBody>
              </MessageBar>
            ) : null}
            {queue.map((c) => (
              <QueueCard key={`${chain.chain_id}-${c.id}-${excluded.join(",")}`} c={c} chain={chain} data={data} disabled={outage}
                         unconfirmed={unconfirmed} onDecide={record} onSendToAgents={(text) => setDeskLine(text)} />
            ))}
          </Region>

          <Region n={4} on={explain} className="mh-audiences">
            <h2 className="mh-pane-title"><Term id="audience">Audience versions</Term></h2>
            <p className="mh-small mh-muted">The same goal told for five kinds of viewer, each checked for fairness. Pick whose story the player-focus version follows.</p>
            <Field label="Player-focus version follows">
              <Dropdown value={featured ? labelFor(data, featured) : "Most responsible player"} selectedOptions={featured ? [featured] : []}
                onOptionSelect={(_, d) => setFeatured(d.optionValue)}>
                {data.roster.filter((r) => r.team_id === chain.conceding_team_id).map((r) => (
                  <Option key={r.player_id} value={r.player_id} text={labelFor(data, r.player_id)}>{labelFor(data, r.player_id)}</Option>
                ))}
              </Dropdown>
            </Field>
            <div className="mh-audience-grid">
              {versions.map((v) => (
                <article key={v.id} className="mh-card mh-audience">
                  <header><strong>{v.audience}</strong><span className="mh-small mh-muted">{v.description}. {v.language}.</span></header>
                  <p>"{v.text}"</p>
                  <ScoreBadge si={v.result.si} verdict={v.result.verdict} size="small" />
                  {v.note && <p className="mh-small mh-muted">{v.note}</p>}
                </article>
              ))}
            </div>
            <p className="mh-small mh-muted">
              {live ? "These quick drafts come from a template in your browser, so they appear instantly. The AI desk below shows the versions the AI writes for the same goal."
                    : "Drafts from the template writer, checked in your browser. On the hosted site the Personalizer agent writes these with Microsoft Foundry."}
            </p>
          </Region>

          <Region n={6} on={explain} className="mh-desk-region">
            <h2 className="mh-pane-title"><Term id="agents">AI desk</Term></h2>
            <div className="mh-desk-grid">
              <div>
                <h3>Fix a line with the agents</h3>
                <p className="mh-small mh-muted">{deskLine ? <>Line: "{deskLine}"</> : "No line chosen: the agents will write one."}</p>
                <AgentDesk key={`${chain.chain_id}-${deskLine}`} chainId={chain.chain_id} line={deskLine} live={live}
                  onResult={async (r) => {
                    if (r.status === "ready" && r.line && r.audit && deskLine) {
                      setLog(await append(log, { chain_id: chain.chain_id, text: r.line, si: r.audit.si, verdict: r.audit.verdict, action: "agents fixed it" }));
                      setAired(r.line);
                    }
                  }} />
              </div>
              <div>
                <h3 className="mh-term">Live feed<Info id="liveFeed" /></h3>
                <LiveFeed data={data} live={live} />
                <h3 className="mh-term mh-recap-title">Match recap<Info id="recap" /></h3>
                <MatchRecap key={data.match.game_id} gameId={data.match.game_id} live={live} />
              </div>
            </div>
          </Region>

          <Region n={5} on={explain} className="mh-log">
            <h2 className="mh-pane-title"><Term id="auditLog">Audit log</Term></h2>
            {!log.length ? <p className="mh-muted">No decisions yet. Approve, rewrite or reject a line in the queue.</p> : (
              <div className="mh-table-wrap">
                <table className="mh-table">
                  <thead><tr><th>#</th><th>Decision</th><th>Score</th><th>Line</th><th>Fingerprint</th></tr></thead>
                  <tbody>
                    {log.map((e) => (
                      <tr key={e.seq}>
                        <td>{e.seq}</td><td>{e.action}{e.reason ? `: ${e.reason}` : ""}</td>
                        <td>{e.si.toFixed(2)} {e.verdict}</td><td>{e.text}</td>
                        <td><code title={e.hash}>{e.hash.slice(0, 10)}</code></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="mh-row">
              <Button size="small" icon={<LockClosed16Regular />} disabled={!log.length}
                onClick={async () => { const bad = await verifyLog(log); setVerifyMsg(bad ? `Broken at entry ${bad}: the log was changed.` : `Intact: all ${log.length} fingerprints match.`); }}>
                Verify the chain
              </Button>
              <Button size="small" appearance="subtle" disabled={!log.length}
                onClick={() => { setLog((l) => l.map((e, i) => (i === 0 ? { ...e, text: `${e.text} (edited later)` } : e))); setVerifyMsg(null); }}>
                Tamper with entry 1
              </Button>
            </div>
            {verifyMsg && <p role="status" className={verifyMsg.startsWith("Intact") ? "mh-ok" : "mh-bad"}>{verifyMsg}</p>}
          </Region>
        </div>
      )}

      {broadcast && data && chain && (
        <div className="mh-broadcast" role="img" aria-label="Broadcast preview with the approved graphic">
          <div className="mh-broadcast-frame">
            <div className="mh-broadcast-score">{data.match.home.name} {data.match.score[0]} - {data.match.score[1]} {data.match.away.name}</div>
            <div className="mh-broadcast-chain">
              {chain.responsibility.slice(0, 3).map((c) => <span key={c.player_id}>#{c.shirt} {Math.round(c.share * 100)}%</span>)}
            </div>
            <div className="mh-lower-third">{aired ?? "No line approved yet"}</div>
          </div>
        </div>
      )}
      <p className="mh-note"><QuestionCircle20Regular aria-hidden /> First time here? Turn on <strong>Explain this screen</strong>, or read <Link to="/how-it-works">How it works</Link>.</p>
    </div>
  );
}

const labelFor = (data: MatchData, pid: string) => {
  const r = data.roster.find((x) => x.player_id === pid);
  return r ? `#${r.shirt} ${r.name}` : pid;
};

function QueueCard({ c, chain, data, disabled, unconfirmed, onDecide, onSendToAgents }:
  { c: Candidate; chain: Chain; data: MatchData; disabled: boolean; unconfirmed?: string;
    onDecide: (c: { text: string; si: number; verdict: string }, a: LogEntry["action"], reason?: string) => void;
    onSendToAgents: (text: string) => void }) {
  const [current, setCurrent] = useState(c);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(c.text);
  const [askReason, setAskReason] = useState(false);
  const [reason, setReason] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const [why, setWhy] = useState(false);
  const r = useMemo(() => audit(current.text, chain.shares, new Roster(data.roster), chain.conceding_team_id, undefined, chain.goal),
    [current.text, chain, data]);
  const needsReason = r.verdict === "unfair" || (!!unconfirmed && (r.blame[unconfirmed] ?? 0) > 0);
  const recheck = (text: string) => {
    setCurrent({ ...current, text, result: audit(text, chain.shares, new Roster(data.roster), chain.conceding_team_id, undefined, chain.goal) });
  };

  if (done) return <article className="mh-card mh-queue-card is-done"><p className="mh-small"><CheckmarkCircle20Regular aria-hidden /> {done}</p></article>;

  return (
    <article className={`mh-card mh-queue-card mh-queue--${r.verdict}`}>
      <header className="mh-row mh-between">
        <span className="mh-small mh-muted">{current.source}</span>
        <ScoreBadge si={r.si} verdict={r.verdict} size="small" />
      </header>
      {editing ? (
        <Field label="Edit the line"><Textarea value={draft} onChange={(_, d) => setDraft(d.value)} rows={2} /></Field>
      ) : <p className="mh-queue-text">"{current.text}"</p>}
      <button type="button" className="mh-linkbtn" aria-expanded={why} onClick={() => setWhy((w) => !w)}>{why ? "Hide why" : "Why this score?"}</button>
      {why && <ul className="mh-reasons">{r.reasons.map((x) => <li key={x}>{x}</li>)}<li>{r.contrastive}</li></ul>}
      {askReason && (
        <Field label={<span className="mh-term">{r.verdict === "unfair" ? "Reason for airing an Unfair line" : "Reason: this line blames a player whose evidence is unconfirmed"}<Info id="reasonRequired" /></span>} required>
          <Input value={reason} onChange={(_, d) => setReason(d.value)} placeholder="For example: quoting the manager directly" />
        </Field>
      )}
      <div className="mh-row mh-wrap">
        {editing ? (
          <>
            <Button size="small" appearance="primary" onClick={() => { recheck(draft); setEditing(false); }}>Re-check</Button>
            <Button size="small" onClick={() => setEditing(false)}>Cancel</Button>
          </>
        ) : askReason ? (
          <>
            <Button size="small" appearance="primary" disabled={!reason.trim() || disabled}
              onClick={() => { onDecide({ text: current.text, si: r.si, verdict: r.verdict }, "approved with reason", reason.trim()); setDone("Aired with a recorded reason."); }}>
              Air with this reason
            </Button>
            <Button size="small" onClick={() => setAskReason(false)}>Cancel</Button>
          </>
        ) : (
          <>
            <span className="mh-term">
              <Button size="small" appearance="primary" icon={<CheckmarkCircle20Regular />} disabled={disabled}
                onClick={() => {
                  if (needsReason) { setAskReason(true); return; }
                  onDecide({ text: current.text, si: r.si, verdict: r.verdict }, "approved"); setDone("Approved for air.");
                }}>Approve</Button>
              <Info id="approve" />
            </span>
            {r.fairRewrite && (
              <Button size="small" icon={<Wand20Regular />} disabled={disabled}
                onClick={() => {
                  const fr = audit(r.fairRewrite!, chain.shares, new Roster(data.roster), chain.conceding_team_id, undefined, chain.goal);
                  onDecide({ text: r.fairRewrite!, si: fr.si, verdict: fr.verdict }, "used fair version"); setDone(`Fair version aired: "${r.fairRewrite}"`);
                }}>Use fair version</Button>
            )}
            <Button size="small" icon={<Edit20Regular />} onClick={() => { setDraft(current.text); setEditing(true); }}>Edit</Button>
            <Button size="small" appearance="subtle" onClick={() => onSendToAgents(current.text)}>Send to the agents</Button>
            <Button size="small" appearance="subtle" icon={<Dismiss20Regular />} disabled={disabled}
              onClick={() => { onDecide({ text: current.text, si: r.si, verdict: r.verdict }, "rejected"); setDone("Rejected. It will not air."); }}>Reject</Button>
          </>
        )}
      </div>
    </article>
  );
}
