// Browser port of packages/narrative_core/scapegoat.py. Parity is checked by engine.test.ts.
import { DEFAULT_POLICY, type Policy, type Shares, type Verdict } from "./types";

export function normalize(weights: Shares): Shares {
  const clipped: Shares = {};
  let total = 0;
  for (const [k, v] of Object.entries(weights)) {
    const c = Math.max(0, v);
    clipped[k] = c;
    total += c;
  }
  if (total === 0) return {};
  const out: Shares = {};
  for (const [k, v] of Object.entries(clipped)) if (v > 0) out[k] = v / total;
  return out;
}

/** Whole percentages that always add up to 100 (largest remainder); the same rule as percents() in Python. */
export function percents(weights: Shares): Record<string, number> {
  const r = normalize(weights);
  const raw = Object.entries(r).map(([k, v]) => [k, 100 * v] as const);
  const out: Record<string, number> = Object.fromEntries(raw.map(([k, v]) => [k, Math.floor(v)]));
  let short = raw.length ? 100 - Object.values(out).reduce((a, b) => a + b, 0) : 0;
  const order = [...raw].sort(([ka, a], [kb, b]) =>
    (b - Math.floor(b)) - (a - Math.floor(a)) || b - a || (ka < kb ? -1 : ka > kb ? 1 : 0));
  for (const [k] of order) { if (short-- <= 0) break; out[k] += 1; }
  return out;
}

/** Total variation distance between the blame in a sentence and the blame in the evidence. */
export function scapegoatIndex(blame: Shares, evidence: Shares): number {
  const b = normalize(blame);
  if (Object.keys(b).length === 0) return 0;
  const r = normalize(evidence);
  if (Object.keys(r).length === 0) return 1;
  const keys = new Set([...Object.keys(b), ...Object.keys(r)]);
  let sum = 0;
  for (const k of keys) sum += Math.abs((b[k] ?? 0) - (r[k] ?? 0));
  return 0.5 * sum;
}

export function blameInflation(blame: Shares, evidence: Shares, floor = 0.01): Shares {
  const b = normalize(blame);
  const r = normalize(evidence);
  const out: Shares = {};
  for (const [k, v] of Object.entries(b)) out[k] = v / Math.max(r[k] ?? 0, floor);
  return out;
}

export function verdict(si: number, policy: Policy = DEFAULT_POLICY): Verdict {
  if (si > policy.unfair_above) return "unfair";
  if (si > policy.watch_above) return "watch";
  return "fair";
}
