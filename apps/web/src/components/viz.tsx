import { CheckmarkCircle16Filled, DismissCircle16Filled, Warning16Filled } from "@fluentui/react-icons";
import type { Verdict } from "../engine/types";
import { Info } from "./Info";

const VERDICT = {
  fair: { label: "Fair", Icon: CheckmarkCircle16Filled },
  watch: { label: "Watch", Icon: Warning16Filled },
  unfair: { label: "Unfair", Icon: DismissCircle16Filled },
} as const;

/** A Scapegoat Index score: number, icon and word, never colour alone. */
export function ScoreBadge({ si, verdict, size = "medium" }: { si: number; verdict: Verdict; size?: "small" | "medium" | "large" }) {
  const v = VERDICT[verdict];
  return (
    <span className={`mh-score mh-score--${verdict} mh-score--${size}`} role="status"
          aria-label={`Scapegoat Index ${si.toFixed(2)}, ${v.label}`}>
      <v.Icon aria-hidden />
      <span className="mh-score-word">{v.label}</span>
      <span className="mh-score-num">{si.toFixed(2)}</span>
    </span>
  );
}

export interface BarRow { id: string; label: string; share: number; note?: string }

/** Sorted horizontal bars with the percentage written at the end of each bar. */
export function ResponsibilityBars({ rows, team, caption }: { rows: BarRow[]; team: "a" | "b"; caption: string }) {
  if (!rows.length) return <p className="mh-muted">No defending action lost the ball in this move.</p>;
  return (
    <figure className="mh-bars" aria-label={caption}>
      <figcaption className="mh-sr">{caption}</figcaption>
      {rows.map((r) => (
        <div className="mh-bar-row" key={r.id}>
          <div className="mh-bar-label">{r.label}</div>
          <div className="mh-bar-track">
            <div className={`mh-bar-fill mh-team-${team}`} style={{ width: `${Math.max(2, r.share * 100)}%` }} />
            <span className="mh-bar-value">{Math.round(r.share * 100)}%</span>
          </div>
          {r.note && <div className="mh-bar-note">{r.note}</div>}
        </div>
      ))}
    </figure>
  );
}

export interface DumbbellRow { id: string; label: string; story: number; evidence: number }

/** Story versus evidence: hollow ring for the sentence's blame, filled dot for the evidence. */
export function StoryVsEvidence({ rows }: { rows: DumbbellRow[] }) {
  if (!rows.length) return null;
  return (
    <figure className="mh-dumbbell">
      <figcaption>
        <span className="mh-term">Story versus evidence<Info id="storyVsEvidence" /></span>
        <span className="mh-legend">
          <span className="mh-legend-item"><span className="mh-ring" aria-hidden /> What the sentence says</span>
          <span className="mh-legend-item"><span className="mh-dot" aria-hidden /> What the evidence says</span>
        </span>
      </figcaption>
      {rows.map((r) => {
        const lo = Math.min(r.story, r.evidence) * 100;
        const hi = Math.max(r.story, r.evidence) * 100;
        return (
          <div className="mh-db-row" key={r.id}>
            <div className="mh-db-label">{r.label}</div>
            <div className="mh-db-track" role="img" aria-label={`${r.label}: sentence ${Math.round(r.story * 100)}%, evidence ${Math.round(r.evidence * 100)}%`}>
              <div className="mh-db-line" style={{ left: `${lo}%`, width: `${hi - lo}%` }} />
              <div className="mh-db-ring" style={{ left: `${r.story * 100}%` }} />
              <div className="mh-db-dot" style={{ left: `${r.evidence * 100}%` }} />
            </div>
            <div className="mh-db-values">{Math.round(r.story * 100)}% vs {Math.round(r.evidence * 100)}%</div>
          </div>
        );
      })}
      <div className="mh-db-axis" aria-hidden><span>0%</span><span>50%</span><span>100%</span></div>
    </figure>
  );
}

/** A 0 to 1 scale with the three bands and a marker. */
export function ScaleMeter({ si, policy = { watch_above: 0.2, unfair_above: 0.4 } }:
  { si?: number; policy?: { watch_above: number; unfair_above: number } }) {
  return (
    <div className="mh-meter" aria-hidden={si === undefined}>
      <div className="mh-meter-band mh-band-fair" style={{ width: `${policy.watch_above * 100}%` }}><span>Fair</span></div>
      <div className="mh-meter-band mh-band-watch" style={{ width: `${(policy.unfair_above - policy.watch_above) * 100}%` }}><span>Watch</span></div>
      <div className="mh-meter-band mh-band-unfair" style={{ width: `${(1 - policy.unfair_above) * 100}%` }}><span>Unfair</span></div>
      {si !== undefined && <div className="mh-meter-marker" style={{ left: `${si * 100}%` }}><span>{si.toFixed(2)}</span></div>}
    </div>
  );
}
