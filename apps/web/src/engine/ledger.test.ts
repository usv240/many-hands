// The browser ledger must rebuild the same moments and responsibility as the Python ledger
// from the Bring Your Own sample file.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, it } from "vitest";
import { buildMatch, parseCsv } from "./ledger";
import type { MatchData } from "./types";

const pub = (f: string) => readFileSync(resolve(__dirname, `../../public/data/${f}`), "utf8");

it("parses the sample and finds the same moments with the same shares", () => {
  const { actions, meta, report } = parseCsv(pub("sample-match.csv"));
  expect(report.ok).toBe(true);
  const built = buildMatch(actions, meta);
  const py: MatchData = JSON.parse(pub("match-20045.json"));
  expect(built.chains.length).toBe(py.chains.length);
  expect(built.match.score).toEqual(py.match.score);
  for (const c of py.chains) {
    const shotId = Number(c.chain_id.split("-")[1]);
    const mine = built.chains.find((x) => x.chain_id === `upload-${shotId}`)!;
    expect(mine, c.chain_id).toBeTruthy();
    expect(Object.keys(mine.shares).sort()).toEqual(Object.keys(c.shares).sort());
    for (const [p, s] of Object.entries(c.shares)) expect(mine.shares[p]).toBeCloseTo(s, 2);
  }
});

it("reports missing columns instead of guessing", () => {
  const r = parseCsv("team_id,player_id\nA,a1\n");
  expect(r.report.ok).toBe(false);
  expect(r.report.missing).toContain("vaep_value");
});
