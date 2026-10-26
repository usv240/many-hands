import { Button, Tab, TabList } from "@fluentui/react-components";
import { Checkmark16Regular, Copy16Regular } from "@fluentui/react-icons";
import { useState } from "react";
import { Term } from "../components/Info";
import { PageHeader } from "../components/Layout";

function Code({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="mh-codeblock">
      <Button size="small" appearance="subtle" className="mh-copy" icon={copied ? <Checkmark16Regular /> : <Copy16Regular />}
        onClick={() => { navigator.clipboard?.writeText(code); setCopied(true); window.setTimeout(() => setCopied(false), 1500); }}>
        {copied ? "Copied" : "Copy"}
      </Button>
      <pre className="mh-code">{code}</pre>
    </div>
  );
}

const QUICK: Record<string, string> = {
  curl: `curl -X POST http://localhost:8000/v1/audit \\
  -H "Content-Type: application/json" \\
  -d '{"chain_id": "20003-300", "text": "Number 8s howler cost them the goal."}'`,
  python: `import httpx
r = httpx.post("http://localhost:8000/v1/audit", json={
    "chain_id": "20003-300",
    "text": "Number 8's howler cost them the goal.",
    "policy": {"watch_above": 0.2, "unfair_above": 0.4},
})
print(r.json()["si"], r.json()["verdict"], r.json()["fair_rewrite"])`,
  cli: `uv run python packages/sdk/manyhands/cli.py matches
uv run python packages/sdk/manyhands/cli.py chains 20003
uv run python packages/sdk/manyhands/cli.py audit 20003-300 "Number 8's howler cost them the goal."`,
};

const ENDPOINTS = [
  ["GET", "/v1/health", "Service status and mode"],
  ["GET", "/v1/matches", "Fictional matches available"],
  ["GET", "/v1/matches/{id}/chains", "Decisive moments with responsibility and the unsung"],
  ["GET", "/v1/matches/{id}/roster", "Players, for naming in sentences"],
  ["GET", "/v1/chains/{chain_id}", "Every action in the build-up, with values"],
  ["GET", "/v1/chains/{chain_id}/responsibility?method=", "Shares by method: combined, vaep, lasttouch"],
  ["GET", "/v1/chains/{chain_id}/counterfactual?action_id=", "Danger removed if one loss had not happened"],
  ["POST", "/v1/audit", "Score a sentence; reasons, contrastive line and fair rewrite (deep: true adds the gpt-5-mini reader)"],
  ["POST", "/v1/broadcast", "The full agent workflow on one moment: write or fix the line, audit it, five audience versions"],
  ["POST", "/v1/matches/{id}/recap", "The whole match as a recap for casual, analyst or es; every sentence audited"],
  ["POST", "/v1/matches/{id}/kickoff?auto_air=", "Play a match into Azure Event Hubs; goals wake the agents"],
  ["GET", "/v1/matches/{id}/live", "Server-Sent Events: every action, every line, every decision"],
  ["GET", "/v1/queue", "Live lines waiting for a producer"],
  ["POST", "/v1/queue/{chain_id}/decision", "Approve or reject a queued line; a reason is required for one that is not Fair"],
  ["GET", "/v1/log", "The hash-chained decision log, with a verification"],
  ["GET", "/v1/metrics", "Live timings, graphics sent, usage limits"],
];

const TOOLS = ["list_matches", "get_chains", "get_chain", "responsibility", "counterfactual", "extract_blame", "audit_line", "fair_rewrite_constraints"];

export default function Developers() {
  const [tab, setTab] = useState("curl");
  return (
    <div className="mh-page">
      <PageHeader title="Developers" purpose="Use Many Hands from your own software: a REST API, an MCP server for AI assistants, and a command line that can rerun our benchmarks." />
      <section className="mh-section" aria-labelledby="quick">
        <h2 id="quick">Quickstart</h2>
        <Code code={`git clone <repository>\ncd many-hands\nuv sync\nuv run uvicorn services.api.app:app --port 8000   # docs at http://localhost:8000/docs`} />
        <TabList selectedValue={tab} onTabSelect={(_, d) => setTab(String(d.value))} aria-label="Language">
          <Tab value="curl">curl</Tab><Tab value="python">Python</Tab><Tab value="cli">Command line</Tab>
        </TabList>
        <Code code={QUICK[tab]} />
      </section>
      <section className="mh-section" aria-labelledby="api">
        <h2 id="api">REST API, version 1</h2>
        <div className="mh-table-wrap">
          <table className="mh-table">
            <thead><tr><th>Method</th><th>Path</th><th>What it does</th></tr></thead>
            <tbody>{ENDPOINTS.map(([m, p, d]) => <tr key={p}><td><code>{m}</code></td><td><code>{p}</code></td><td>{d}</td></tr>)}</tbody>
          </table>
        </div>
        <p className="mh-small mh-muted">OpenAPI document at <code>/openapi.json</code>; interactive docs at <code>/docs</code>. The demo API is open, with no key: each caller gets 12 model-backed requests a minute, and past the daily model budget the agents answer with their templates instead of failing.</p>
      </section>
      <section className="mh-section" id="mcp" aria-labelledby="mcph">
        <h2 id="mcph"><Term id="mcp">MCP server</Term></h2>
        <p>Give any MCP client, such as GitHub Copilot in VS Code, the same tools our agents use.</p>
        <ul className="mh-tools">{TOOLS.map((t) => <li key={t}><code>{t}</code></li>)}</ul>
        <Code code={`// .vscode/mcp.json
{
  "servers": {
    "many-hands": {
      "command": "uv",
      "args": ["run", "python", "services/api/mcp_server.py"]
    }
  }
}

# or over HTTP for remote clients
uv run python services/api/mcp_server.py --http --port 8010`} />
      </section>
      <section className="mh-section" id="cli" aria-labelledby="clih">
        <h2 id="clih"><Term id="cli">Command line</Term></h2>
        <Code code={`uv run python packages/sdk/manyhands/cli.py verify --suite synthetic
uv run python packages/sdk/manyhands/cli.py verify --suite external`} />
        <p className="mh-small mh-muted"><code>verify</code> reruns a benchmark and compares every published number with the fresh result.</p>
      </section>
    </div>
  );
}
