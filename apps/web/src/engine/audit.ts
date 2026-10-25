// Browser port of packages/narrative_core/audit.py.
import { blameOf, extract, type Mention, Roster } from "./extraction";
import { blameInflation, normalize, scapegoatIndex, verdict } from "./scapegoat";
import { DEFAULT_POLICY, type Policy, type Shares, type Verdict } from "./types";

export const JUSTIFIED_SHARE = 0.6;

export interface AuditResult {
  text: string;
  si: number;
  verdict: Verdict;
  blame: Shares;
  evidence: Shares;
  inflation: Shares;
  mentions: Mention[];
  unresolved: string[];
  reasons: string[];
  contrastive: string;
  fairRewrite: string | null;
  justified: boolean;
}

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
const pct = (x: number) => `${Math.round(x * 100)}%`;

export function label(roster: Roster | null, pid: string): string {
  const e = roster?.entries.find((x) => x.player_id === pid);
  return e ? `number ${e.shirt}` : pid;
}

const sorted = (r: Shares) => Object.entries(r).sort((a, b) => b[1] - a[1]);

export function contrastive(evidence: Shares, blamed: string | null, roster: Roster | null): string {
  const r = normalize(evidence);
  const order = sorted(r);
  if (!order.length) return "The evidence does not point to any defending mistake behind this moment.";
  const [top, topS] = order[0];
  if (blamed && blamed in r && blamed !== top) {
    return `${capitalize(label(roster, blamed))} carried ${pct(r[blamed])} of the danger; `
      + `${label(roster, top)} carried ${pct(topS)}, the largest share.`;
  }
  if (blamed && !(blamed in r)) {
    return `The evidence gives ${label(roster, blamed)} no share of this moment; `
      + `${label(roster, top)} carried the largest share at ${pct(topS)}.`;
  }
  if (order.length === 1) return `${capitalize(label(roster, top))} carried all of the measurable danger.`;
  const [second, secondS] = order[1];
  return `${capitalize(label(roster, top))} carried ${pct(topS)} of the danger, ${label(roster, second)} ${pct(secondS)}.`;
}

export function fairRewrite(evidence: Shares, roster: Roster | null, goal = true): string {
  const r = sorted(normalize(evidence));
  const outcome = goal ? "the goal" : "the chance";
  if (!r.length) return `A well-worked move created ${outcome}; no single defensive mistake stands out.`;
  if (r[0][1] >= JUSTIFIED_SHARE) {
    return `${capitalize(label(roster, r[0][0]))} lost the ball, and that error led directly to ${outcome}.`;
  }
  const names = r.slice(0, 3).filter(([, s]) => s >= 0.15).map(([p]) => label(roster, p));
  if (names.length === 1) return `A loss of the ball by ${names[0]} led to ${outcome}, with the defence unable to recover.`;
  const joined = `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
  return `Mistakes by ${joined} combined to let the attack through for ${outcome}.`;
}

export function audit(text: string, evidence: Shares, roster: Roster, concedingTeamId: string,
                      policy: Policy = DEFAULT_POLICY, goal = true): AuditResult {
  const x = extract(text, roster, concedingTeamId);
  const blame = blameOf(x);
  const si = scapegoatIndex(blame, evidence);
  const v = verdict(si, policy);
  const r = normalize(evidence);
  const top = sorted(r)[0]?.[0] ?? null;
  const nb = Object.keys(normalize(blame));
  const justified = Boolean(top && r[top] >= JUSTIFIED_SHARE && nb.length === 1 && nb[0] === top);
  const blamed = sorted(blame)[0]?.[0] ?? null;
  const reasons: string[] = [];
  if (!Object.keys(blame).length) reasons.push("The line blames no one, so it scores 0.");
  else if (v === "fair") reasons.push("The blame in the line matches the evidence.");
  else {
    const infl = blameInflation(blame, evidence);
    const worst = sorted(infl)[0][0];
    reasons.push(`${capitalize(label(roster, worst))} gets ${infl[worst].toFixed(1)} times the blame the evidence supports.`);
    const missing = Object.entries(r).filter(([p, s]) => s >= 0.15 && !(p in blame));
    if (missing.length) {
      reasons.push("Not mentioned despite a real share: "
        + missing.map(([p, s]) => `${label(roster, p)} (${pct(s)})`).join(", ") + ".");
    }
  }
  if (x.unresolved.length) reasons.push(`Could not tell who is meant by: ${x.unresolved.join(", ")}.`);
  return {
    text, si: Math.round(si * 1000) / 1000, verdict: v, blame: normalize(blame), evidence: r,
    inflation: blameInflation(blame, evidence), mentions: x.mentions, unresolved: x.unresolved,
    reasons, contrastive: contrastive(evidence, blamed, roster),
    fairRewrite: v === "fair" ? null : fairRewrite(evidence, roster, goal), justified,
  };
}
