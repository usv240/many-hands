import { useEffect, useState } from "react";
import type { MatchData, MatchInfo } from "../engine/types";

// The site ships with its own copy of the demo data (exported by scripts/export_web_data.py),
// so every page works with no server at all. An API can be layered on later via VITE_API_BASE.
const cache = new Map<string, Promise<unknown>>();

function getJson<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    cache.set(path, fetch(path).then((r) => {
      if (!r.ok) throw new Error(`Could not load ${path} (${r.status})`);
      return r.json();
    }));
  }
  return cache.get(path) as Promise<T>;
}

export const loadMatches = () => getJson<MatchInfo[]>("/data/matches.json");
export const loadMatch = (id: number) => getJson<MatchData>(`/data/match-${id}.json`);
export const loadResults = () => getJson<Results>("/data/results.json");

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): { data?: T; error?: string } {
  const [state, setState] = useState<{ data?: T; error?: string }>({});
  useEffect(() => {
    let live = true;
    fn().then((data) => live && setState({ data })).catch((e) => live && setState({ error: String(e.message ?? e) }));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export interface Metric { mean: number; ci95_low: number; ci95_high: number }

export interface Results {
  external: {
    cases: number; matches: number; goals: number; excluded: Record<string, number>;
    metrics: Record<string, Metric>; verdicts_if_blamed_alone: Record<string, number>;
    justified_cases: number; justified_false_unfair: number; labelled_share_median: number; note: string;
  };
  synthetic: {
    bench_games: number; train_games: number; moments: number; goals: number; justified_cases: number;
    metrics: Record<string, Metric>;
    multi_cause: { n: number; metrics: Record<string, number> };
    last_touch_story_unfair_share: number;
  };
  calibration: { statistic: string; real: number; simulated: number; difference_pct: number }[];
  redteam: {
    attacks: number;
    held_out: RedTeamSplit;
    all: RedTeamSplit;
    controls: { lines: number; unfair_rules: number; unfair_with_reader: number };
    caveat: string;
  };
  foundry_eval: {
    status: string; portal_url: string; items: number;
    groups: Record<string, Record<string, number>>;
  };
  operations: {
    moments: number; matches: number; all_ready: number; model: string;
    line_ready_s: { p50: number; p95: number }; all_versions_s: { p50: number; p95: number };
    model_calls_per_goal: number; tokens_per_goal: number; cost_per_goal_usd: number;
    cost_per_match_usd: number; cost_per_season_usd: number; decisive_moments_per_match: number; note: string;
  };
}

export interface RedTeamSplit {
  judge_unfair: number; caught_rules: number; caught_with_reader: number;
  hard_negatives: number; hard_negatives_unfair_rules: number; hard_negatives_unfair_with_reader: number;
}

/** The demo moment used on the landing page: a goal where blame is genuinely shared. */
export const SHOWCASE = { gameId: 20003, chainId: "20003-300" };
