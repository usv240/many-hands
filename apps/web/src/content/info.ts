// Every "i" text on the site lives here, so wording stays consistent and can be reviewed in one
// place. Each entry: a title, what it is, why it matters, and optionally a deeper version for the
// "In depth" and "Technically" reading levels, plus a link to learn more.

export interface InfoEntry {
  title: string;
  what: string;
  why: string;
  deep?: string;
  tech?: string;
  more?: { label: string; to: string };
}

export const INFO = {
  si: {
    title: "Scapegoat Index",
    what: "A score from 0 to 1 comparing who a sentence blames with who the evidence says contributed.",
    why: "It catches stories that pin a team's mistake on one player.",
    deep: "Below 0.20 is Fair, 0.20 to 0.40 is Watch, above 0.40 is Unfair. Broadcasters can set their own limits.",
    tech: "Total variation distance between the sentence's blame distribution and the ledger's responsibility distribution. A sentence with no blame scores 0.",
    more: { label: "How the score works", to: "/how-it-works#score" },
  },
  verdict: {
    title: "Fair, Watch, Unfair",
    what: "Three bands of the Scapegoat Index: below 0.20, 0.20 to 0.40, above 0.40.",
    why: "It turns a number into a decision a producer can act on in seconds.",
  },
  responsibility: {
    title: "Responsibility",
    what: "Each player's share of what led to this moment. The shares add up to 100 percent.",
    why: "It shows the whole team's part, not just the last touch.",
    tech: "Material losses of action value (VAEP) by the conceding team in the chain, counting only actions that lost the ball, with the final turnover weighted double. Settings chosen on the synthetic ground truth.",
    more: { label: "The method", to: "/how-it-works#explain" },
  },
  chain: {
    title: "Chain of actions",
    what: "The passes, runs, tackles and shots that led to this moment, in order.",
    why: "Goals are built from many actions, not one.",
    tech: "From the conceding team's last controlled action up to the shot, capped at 25 actions and never crossing half time.",
  },
  unsung: {
    title: "Unsung",
    what: "The attacking player who did most to create this moment without taking the shot.",
    why: "Fair means credit as well as blame.",
  },
  evidence: {
    title: "Evidence",
    what: "The facts behind a score: each action, its value, and who made it.",
    why: "You can check our reasoning instead of having to trust it.",
  },
  storyVsEvidence: {
    title: "Story versus evidence",
    what: "Each row is a player. The ring is how much the sentence blames them; the dot is how much the evidence does.",
    why: "Big gaps between ring and dot are where unfair blame hides.",
  },
  contrastive: {
    title: "Why this player, not that one",
    what: "A one-line comparison between the player the sentence blames and the player the evidence points to.",
    why: "People understand causes best by comparison (Miller, 2019).",
  },
  fairRewrite: {
    title: "Fair version",
    what: "A rewrite that keeps every fact but shares the blame the way the evidence does.",
    why: "It saves the producer time under live pressure.",
  },
  justified: {
    title: "Justified blame",
    what: "When one player really did carry 60 percent or more of the danger, naming them alone is fair.",
    why: "Many Hands is fair both ways. It does not excuse real mistakes.",
  },
  readingLevel: {
    title: "Reading level",
    what: "Changes how much detail the explanations on this site give. The facts stay the same.",
    why: "So everyone, from fans to engineers, can follow.",
  },
  theme: {
    title: "Theme",
    what: "Light, dark, or follow your device.",
    why: "Light reads best for most people; dark can help in low light or with some vision conditions.",
  },
  judges: {
    title: "Judges start here",
    what: "A three-minute path through the project, mapped to each judging criterion.",
    why: "So the evidence for every claim is one click away.",
  },
  policy: {
    title: "Policy",
    what: "The fairness limits this broadcaster has chosen: where Watch and Unfair begin.",
    why: "Different organisations make different choices. This is Bring Your Own Policy.",
  },
  approve: {
    title: "Approve",
    what: "Sends this line to air.",
    why: "A person has the final say on anything the check does not pass as Fair.",
  },
  reasonRequired: {
    title: "Reason required",
    what: "An Unfair line can still be aired, but the producer must say why.",
    why: "It keeps an honest record of every decision.",
  },
  auditLog: {
    title: "Audit log",
    what: "A record of every decision. Each entry includes a fingerprint of the one before, so any change shows.",
    why: "Anyone can check what aired, and why, after the match.",
    tech: "SHA-256 hash chain computed in your browser with the Web Crypto API. Press Verify to recompute it.",
  },
  failClosed: {
    title: "Fails closed",
    what: "If the fairness check is not working, nothing airs.",
    why: "Safety must not depend on everything going right.",
  },
  audience: {
    title: "Audience",
    what: "Who this version is written for: analyst, casual fan, club fan, one featured player, or another language.",
    why: "The same facts, told the way each viewer needs. Every version is checked separately.",
  },
  vaep: {
    title: "Action value",
    what: "How much an action changed each team's chance of scoring soon.",
    why: "It lets us compare passes, tackles and shots on one scale.",
    tech: "VAEP (Decroos et al., KDD 2019): two gradient-boosted classifiers estimate the chance of scoring and of conceding within the next 10 actions; an action's value is the change in their difference.",
    more: { label: "Research", to: "/learn#references" },
  },
  lastTouch: {
    title: "Last-touch blame",
    what: "The simple rule that blames whoever lost the ball last.",
    why: "It is the obvious alternative, so it is the baseline we measure against.",
  },
  negativeControl: {
    title: "Negative control",
    what: "A test where the right answer is to do nothing: here, cases where one player really was to blame.",
    why: "It measures how often the system cries wolf. Ours is scored against a known true cause, not against our own ledger.",
  },
  external: {
    title: "External benchmark",
    what: "A test on real public match data that we did not create, where a data company had already marked the error.",
    why: "It shows the method works beyond our own examples.",
  },
  synthetic: {
    title: "Synthetic benchmark",
    what: "A test on our fictional matches, where we know the true cause of every goal.",
    why: "Real data never tells you the true cause. Ours does, because we can replay each attack without the mistake.",
  },
  groundTruth: {
    title: "Ground truth",
    what: "The real answer. Here: how much less dangerous an attack becomes when one mistake is removed, measured over 100 replays.",
    why: "It is how we can grade the method honestly.",
  },
  calibration: {
    title: "Calibrated",
    what: "Our fictional matches are tuned so their statistics look like real football.",
    why: "So results on them mean something in the real world.",
  },
  ci: {
    title: "95 percent interval",
    what: "The range the true value most likely sits in, given how many cases we tested.",
    why: "A number without its uncertainty can mislead.",
  },
  synthetic_data: {
    title: "Fictional match",
    what: "Created by our simulator. No real players or clubs.",
    why: "The hackathon requires synthetic data, and it protects real people.",
  },
  replay: {
    title: "Replay mode",
    what: "A recorded fictional match is playing, and checks run in your browser.",
    why: "The demo works even if the server or the AI is unavailable.",
  },
  mcp: {
    title: "MCP server",
    what: "A standard way for AI assistants to use outside tools. Ours offers 8 tools.",
    why: "Your own AI assistant can check stories without new code.",
  },
  cli: {
    title: "Command line",
    what: "Run checks and rerun our benchmarks from a terminal.",
    why: "Judges and engineers can reproduce every number.",
  },
  byo: {
    title: "Bring your own",
    what: "Use your own sentences, your own fairness limits, and your own match files.",
    why: "So Many Hands works on your content, not only ours.",
  },
  pipeline: {
    title: "The five stages",
    what: "Ingest, Interpret, Explain, Render, Personalize: the pipeline the hackathon asks for.",
    why: "Each stage is a visible part of the product.",
  },
  recap: {
    title: "Match recap",
    what: "The whole match in a few sentences, for a casual fan, an analyst or a Spanish speaker. The Recapper agent writes it; the Auditor checks every sentence about a goal against that goal's evidence.",
    why: "A recap is where one player usually gets the blame for a whole match. Here an unfair sentence is swapped for a fair one before anyone reads it.",
    tech: "POST /v1/matches/{id}/recap. gpt-5-mini writes JSON sentences tagged with the goal each is about; each is read by the rules and the gpt-5-mini reader, scored in code, and scoreline-checked. Unfair or wrong sentences are replaced by the fair template line; blame not tied to a goal is dropped.",
  },
  liveFeed: {
    title: "Live feed",
    what: "The match arrives as a stream of events through Azure Event Hubs. When a goal arrives, it wakes the AI agents by itself. A Fair line goes on air at once; anything else waits for you.",
    why: "In a real studio nobody has time to press a button when a goal goes in, but a person should decide anything that is not clearly fair.",
    tech: "Event Hubs (Entra ID only) carries each action; a consumer in the Container App runs the Agent Framework workflow on every decisive moment. The Auditor hands the approved line on before the audience versions are written: Fair lines go to the broadcast-graphics hub, others to the producer queue (GET /v1/queue). Every decision is in a hash-chained log (GET /v1/log). Time from goal to the line on air is measured on every goal.",
  },
  evidenceCheck: {
    title: "Evidence check",
    what: "The agent picks the one action the verdict depends on most, plays it, and asks you a single question about it.",
    why: "Data feeds make mistakes. A person who can see the replay settles it in seconds, and the agent knows exactly what to ask.",
    tech: "Deciding action = the largest lost ball by the most responsible player. No removes it and recomputes responsibility in the browser; Can't tell requires a reason to air any line blaming that player.",
  },
  agents: {
    title: "The agents",
    what: "Investigator gathers evidence, Narrator writes with gpt-5-mini, Auditor scores in code, Personalizer writes each audience version.",
    why: "Each has one job, and the one that decides fairness is never an AI.",
    tech: "Microsoft Agent Framework workflow on Microsoft Foundry: Investigator, Narrator and Auditor in a loop of at most two revisions, then a fair-by-construction template; Personalizer fan-out; every variant re-audited; fails closed.",
  },
  redTeam: {
    title: "Red team",
    what: "An attacker agent tries to get unfair lines past the Auditor; a separate judge agent decides which were unfair.",
    why: "A fairness check is only as good as the hardest attack it has survived.",
    tech: "Hot Take and Judge are separate gpt-5-mini agents; Judge quotes are verified in code. Every attack is saved in benchmarks/redteam/cases.json and re-scored by the test suite on every commit.",
  },
} satisfies Record<string, InfoEntry>;

export type InfoId = keyof typeof INFO;
