// Matches the visitor brought themselves. Kept in memory only: nothing is uploaded anywhere,
// and closing the tab deletes them.
import type { MatchData } from "../engine/types";

const store = new Map<number, MatchData>();
let nextId = -1;

export function addUploaded(data: Omit<MatchData, "match"> & { match: Omit<MatchData["match"], "game_id"> }): number {
  const id = nextId--;
  const full: MatchData = {
    ...data,
    match: { ...data.match, game_id: id },
    chains: data.chains.map((c) => ({ ...c, game_id: id })),
  };
  store.set(id, full);
  return id;
}

export const getUploaded = (id: number) => store.get(id);
