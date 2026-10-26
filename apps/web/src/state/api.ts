import { useEffect, useState } from "react";

// The hosted site serves the API from the same address. When it is not reachable (a static
// preview, a network failure) every page still works on the browser engine and says so.
export interface Health {
  status: string;
  version: string;
  models: { extractor: string; writer: string };
}

export interface TraceStep { agent: string; action: string; ms: number; detail: string; model: boolean }

export interface Variant { id: string; audience: string; text: string; si: number | null; verdict: "fair" | "watch" | "unfair" | "held"; aired: boolean; note?: string | null }

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
  line_ready_s: number | null;
}

export interface Metrics {
  transport: string; goals_processed: number;
  line_p50_s: number | null; line_p95_s: number | null; // goal to the fair line ready for air
  p50_s: number | null; p95_s: number | null;           // goal to all five audience versions ready
}

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
  if (!r.ok) throw await failure(r, "The agents could not run");
  return r.json();
}

export async function kickoff(gameId: number, autoAir = true): Promise<{ status: string; transport: string; decisive_moments: number[] }> {
  const r = await fetch(`/v1/matches/${gameId}/kickoff?auto_air=${autoAir}`, { method: "POST" });
  if (!r.ok) throw await failure(r, "Kick-off failed");
  return r.json();
}

export async function getMetrics(): Promise<Metrics | null> {
  return fetch("/v1/metrics").then((r) => (r.ok ? r.json() : null)).catch(() => null);
}

/** The server's message for a refused request (rate limit, busy), or a plain fallback. */
async function failure(r: Response, fallback: string): Promise<Error> {
  const detail = (await r.json().catch(() => null))?.detail;
  return new Error(typeof detail === "string" ? detail : `${fallback} (${r.status}).`);
}

export interface RecapSentence {
  text: string; chain_id: string | null; si: number | null;
  verdict: "fair" | "watch" | "unfair"; replaced: string | null; reasons: string[];
}
export interface Recap {
  game_id: number; audience: string; title: string; sentences: RecapSentence[];
  model_used: boolean; model: string; replaced: number; seconds: number;
}

export async function recap(gameId: number, audience: string): Promise<Recap> {
  const r = await fetch(`/v1/matches/${gameId}/recap`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ audience }),
    signal: AbortSignal.timeout(60000),
  });
  if (!r.ok) throw await failure(r, "The recap could not be written");
  return r.json();
}

/** A live line the check did not pass as Fair, waiting on the server for a producer. */
export interface QueueItem {
  game_id: number; chain_id: string; line: string; status: "pending" | "approved" | "rejected";
  audit: { si: number; verdict: "fair" | "watch" | "unfair"; reasons?: string[] };
}

export interface LogRecord { chain_id: string; decision: string; by: string; reason: string; at: number; hash: string }

export async function decide(chainId: string, decision: "approve" | "reject", reason: string, producer = "Producer in the Studio"):
  Promise<{ item: QueueItem; record: LogRecord; graphic_sent_to: string | null }> {
  const r = await fetch(`/v1/queue/${encodeURIComponent(chainId)}/decision`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, reason, producer }),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? `The decision was not recorded (${r.status}).`);
  return r.json();
}

export async function getLog(): Promise<{ verify: { ok: boolean; entries: number; broken_at: number | null }; entries: LogRecord[] } | null> {
  return fetch("/v1/log").then((r) => (r.ok ? r.json() : null)).catch(() => null);
}
