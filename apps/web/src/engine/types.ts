export type Shares = Record<string, number>;

export interface RosterEntry {
  player_id: string;
  name: string;
  shirt: number;
  team_id: string;
  role: string;
  aliases?: string[];
}

export interface Action {
  action_id: number;
  period_id: number;
  time_seconds: number;
  team_id: string;
  player_id: string;
  type_name: string;
  result_name: string;
  start_x: number;
  start_y: number;
  end_x: number;
  end_y: number;
  vaep_value: number;
  offensive_value: number;
  defensive_value: number;
}

export interface Contributor {
  player_id: string;
  name: string;
  shirt: number | null;
  share: number;
  reason: string;
}

export interface Chain {
  chain_id: string;
  game_id: number;
  goal: boolean;
  attacking_team_id: string;
  conceding_team_id: string;
  shooter_id: string;
  clock_s: number;
  period: number;
  minute: number;
  n_actions: number;
  responsibility: Contributor[];
  last_touch: string[];
  unsung: Contributor | null;
  actions: Action[];
  shares: Shares;
}

export interface TeamRef {
  team_id: string;
  name: string;
}

export interface MatchInfo {
  game_id: number;
  home: TeamRef;
  away: TeamRef;
  score: [number, number];
  decisive_moments: number;
  goals: number;
}

export interface MatchData {
  match: MatchInfo;
  roster: RosterEntry[];
  chains: Chain[];
}

export type Verdict = "fair" | "watch" | "unfair";

export interface Policy {
  watch_above: number;
  unfair_above: number;
}

export const DEFAULT_POLICY: Policy = { watch_above: 0.2, unfair_above: 0.4 };
