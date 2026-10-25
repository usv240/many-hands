import { useEffect, useState } from "react";

// The hosted site serves the API from the same address. When it is not reachable (a static
// preview, a network failure) every page still works on the browser engine and says so.
export interface Health {
  status: string;
  version: string;
  models: { extractor: string; writer: string };
}

export interface TraceStep { agent: string; action: string; ms: number; detail: string; model: boolean }

export interface Variant { id: string; audience: string; text: string; si: number; verdict: "fair" | "watch" | "unfair"; aired: boolean; note?: string | null }

export interface AgentResult {
  status: "ready" | "held";
  line: string | null;
  audit: { si: number; verdict: "fair" | "watch" | "unfair"; reasons: string[]; contrastive: string } | null;
  source: string | null;
  revisions: number;
  history: { text: string; source: string; si: number; verdict: "fair" | "watch" | "unfair"; fact_errors?: string[] }[];
  variants: Variant[];
  trace: TraceStep[];
  model: string;
  model_used: boolean;
  held_reason: string | null;
}

export interface Metrics { transport: string; goals_processed: number; p50_s: number | null; p95_s: number | null }

export const LIVE_URL = "https://ca-manyhands-7kzrrno7qr6zo.orangedune-9d42108b.eastus2.azurecontainerapps.io";

let healthPromise: Promise<Health | null> | null = null;

export function getHealth(): Promise<Health | null> {
  healthPromise ??= fetch("/v1/health", { signal: AbortSignal.timeout(4000) })
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);
  return healthPromise;
}

export function useHealth(): { health: Health | null; checked: boolean } {
  const [state, setState] = useState<{ health: Health | null; checked: boolean }>({ health: null, checked: false });
  useEffect(() => { getHealth().then((health) => setState({ health, checked: true })); }, []);
  return state;
}

export const liveAi = (h: Health | null) => !!h && h.models.writer !== "template";

export async function broadcast(body: { chain_id: string; text?: string; featured?: string; simulate_auditor_outage?: boolean }): Promise<AgentResult> {
  const r = await fetch("/v1/broadcast", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    signal: AbortSignal.timeout(45000),
  });
  if (!r.ok) throw new Error(`The agents could not run (${r.status}).`);
  return r.json();
}

export async function kickoff(gameId: number): Promise<{ status: string; transport: string; decisive_moments: number[] }> {
  const r = await fetch(`/v1/matches/${gameId}/kickoff`, { method: "POST" });
  if (!r.ok) throw new Error(`Kick-off failed (${r.status}).`);
  return r.json();
}

export async function getMetrics(): Promise<Metrics | null> {
  return fetch("/v1/metrics").then((r) => (r.ok ? r.json() : null)).catch(() => null);
}
