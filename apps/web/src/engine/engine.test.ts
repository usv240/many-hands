// Parity: the browser engine must give the same answers as the Python engine, case for case.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { audit } from "./audit";
import { Roster } from "./extraction";
import { scapegoatIndex, verdict } from "./scapegoat";
import type { MatchData } from "./types";
import parity from "./__fixtures__/parity.json";

const load = (gid: number): MatchData =>
  JSON.parse(readFileSync(resolve(__dirname, `../../public/data/match-${gid}.json`), "utf8"));

describe("Scapegoat Index", () => {
  it("is 0 for a sentence that blames no one and 1 for blame without evidence", () => {
    expect(scapegoatIndex({}, { a: 1 })).toBe(0);
    expect(scapegoatIndex({ a: 1 }, {})).toBe(1);
  });
  it("gives sole blame 1 minus that player's share", () => {
    expect(scapegoatIndex({ p5: 1 }, { p5: 0.19, p8: 0.81 })).toBeCloseTo(0.81);
  });
  it("uses the policy bands", () => {
    expect(verdict(0.2)).toBe("fair");
    expect(verdict(0.21)).toBe("watch");
    expect(verdict(0.41)).toBe("unfair");
  });
  it("sends blame with no counted mistake to a person instead of calling it unfair", () => {
    const data = load(20003);
    const team = data.chains[0].conceding_team_id;
    const shirt = data.roster.find((p) => p.team_id === team)!.shirt;
    const r = audit(`Number ${shirt}'s howler cost them the goal.`, {}, new Roster(data.roster), team);
    expect(r.verdict).toBe("watch");
    expect(r.reasons[0]).toContain("neither support nor rule out");
  });
});

describe("parity with the Python engine", () => {
  const cache = new Map<number, MatchData>();
  for (const c of parity as Array<{ chain_id: string; game_id: number; text: string; si: number;
    verdict: string; unresolved: string[] }>) {
    it(`${c.chain_id}: ${c.text}`, () => {
      if (!cache.has(c.game_id)) cache.set(c.game_id, load(c.game_id));
      const data = cache.get(c.game_id)!;
      const chain = data.chains.find((x) => x.chain_id === c.chain_id)!;
      const r = audit(c.text, chain.shares, new Roster(data.roster), chain.conceding_team_id,
                      undefined, chain.goal);
      expect(r.si).toBeCloseTo(c.si, 3);
      expect(r.verdict).toBe(c.verdict);
      expect(r.unresolved).toEqual(c.unresolved);
    });
  }
});
