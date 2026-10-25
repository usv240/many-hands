// Browser port of packages/ledger_core (chains.find_moments and responsibility.onball_blame),
// so a visitor can bring their own rated match file and see it in the Studio with no server.
import { normalize } from "./scapegoat";
import type { Action, Chain, Contributor, MatchData, RosterEntry, Shares } from "./types";

const SHOT_TYPES = new Set(["shot", "shot_penalty", "shot_freekick"]);
const CONTROL_TYPES = new Set(["pass", "cross", "dribble", "take_on", "clearance", "throw_in", "goalkick",
  "freekick_short", "freekick_crossed", "corner_short", "corner_crossed"]);
const MIN_FRACTION = 0.2;
const MIN_ABS = 0.002;
const LAST_TURNOVER_BOOST = 2.0;
const MAX_WINDOW = 25;

export type RatedAction = Action & { scores?: number };

export function onballBlame(chain: RatedAction[], defending: string): Shares {
  const d = chain.filter((a) => a.team_id === defending && a.player_id);
  let loss = d.map((a) => Math.max(0, -a.vaep_value));
  const failed = d.map((a) => a.result_name !== "success");
  if (failed.some(Boolean)) {
    loss = loss.map((v, i) => (failed[i] ? v : 0));
    const last = failed.lastIndexOf(true);
    loss[last] *= LAST_TURNOVER_BOOST;
  }
  const max = Math.max(0, ...loss);
  if (!d.length || max <= 0) return {};
  const w: Shares = {};
  d.forEach((a, i) => {
    if (loss[i] >= MIN_FRACTION * max && loss[i] >= MIN_ABS) w[a.player_id] = (w[a.player_id] ?? 0) + loss[i];
  });
  return normalize(w);
}

function lastTouch(chain: RatedAction[], defending: string): string[] {
  const seen: string[] = [];
  for (const a of [...chain].reverse()) if (a.team_id === defending && a.player_id && !seen.includes(a.player_id)) seen.push(a.player_id);
  return seen;
}

export function findChains(actions: RatedAction[], minXg = 0.07): { shot: number; start: number; attacking: string; conceding: string; goal: boolean }[] {
  const a = [...actions].sort((x, y) => x.period_id - y.period_id || x.action_id - y.action_id);
  const teams = [...new Set(a.map((x) => x.team_id))];
  const out = [];
  for (let i = 0; i < a.length; i++) {
    const row = a[i];
    if (!SHOT_TYPES.has(row.type_name)) continue;
    const goal = row.result_name === "success";
    if (!goal && (row.scores ?? 0) < minXg) continue;
    const conceding = teams.find((t) => t !== row.team_id) ?? "";
    let start = i;
    for (let j = i - 1; j > Math.max(i - MAX_WINDOW, -1); j--) {
      const prev = a[j];
      if (prev.period_id !== row.period_id) break;
      start = j;
      if (prev.team_id === conceding && CONTROL_TYPES.has(prev.type_name) && prev.result_name === "success") break;
    }
    out.push({ shot: i, start, attacking: row.team_id, conceding, goal });
  }
  return out;
}

export interface UploadMeta { homeTeamId?: string; teamNames?: Record<string, string>; roster?: RosterEntry[] }

/** Build a full MatchData (chains, responsibility, unsung) from rated actions. */
export function buildMatch(actions: RatedAction[], meta: UploadMeta = {}): Omit<MatchData, "match"> & { match: Omit<MatchData["match"], "game_id"> } {
  const a = [...actions].sort((x, y) => x.period_id - y.period_id || x.action_id - y.action_id);
  const teams = [...new Set(a.map((x) => x.team_id))];
  const home = meta.homeTeamId && teams.includes(meta.homeTeamId) ? meta.homeTeamId : teams[0];
  const away = teams.find((t) => t !== home) ?? "away";
  const roster: RosterEntry[] = meta.roster?.length ? meta.roster : [...new Map(a.map((x) => [x.player_id, x])).values()]
    .map((x, i) => ({ player_id: x.player_id, name: x.player_id, shirt: i + 1, team_id: x.team_id, role: "" }));
  const who = (pid: string) => roster.find((r) => r.player_id === pid);
  const goals = (t: string) => a.filter((x) => SHOT_TYPES.has(x.type_name) && x.result_name === "success" && x.team_id === t).length;

  const chains: Chain[] = findChains(a).map((m) => {
    const chain = a.slice(m.start, m.shot + 1);
    const shares = onballBlame(chain, m.conceding);
    const reason = (pid: string) => {
      const mine = chain.filter((x) => x.player_id === pid && x.team_id === m.conceding && x.vaep_value < 0)
        .sort((x, y) => x.vaep_value - y.vaep_value)[0];
      if (!mine) return "involved in the build-up";
      const ownHalf = m.conceding === home ? mine.start_x < 52.5 : mine.start_x >= 52.5;
      const kind = mine.type_name === "dribble" ? "carry" : mine.type_name.replace("_", " ");
      const mm = Math.floor(mine.time_seconds / 60), ss = Math.floor(mine.time_seconds % 60);
      return `${kind} that ${mine.result_name !== "success" ? "lost the ball" : "played it backwards under pressure"} ${ownHalf ? "in own half" : "upfield"}, ${mm}:${String(ss).padStart(2, "0")}`;
    };
    const contributor = (pid: string, share: number): Contributor =>
      ({ player_id: pid, name: who(pid)?.name ?? pid, shirt: who(pid)?.shirt ?? null, share, reason: reason(pid) });
    const shot = chain[chain.length - 1];
    const credit: Shares = {};
    for (const x of chain) if (x.team_id === m.attacking && x.player_id !== shot.player_id && x.vaep_value > 0) credit[x.player_id] = (credit[x.player_id] ?? 0) + x.vaep_value;
    const cn = normalize(credit);
    const top = Object.entries(cn).sort((p, q) => q[1] - p[1])[0];
    return {
      chain_id: `upload-${shot.action_id}`, game_id: 0, goal: m.goal, attacking_team_id: m.attacking,
      conceding_team_id: m.conceding, shooter_id: shot.player_id, clock_s: shot.time_seconds, period: shot.period_id,
      minute: Math.floor(shot.time_seconds / 60) + (shot.period_id === 2 ? 45 : 0), n_actions: chain.length,
      responsibility: Object.entries(shares).sort((p, q) => q[1] - p[1]).map(([p, s]) => contributor(p, s)),
      last_touch: lastTouch(chain.slice(0, -1), m.conceding).slice(0, 1),
      unsung: top ? { player_id: top[0], name: who(top[0])?.name ?? top[0], shirt: who(top[0])?.shirt ?? null, share: top[1], reason: "action that raised the danger most" } : null,
      actions: chain, shares,
    };
  });
  return {
    match: {
      home: { team_id: home, name: meta.teamNames?.[home] ?? home }, away: { team_id: away, name: meta.teamNames?.[away] ?? away },
      score: [goals(home), goals(away)], decisive_moments: chains.length, goals: chains.filter((c) => c.goal).length,
    },
    roster, chains,
  };
}

const REQUIRED = ["period_id", "time_seconds", "team_id", "player_id", "type_name", "result_name",
  "start_x", "start_y", "end_x", "end_y", "vaep_value"];

export interface ParseReport { ok: boolean; rows: number; missing: string[]; message: string }

/** Parse a rated SPADL CSV (one action per row). Extra columns player_name, shirt, role, team_name are used for the roster. */
export function parseCsv(text: string): { actions: RatedAction[]; meta: UploadMeta; report: ParseReport } {
  const lines = text.replace(/\r/g, "").split("\n").filter((l) => l.trim());
  const split = (l: string) => {
    const out: string[] = []; let cur = ""; let q = false;
    for (const ch of l) {
      if (ch === '"') q = !q; else if (ch === "," && !q) { out.push(cur); cur = ""; } else cur += ch;
    }
    out.push(cur); return out;
  };
  const head = split(lines[0] ?? "").map((h) => h.trim());
  const missing = REQUIRED.filter((c) => !head.includes(c));
  if (missing.length) return { actions: [], meta: {}, report: { ok: false, rows: 0, missing, message: `Missing columns: ${missing.join(", ")}.` } };
  const idx = (c: string) => head.indexOf(c);
  const num = (v: string) => Number(v);
  const rosterMap = new Map<string, RosterEntry>();
  const names: Record<string, string> = {};
  const actions: RatedAction[] = lines.slice(1).map((l, i) => {
    const c = split(l);
    const get = (k: string) => (idx(k) >= 0 ? c[idx(k)] : undefined);
    const pid = get("player_id") ?? "";
    const team = get("team_id") ?? "";
    if (get("player_name") && !rosterMap.has(pid)) {
      rosterMap.set(pid, { player_id: pid, name: get("player_name")!, shirt: Number(get("shirt") ?? 0), team_id: team, role: get("role") ?? "" });
    }
    if (get("team_name")) names[team] = get("team_name")!;
    return {
      action_id: idx("action_id") >= 0 ? num(get("action_id")!) : i, period_id: num(get("period_id")!),
      time_seconds: num(get("time_seconds")!), team_id: team, player_id: pid,
      type_name: get("type_name")!, result_name: get("result_name")!,
      start_x: num(get("start_x")!), start_y: num(get("start_y")!), end_x: num(get("end_x")!), end_y: num(get("end_y")!),
      vaep_value: num(get("vaep_value")!), offensive_value: num(get("offensive_value") ?? "0"),
      defensive_value: num(get("defensive_value") ?? "0"), scores: get("scores") ? num(get("scores")!) : undefined,
    };
  });
  const bad = actions.filter((x) => Number.isNaN(x.vaep_value) || Number.isNaN(x.start_x)).length;
  return {
    actions, meta: { roster: [...rosterMap.values()], teamNames: names, homeTeamId: lines.length > 1 ? undefined : undefined },
    report: { ok: bad === 0 && actions.length > 0, rows: actions.length, missing: [],
              message: bad ? `${bad} rows have unreadable numbers.` : `Read ${actions.length} actions.` },
  };
}
