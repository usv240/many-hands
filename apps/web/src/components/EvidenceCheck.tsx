import { Button } from "@fluentui/react-components";
import { CheckmarkCircle20Regular, Eye20Regular, Question20Regular } from "@fluentui/react-icons";
import type { Action, Chain, MatchData } from "../engine/types";
import { Info } from "./Info";

export type EvidenceStatus = "pending" | "confirmed" | "rejected" | "unclear";

/** The single action the verdict leans on most: the biggest lost ball by the most responsible player. */
export function decidingAction(chain: Chain): Action | null {
  const top = chain.responsibility[0]?.player_id;
  if (!top) return null;
  const losses = chain.actions
    .filter((a) => a.player_id === top && a.team_id === chain.conceding_team_id && a.result_name !== "success")
    .sort((a, b) => a.vaep_value - b.vaep_value);
  return losses[0] ?? null;
}

/**
 * The agent directs the producer: it chooses what to look at, plays it, and asks one question.
 * Nothing involving this player airs until the question is answered.
 */
export function EvidenceCheck({ chain, data, status, onAnswer }:
  { chain: Chain; data: MatchData; status: EvidenceStatus;
    onAnswer: (s: Exclude<EvidenceStatus, "pending">, action: Action) => void }) {
  const action = decidingAction(chain);
  if (!action) return null;
  const p = data.roster.find((r) => r.player_id === action.player_id);
  const who = p ? `number ${p.shirt}, ${p.name}` : action.player_id;
  const index = chain.actions.findIndex((a) => a.action_id === action.action_id) + 1;
  const kind = action.type_name === "dribble" ? "carry" : action.type_name.replace("_", " ");
  const minute = Math.floor(action.time_seconds / 60) + (action.period_id === 2 ? 45 : 0);

  return (
    <div className={`mh-evidence-check is-${status}`} role="region" aria-label="Evidence check">
      <p className="mh-term"><strong>Evidence check</strong><Info id="evidenceCheck" /></p>
      {status === "pending" && (
        <>
          <p>
            <Eye20Regular aria-hidden /> Before anything about this goal airs, look at action {index} on the pitch
            ({minute}'). The verdict depends on it most.
          </p>
          <p className="mh-question">Does the replay show {who} losing the ball with that {kind}?</p>
          <p className="mh-small mh-muted">Yes keeps the scores. No treats it as a data error: that action is removed and the blame is worked out again.
            Can't tell means any line blaming this player needs a written reason to air.</p>
          <div className="mh-row mh-wrap">
            <Button appearance="primary" icon={<CheckmarkCircle20Regular />} onClick={() => onAnswer("confirmed", action)}>Yes, it does</Button>
            <Button onClick={() => onAnswer("rejected", action)}>No, the data is wrong</Button>
            <Button appearance="subtle" icon={<Question20Regular />} onClick={() => onAnswer("unclear", action)}>Can't tell</Button>
          </div>
        </>
      )}
      {status === "confirmed" && <p className="mh-ok">Confirmed by the producer. The verdicts below stand.</p>}
      {status === "rejected" && <p>Action {index} was removed as a data error, and responsibility was recalculated without it. Every score below uses the corrected evidence.</p>}
      {status === "unclear" && <p>Unconfirmed. Any line that blames {who} now needs a typed reason before it can air.</p>}
    </div>
  );
}
