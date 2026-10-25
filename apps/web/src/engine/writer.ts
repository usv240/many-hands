// Template writer for the offline demo. In production the Narrator and Personalizer agents
// (Microsoft Agent Framework, models on Microsoft Foundry) write these lines; every line, from
// either writer, goes through the same audit before it can air.
import { audit, type AuditResult, fairRewrite, JUSTIFIED_SHARE } from "./audit";
import { Roster } from "./extraction";
import type { Chain, MatchData, Policy } from "./types";

export interface Candidate {
  id: string;
  source: string;
  text: string;
  result: AuditResult;
}

export interface AudienceVersion {
  id: string;
  audience: string;
  description: string;
  text: string;
  language: string;
  result: AuditResult;
  note?: string;
}

const surname = (name: string) => name.split(/\s+/).slice(-1)[0];

export function teamName(data: MatchData, teamId: string) {
  return data.match.home.team_id === teamId ? data.match.home.name : data.match.away.name;
}

function player(data: MatchData, pid: string) {
  return data.roster.find((r) => r.player_id === pid);
}

/** Lines a studio might be about to air for this moment, for the pre-air queue. */
export function candidates(data: MatchData, chain: Chain, policy?: Policy): Candidate[] {
  const roster = new Roster(data.roster);
  const run = (text: string) => audit(text, chain.shares, roster, chain.conceding_team_id, policy, chain.goal);
  const last = chain.last_touch[0] ? player(data, chain.last_touch[0]) : undefined;
  const top = chain.responsibility[0];
  const out: Candidate[] = [];
  if (last) {
    const t = `Number ${last.shirt}'s howler cost them the goal.`;
    out.push({ id: "hot", source: "Pundit script", text: t, result: run(t) });
  }
  const neutral = `${teamName(data, chain.attacking_team_id)} worked it through ${chain.n_actions} actions and finished it off.`;
  out.push({ id: "neutral", source: "AI recap", text: neutral, result: run(neutral) });
  if (top) {
    const t = top.share >= JUSTIFIED_SHARE
      ? `Number ${top.shirt} lost the ball, and that error led directly to the ${chain.goal ? "goal" : "chance"}.`
      : `Number ${top.shirt} lost it, and the defence could not recover.`;
    out.push({ id: "graphic", source: "Lower-third graphic", text: t, result: run(t) });
  }
  return out;
}

/** The same moment, told for different viewers. Every version is audited on its own. */
export function audienceVersions(data: MatchData, chain: Chain, featured?: string, policy?: Policy): AudienceVersion[] {
  const roster = new Roster(data.roster);
  const run = (text: string) => audit(text, chain.shares, roster, chain.conceding_team_id, policy, chain.goal);
  const fair = fairRewrite(chain.shares, roster, chain.goal);
  const contributors = chain.responsibility.filter((c) => c.share >= 0.15);
  const shooter = player(data, chain.shooter_id);
  const unsung = chain.unsung ? player(data, chain.unsung.player_id) : undefined;
  const concedingName = teamName(data, chain.conceding_team_id);
  const attackingName = teamName(data, chain.attacking_team_id);
  const event = chain.goal ? "goal" : "chance";

  const analyst = `${chain.minute}'. ${chain.n_actions} actions. Responsibility: `
    + (contributors.length
      ? contributors.map((c) => `#${c.shirt} ${Math.round(c.share * 100)}% (${c.reason.split(",")[0]})`).join("; ")
      : "no defending loss of value")
    + (unsung ? `. Unsung: ${unsung.name}.` : ".");

  const single = contributors.length === 1 && contributors[0].share >= JUSTIFIED_SHARE;
  const casual = single
    ? `Tough moment for ${concedingName}: one loose ball gave ${attackingName} the ${event}, and they took it.`
    : `Tough one for ${concedingName}: a couple of loose balls in a row gave ${attackingName} a way in.`;

  const celebrate = `What a move from ${attackingName}`
    + (unsung && shooter && unsung.player_id !== shooter.player_id
      ? `: ${surname(unsung.name)} set it up and ${surname(shooter.name)} finished it.`
      : shooter ? `, finished by ${surname(shooter.name)}.` : ".");

  const focusId = featured ?? chain.responsibility[0]?.player_id;
  const focus = focusId ? player(data, focusId) : undefined;
  const focusShare = focusId ? chain.shares[focusId] ?? 0 : 0;
  const focusLine = focus
    ? focusShare >= JUSTIFIED_SHARE
      ? `Following number ${focus.shirt}: a ball lost here led to the ${event}. One moment in a full match.`
      : focusShare > 0
        ? `Following number ${focus.shirt}: part of a move where several things went wrong, not the whole story.`
        : `Following number ${focus.shirt}: not involved in the build-up to this ${event}.`
    : `No featured player selected.`;

  const spanishSource = fair;
  const spanish = single
    ? `Una pérdida del número ${contributors[0].shirt} llevó directamente al ${chain.goal ? "gol" : "remate"}.`
    : `Varios errores, de ${contributors.map((c) => `el número ${c.shirt}`).join(" y ")}, abrieron el camino al ${chain.goal ? "gol" : "remate"}.`;

  return [
    { id: "analyst", audience: "Analyst", description: "Numbers first, every contributor", text: analyst, language: "English", result: run(analyst) },
    { id: "casual", audience: `Casual fan of ${concedingName}`, description: "Plain words, no blame game", text: casual, language: "English", result: run(casual) },
    { id: "club", audience: `Fan of ${attackingName}`, description: "Credit for the move", text: celebrate, language: "English", result: run(celebrate) },
    { id: "focus", audience: focus ? `Following number ${focus.shirt}` : "Player focus", description: "One player, in context", text: focusLine, language: "English", result: run(focusLine) },
    { id: "es", audience: "Spanish speaker", description: "Same facts, another language", text: spanish, language: "Spanish", result: run(spanishSource),
      note: "Checked on the English source before translation. In production, Azure AI Translator translates the approved line." },
  ];
}
