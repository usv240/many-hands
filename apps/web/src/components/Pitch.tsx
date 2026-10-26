import { Button, Slider } from "@fluentui/react-components";
import { Next20Regular, Pause20Filled, Play20Filled, Previous20Regular } from "@fluentui/react-icons";
import { useEffect, useMemo, useState } from "react";
import type { Action, MatchData } from "../engine/types";

const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const verb = (a: Action) => {
  const kind = a.type_name === "dribble" ? "carry" : a.type_name.replace("_", " ");
  return a.result_name === "success" ? kind : `${kind}, lost the ball`;
};

/**
 * Replays a chain on a 2D pitch. Play, pause and step buttons (dragging is never required, WCAG
 * 2.5.7); arrow keys step when focused; with reduced motion the whole chain shows at once.
 */
export function PitchReplay({ actions, data, highlight = [], compact, focusActionId }:
  { actions: Action[]; data: MatchData; highlight?: string[]; compact?: boolean; focusActionId?: number }) {
  const [step, setStep] = useState(() => (reduceMotion() ? actions.length : 1));
  const [playing, setPlaying] = useState(false);
  useEffect(() => { setStep(reduceMotion() ? actions.length : 1); setPlaying(false); }, [actions]);
  useEffect(() => {
    if (focusActionId === undefined) return;
    const i = actions.findIndex((a) => a.action_id === focusActionId);
    if (i >= 0) { setPlaying(false); setStep(i + 1); }
  }, [focusActionId, actions]);
  useEffect(() => {
    if (!playing) return;
    if (step >= actions.length) { setPlaying(false); return; }
    const t = window.setTimeout(() => setStep((s) => s + 1), 650);
    return () => window.clearTimeout(t);
  }, [playing, step, actions.length]);

  const homeId = data.match.home.team_id;
  const name = (pid: string) => data.roster.find((r) => r.player_id === pid);
  const shown = actions.slice(0, step);
  const current = shown[shown.length - 1];
  const caption = useMemo(() => {
    if (!current) return "";
    const p = name(current.player_id);
    const team = current.team_id === homeId ? data.match.home.name : data.match.away.name;
    return `${step} of ${actions.length}: ${team} number ${p?.shirt ?? "?"} ${p?.name ?? ""}, ${verb(current)}`;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, step]);

  return (
    <div className={`mh-pitch-wrap${compact ? " is-compact" : ""}`}>
      <svg viewBox="-2 -2 109 72" className="mh-pitch" role="img"
           aria-label={`Pitch replay of ${actions.length} actions. ${caption}`}
           tabIndex={0}
           onKeyDown={(e) => {
             if (e.key === "ArrowRight") setStep((s) => Math.min(actions.length, s + 1));
             if (e.key === "ArrowLeft") setStep((s) => Math.max(1, s - 1));
           }}>
        <rect x="0" y="0" width="105" height="68" className="mh-pitch-grass" rx="1" />
        <g className="mh-pitch-lines">
          <rect x="0" y="0" width="105" height="68" fill="none" />
          <line x1="52.5" y1="0" x2="52.5" y2="68" />
          <circle cx="52.5" cy="34" r="9.15" fill="none" />
          <rect x="0" y="13.84" width="16.5" height="40.32" fill="none" />
          <rect x="88.5" y="13.84" width="16.5" height="40.32" fill="none" />
          <rect x="0" y="24.84" width="5.5" height="18.32" fill="none" />
          <rect x="99.5" y="24.84" width="5.5" height="18.32" fill="none" />
        </g>
        <defs>
          {(["a", "b"] as const).map((t) => (
            <marker key={t} id={`arrow-${t}`} viewBox="0 0 6 6" refX="5" refY="3" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
              <path d="M0,0 L6,3 L0,6 z" className={`mh-fill-team-${t}`} />
            </marker>
          ))}
        </defs>
        {shown.map((a, i) => {
          const t = a.team_id === homeId ? "a" : "b";
          const isCurrent = i === shown.length - 1;
          const lost = a.result_name !== "success";
          const hl = highlight.includes(a.player_id) && lost;
          const moved = Math.hypot(a.end_x - a.start_x, a.end_y - a.start_y) > 1;
          return (
            <g key={a.action_id} className={`mh-act${isCurrent ? " is-current" : ""}`} opacity={isCurrent ? 1 : 0.55}>
              {moved && (
                <line x1={a.start_x} y1={68 - a.start_y} x2={a.end_x} y2={68 - a.end_y}
                      className={`mh-stroke-team-${t}${a.type_name === "dribble" ? " is-carry" : ""}${lost ? " is-lost" : ""}`}
                      markerEnd={`url(#arrow-${t})`} />
              )}
              {hl && <circle cx={a.start_x} cy={68 - a.start_y} r="3.4" className="mh-act-halo" />}
              <circle cx={a.start_x} cy={68 - a.start_y} r="2.1" className={`mh-fill-team-${t}`} />
              <text x={a.start_x} y={68 - a.start_y + 0.9} className="mh-act-num">{i + 1}</text>
            </g>
          );
        })}
      </svg>
      <div className="mh-pitch-controls">
        <Button size="small" icon={<Previous20Regular />} aria-label="Previous action"
                onClick={() => setStep((s) => Math.max(1, s - 1))} disabled={step <= 1} />
        <Button size="small" appearance="primary" icon={playing ? <Pause20Filled /> : <Play20Filled />}
                onClick={() => { if (step >= actions.length) setStep(1); setPlaying((p) => !p); }}>
          {playing ? "Pause" : step >= actions.length ? "Replay" : "Play"}
        </Button>
        <Button size="small" icon={<Next20Regular />} aria-label="Next action"
                onClick={() => setStep((s) => Math.min(actions.length, s + 1))} disabled={step >= actions.length} />
        <Slider className="mh-pitch-slider" min={1} max={actions.length} value={step}
                aria-label="Action number" onChange={(_, d) => { setPlaying(false); setStep(d.value); }} />
      </div>
      <p className="mh-pitch-caption" aria-live="polite">{caption}</p>
      <div className="mh-legend">
        <span className="mh-legend-item"><span className="mh-swatch mh-team-a" aria-hidden />{data.match.home.name}</span>
        <span className="mh-legend-item"><span className="mh-swatch mh-team-b" aria-hidden />{data.match.away.name}</span>
        <span className="mh-legend-item"><span className="mh-dash" aria-hidden />Dashed: carry (running with the ball)</span>
        <span className="mh-legend-item"><span className="mh-halo-key" aria-hidden />Ring: a lost ball that counts as blame</span>
      </div>
    </div>
  );
}
