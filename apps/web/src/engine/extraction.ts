// Browser port of packages/narrative_core/extraction.py (RuleExtractor). Same rules, same order,
// so the site gives the same answer as the API even when the API is unreachable.
import type { RosterEntry, Shares } from "./types";

const STRENGTH_WORDS: [number, string[]][] = [
  [3, ["howler", "cost them", "cost us", "all on", "entirely", "solely", "to blame", "gifted",
       "handed them", "calamit", "disaster", "lost them", "threw it away", "inexcusable",
       "unforgivable", "liabilit", "blunder"]],
  [2, ["mistake", "error", "fault", "culprit", "guilty", "let them in", "switched off",
       "caught out", "beaten too easily", "sloppy", "careless", "ball-watching",
       "ball watching", "asleep", "should have done better", "nowhere"]],
  [1, ["lost the ball", "gave the ball away", "misplaced", "heavy touch", "too high",
       "out of position", "failed to", "could not", "couldn't", "didn't track",
       "did not track", "slow to", "late to", "left", "allowed", "stepped out"]],
];
const CREDIT_WORDS = ["brilliant", "superb", "assist", "created", "unlocked", "won it", "clever",
  "excellent", "perfect", "great", "wonderful", "scored", "finished"];
const COMMON_WORDS = new Set(`a an the it that this these those he she they we you his her their its
number no what when after then before but and or so if yes not another one two three first second
half minute minutes goal shot pass cross corner penalty var referee keeper striker defence defense
midfield team home away`.split(/\s+/));
const TEAM_WORDS = ["the defence", "the defense", "the back line", "the backline", "the team",
  "the whole team", "everyone", "the midfield", "the back four", "the side"];
const DEFENCE_WORDS = new Set(["the defence", "the defense", "the back line", "the backline", "the back four"]);
const ROLE_MAP: Record<string, string[]> = {
  keeper: ["GK"], goalkeeper: ["GK"], striker: ["ST"],
  "centre back": ["RCB", "LCB"], "center back": ["RCB", "LCB"],
};

export interface Mention {
  player_id: string | null;
  span: string;
  strength: number;
  polarity: "blame" | "credit";
  group: boolean;
  members: string[];
}

export interface Extraction {
  text: string;
  mentions: Mention[];
  unresolved: string[];
}

export function blameOf(x: Extraction): Shares {
  const out: Shares = {};
  for (const m of x.mentions) {
    if (m.polarity !== "blame" || m.strength === 0) continue;
    if (m.group && m.members.length) {
      for (const pid of m.members) out[pid] = (out[pid] ?? 0) + m.strength / m.members.length;
    } else if (m.player_id) {
      out[m.player_id] = (out[m.player_id] ?? 0) + m.strength;
    }
  }
  return out;
}

export class Roster {
  private bySurname = new Map<string, RosterEntry[]>();
  constructor(public entries: RosterEntry[]) {
    for (const e of entries) {
      const parts = e.name.split(/\s+/);
      for (const key of [parts[parts.length - 1].toLowerCase(), ...(e.aliases ?? []).map((a) => a.toLowerCase())]) {
        const list = this.bySurname.get(key) ?? [];
        list.push(e);
        this.bySurname.set(key, list);
      }
    }
  }
  team(teamId: string) { return this.entries.filter((e) => e.team_id === teamId); }
  byShirt(teamId: string, shirt: number) { return this.team(teamId).find((e) => e.shirt === shirt) ?? null; }
  byRole(teamId: string, word: string) {
    const wanted = ROLE_MAP[word] ?? [];
    return this.team(teamId).find((e) => wanted.includes(e.role)) ?? null;
  }
  surname(word: string, teamId?: string) {
    const hits = this.bySurname.get(word.toLowerCase()) ?? [];
    return hits.filter((h) => teamId === undefined || h.team_id === teamId);
  }
}

function strengthOf(text: string): number {
  const low = text.toLowerCase();
  for (const [s, words] of STRENGTH_WORDS) if (words.some((w) => low.includes(w))) return s;
  return 0;
}

export function extract(text: string, roster: Roster, concedingTeamId: string): Extraction {
  const low = text.toLowerCase();
  const strength = strengthOf(text);
  const credit = CREDIT_WORDS.some((w) => low.includes(w));
  const mentions: Mention[] = [];
  const unresolved: string[] = [];
  const seen = new Set<string>();

  const add = (entry: RosterEntry | null, span: string) => {
    if (!entry) { unresolved.push(span); return; }
    if (seen.has(entry.player_id)) return;
    seen.add(entry.player_id);
    const polarity = strength > 0 ? "blame" : credit ? "credit" : "blame";
    mentions.push({ player_id: entry.player_id, span, strength, polarity, group: false, members: [] });
  };

  for (const m of text.matchAll(/(?:number|no\.?|#)\s*(\d{1,2})\b/gi)) {
    add(roster.byShirt(concedingTeamId, Number(m[1])), m[0]);
  }
  for (const m of text.matchAll(/\b(the\s+)?(keeper|goalkeeper|striker|centre back|center back)\b/gi)) {
    add(roster.byRole(concedingTeamId, m[2].toLowerCase()), m[0]);
  }
  for (const m of text.matchAll(/[A-Z][a-z]+(?:-[A-Z][a-z]+)?/g)) {
    const word = m[0];
    const hits = roster.surname(word, concedingTeamId);
    if (hits.length === 1) add(hits[0], word);
    else if (hits.length > 1 || (hits.length === 0 && !COMMON_WORDS.has(word.toLowerCase())
             && roster.surname(word).length === 0)) unresolved.push(word);
  }
  for (const tw of TEAM_WORDS) {
    if (low.includes(tw) && strength > 0) {
      let members = roster.team(concedingTeamId).map((e) => e.player_id);
      if (DEFENCE_WORDS.has(tw)) {
        const defenders = roster.team(concedingTeamId)
          .filter((e) => ["RB", "RCB", "LCB", "LB"].includes(e.role)).map((e) => e.player_id);
        if (defenders.length) members = defenders;
      }
      const idx = low.indexOf(tw);
      mentions.push({ player_id: null, span: text.slice(idx, idx + tw.length), strength,
                      polarity: "blame", group: true, members });
      break;
    }
  }
  return { text, mentions, unresolved };
}
