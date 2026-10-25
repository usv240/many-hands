// A tamper-evident decision log: each entry stores the SHA-256 of the previous entry, so changing
// any past entry breaks every fingerprint after it. Computed in the browser with Web Crypto.

export interface LogEntry {
  seq: number;
  at: string;
  chain_id: string;
  text: string;
  si: number;
  verdict: string;
  action: "approved" | "approved with reason" | "used fair version" | "rejected";
  reason?: string;
  prev: string;
  hash: string;
}

const GENESIS = "0".repeat(64);

async function sha256(s: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

const body = (e: Omit<LogEntry, "hash">) =>
  JSON.stringify([e.seq, e.at, e.chain_id, e.text, e.si, e.verdict, e.action, e.reason ?? "", e.prev]);

export async function append(log: LogEntry[], entry: Omit<LogEntry, "seq" | "at" | "prev" | "hash">): Promise<LogEntry[]> {
  const prev = log.length ? log[log.length - 1].hash : GENESIS;
  const e = { ...entry, seq: log.length + 1, at: new Date().toISOString(), prev };
  return [...log, { ...e, hash: await sha256(body(e)) }];
}

/** Returns the sequence number of the first broken entry, or null if the whole chain is intact. */
export async function verifyLog(log: LogEntry[]): Promise<number | null> {
  let prev = GENESIS;
  for (const e of log) {
    if (e.prev !== prev || (await sha256(body(e))) !== e.hash) return e.seq;
    prev = e.hash;
  }
  return null;
}
