import {
  Accordion, AccordionHeader, AccordionItem, AccordionPanel, Button, Dropdown, Field, Option, Slider,
  Textarea,
} from "@fluentui/react-components";
import { Checkmark16Regular, Copy16Regular, Wand16Regular } from "@fluentui/react-icons";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Info, Term } from "../components/Info";
import { PageHeader } from "../components/Layout";
import { PitchReplay } from "../components/Pitch";
import { ResponsibilityBars, ScaleMeter, ScoreBadge, StoryVsEvidence } from "../components/viz";
import { audit } from "../engine/audit";
import { Roster } from "../engine/extraction";
import { DEFAULT_POLICY, type MatchData, type Policy } from "../engine/types";
import { teamName } from "../engine/writer";
import { loadMatch, loadMatches, SHOWCASE, useAsync } from "../state/data";
import { L } from "../state/prefs";

export default function Check() {
  const [params, setParams] = useSearchParams();
  const matches = useAsync(loadMatches, []);
  const gameId = Number(params.get("match") ?? SHOWCASE.gameId);
  const match = useAsync(() => loadMatch(gameId), [gameId]);
  const data = match.data;
  const chainId = params.get("chain") ?? (gameId === SHOWCASE.gameId ? SHOWCASE.chainId : data?.chains.find((c) => c.goal)?.chain_id);
  const chain = data?.chains.find((c) => c.chain_id === chainId) ?? data?.chains[0];

  const examples = useMemo(() => (data && chain ? makeExamples(data, chain.chain_id) : []), [data, chain]);
  const [text, setText] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [policy, setPolicy] = useState<Policy>(DEFAULT_POLICY);
  const [copied, setCopied] = useState(false);

  useEffect(() => { if (examples.length) { setText(examples[0].text); setSubmitted(examples[0].text); } }, [examples]);

  const result = useMemo(() => {
    if (!data || !chain || !submitted.trim()) return null;
    return audit(submitted, chain.shares, new Roster(data.roster), chain.conceding_team_id, policy, chain.goal);
  }, [data, chain, submitted, policy]);

  const name = (pid: string) => {
    const r = data?.roster.find((x) => x.player_id === pid);
    return r ? `#${r.shirt} ${r.name}` : pid;
  };
  const dumbbell = result
    ? [...new Set([...Object.keys(result.blame), ...Object.keys(result.evidence)])]
        .map((pid) => ({ id: pid, label: name(pid), story: result.blame[pid] ?? 0, evidence: result.evidence[pid] ?? 0 }))
        .sort((a, b) => b.evidence + b.story - (a.evidence + a.story))
    : [];

  const run = () => setSubmitted(text);

  return (
    <div className="mh-page">
      <PageHeader title="Check a sentence" info="si"
        purpose="Pick a goal, write or choose a line about it, and see how fair it is, why, and a fairer version. Everything runs in your browser." />

      <div className="mh-check">
        <section className="mh-panel" aria-labelledby="step1">
          <h2 id="step1"><span className="mh-step-n">1</span> Choose a moment</h2>
          {matches.data && (
            <Field label={<span className="mh-term">Match<Info id="synthetic_data" /></span>}>
              <Dropdown value={matchLabel(matches.data.find((m) => m.game_id === gameId))}
                selectedOptions={[String(gameId)]}
                onOptionSelect={(_, d) => setParams({ match: d.optionValue! })}>
                {matches.data.map((m) => <Option key={m.game_id} value={String(m.game_id)} text={matchLabel(m)}>{matchLabel(m)}</Option>)}
              </Dropdown>
            </Field>
          )}
          {data && (
            <Field label={<span className="mh-term">Goal or chance<Info id="chain" /></span>}>
              <Dropdown value={chain ? chainLabel(data, chain.chain_id) : ""} selectedOptions={chain ? [chain.chain_id] : []}
                onOptionSelect={(_, d) => setParams({ match: String(gameId), chain: d.optionValue! })}>
                {data.chains.map((c) => (
                  <Option key={c.chain_id} value={c.chain_id} text={chainLabel(data, c.chain_id)}>{chainLabel(data, c.chain_id)}</Option>
                ))}
              </Dropdown>
            </Field>
          )}
          {data && chain && (
            <>
              <p className="mh-small mh-muted"><Term id="responsibility">What the evidence says</Term></p>
              <ResponsibilityBars team={chain.conceding_team_id === data.match.home.team_id ? "a" : "b"}
                caption="Responsibility for this moment"
                rows={chain.responsibility.map((c) => ({ id: c.player_id, label: `#${c.shirt} ${c.name}`, share: c.share, note: c.reason }))} />
              <details className="mh-details">
                <summary>Replay the {chain.n_actions} actions</summary>
                <PitchReplay actions={chain.actions} data={data} highlight={chain.responsibility.map((c) => c.player_id)} compact />
              </details>
            </>
          )}
        </section>

        <section className="mh-panel" aria-labelledby="step2">
          <h2 id="step2"><span className="mh-step-n">2</span> Write or pick a line</h2>
          <div className="mh-chips" role="group" aria-label="Example lines">
            {examples.map((e) => (
              <button key={e.kind} type="button" className={`mh-chip${text === e.text ? " is-on" : ""}`}
                      onClick={() => { setText(e.text); setSubmitted(e.text); }}>
                {e.kind}
              </button>
            ))}
          </div>
          <Field label="Line to check" hint="Name players by shirt number (number 5), surname, or role (the keeper).">
            <Textarea value={text} onChange={(_, d) => setText(d.value)} resize="vertical" rows={3}
                      onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) run(); }} />
          </Field>
          <div className="mh-row">
            <Button appearance="primary" onClick={run} disabled={!text.trim()}>Check this line</Button>
            <span className="mh-small mh-muted">or press Ctrl and Enter</span>
          </div>

          <Accordion collapsible>
            <AccordionItem value="policy">
              <div className="mh-row">
                <AccordionHeader size="small">Your fairness limits</AccordionHeader>
                <Info id="policy" />
              </div>
              <AccordionPanel>
                <Field label={`Watch above ${policy.watch_above.toFixed(2)}`}>
                  <Slider min={0.05} max={0.6} step={0.05} value={policy.watch_above}
                    onChange={(_, d) => setPolicy((p) => ({ watch_above: d.value, unfair_above: Math.max(d.value, p.unfair_above) }))} />
                </Field>
                <Field label={`Unfair above ${policy.unfair_above.toFixed(2)}`}>
                  <Slider min={0.1} max={0.9} step={0.05} value={policy.unfair_above}
                    onChange={(_, d) => setPolicy((p) => ({ unfair_above: d.value, watch_above: Math.min(d.value, p.watch_above) }))} />
                </Field>
                <Button size="small" onClick={() => setPolicy(DEFAULT_POLICY)}>Reset to defaults</Button>
              </AccordionPanel>
            </AccordionItem>
          </Accordion>
        </section>

        <section className="mh-panel mh-result" aria-labelledby="step3" aria-live="polite">
          <h2 id="step3"><span className="mh-step-n">3</span> The result</h2>
          {!result ? <p className="mh-muted">Type or pick a line about this moment, then press Check this line.</p> : (
            <>
              <p className="mh-quote">"{result.text}"</p>
              <div className="mh-result-score">
                <ScoreBadge si={result.si} verdict={result.verdict} size="large" />
                <Info id="verdict" />
              </div>
              <ScaleMeter si={result.si} policy={policy} />
              <ul className="mh-reasons">
                {result.reasons.map((r) => <li key={r}>{r}</li>)}
                {result.justified && <li><Term id="justified">Justified blame</Term>: this player really did carry most of the danger.</li>}
              </ul>
              <p><span className="mh-term"><strong>Why this player, not that one</strong><Info id="contrastive" /></span><br />{result.contrastive}</p>
              <StoryVsEvidence rows={dumbbell} />
              {result.fairRewrite && (
                <div className="mh-rewrite">
                  <p className="mh-term"><Wand16Regular aria-hidden /> <strong>Fair version</strong><Info id="fairRewrite" /></p>
                  <p className="mh-quote">"{result.fairRewrite}"</p>
                  <div className="mh-row">
                    <Button size="small" icon={copied ? <Checkmark16Regular /> : <Copy16Regular />}
                      onClick={() => { navigator.clipboard?.writeText(result.fairRewrite!); setCopied(true); window.setTimeout(() => setCopied(false), 1500); }}>
                      {copied ? "Copied" : "Copy"}
                    </Button>
                    <Button size="small" onClick={() => { setText(result.fairRewrite!); setSubmitted(result.fairRewrite!); }}>Check the fair version</Button>
                  </div>
                </div>
              )}
              <details className="mh-details">
                <summary>Show the method</summary>
                <L s={<p>We find who the line blames and how strongly, then compare that with each player's share in the evidence. The score is how far apart the two are.</p>}
                   t={<p>Blame extraction: shirt numbers, surnames and roles resolved against the conceding team; strength 0 to 3 from a word list; group phrases spread over the group; unknown names reported, never guessed. SI = total variation distance between the normalised blame and responsibility distributions. Same code as the API, checked case for case by 154 parity tests.</p>} />
                <pre className="mh-code">{JSON.stringify({ si: result.si, verdict: result.verdict, blame: round(result.blame), evidence: round(result.evidence), unresolved: result.unresolved }, null, 2)}</pre>
              </details>
            </>
          )}
        </section>
      </div>
      <p className="mh-note">Want this in your own tools? Use the <Link to="/developers">API, MCP server or command line</Link>.</p>
    </div>
  );
}

const round = (s: Record<string, number>) => Object.fromEntries(Object.entries(s).map(([k, v]) => [k, Math.round(v * 1000) / 1000]));

function matchLabel(m?: { home: { name: string }; away: { name: string }; score: [number, number] }) {
  return m ? `${m.home.name} ${m.score[0]} - ${m.score[1]} ${m.away.name}` : "";
}

export function chainLabel(data: MatchData, chainId: string) {
  const c = data.chains.find((x) => x.chain_id === chainId)!;
  const who = c.responsibility.length > 1 ? "shared blame" : c.responsibility.length ? "one main cause" : "no lost ball";
  return `${c.minute}' ${c.goal ? "Goal" : "Chance"} for ${teamName(data, c.attacking_team_id)} (${who})`;
}

function makeExamples(data: MatchData, chainId: string) {
  const c = data.chains.find((x) => x.chain_id === chainId)!;
  const team = data.roster.filter((r) => r.team_id === c.conceding_team_id);
  const last = team.find((r) => r.player_id === c.last_touch[0]) ?? team[1];
  const uninvolved = team.find((r) => r.role !== "GK" && !(r.player_id in c.shares)) ?? team[2];
  const top = c.responsibility[0];
  const out = [
    { kind: "Blame one player", text: `Number ${last.shirt}'s howler cost them the goal.` },
    { kind: "Blame the wrong player", text: `${uninvolved.name.split(" ").slice(-1)[0]} was at fault for that one.` },
    { kind: "Blame the defence", text: "The defence switched off completely." },
    { kind: "Neutral", text: "A quick move cut them open down the middle." },
  ];
  if (c.responsibility.length > 1) {
    out.push({ kind: "Share the blame", text: `Loose balls from ${c.responsibility.map((x) => `number ${x.shirt}`).join(" and ")} let them in.` });
  } else if (top) {
    out.push({ kind: "Deserved blame", text: `Number ${top.shirt} lost the ball and they punished it.` });
  }
  return out;
}
