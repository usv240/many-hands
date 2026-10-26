import { Button, MessageBar, MessageBarBody } from "@fluentui/react-components";
import { ArrowDownload20Regular, ArrowUpload20Regular, Document20Regular } from "@fluentui/react-icons";
import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Info, Term } from "../components/Info";
import { PageHeader } from "../components/Layout";
import { buildMatch, type ParseReport, parseCsv } from "../engine/ledger";
import type { MatchData } from "../engine/types";
import { addUploaded } from "../state/uploads";

const MAX_BYTES = 20 * 1024 * 1024;

export default function Byo() {
  const nav = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const [report, setReport] = useState<(ParseReport & { id?: number; moments?: number }) | null>(null);
  const [drag, setDrag] = useState(false);

  const read = async (file: File) => {
    if (file.size > MAX_BYTES) { setReport({ ok: false, rows: 0, missing: [], message: "That file is larger than 20 MB." }); return; }
    const text = await file.text();
    try {
      if (file.name.endsWith(".json")) {
        const data = JSON.parse(text) as MatchData;
        if (!data.chains || !data.roster) throw new Error("This JSON is not a Many Hands match file.");
        const id = addUploaded(data);
        setReport({ ok: true, rows: data.chains.length, missing: [], message: `Loaded ${data.chains.length} moments.`, id, moments: data.chains.length });
        return;
      }
      const { actions, meta, report: r } = parseCsv(text);
      if (!r.ok) { setReport(r); return; }
      const built = buildMatch(actions, meta);
      const id = addUploaded(built);
      setReport({ ...r, id, moments: built.chains.length,
        message: `${r.message} Found ${built.chains.length} decisive moments. Score ${built.match.score[0]} - ${built.match.score[1]}.` });
    } catch (e) {
      setReport({ ok: false, rows: 0, missing: [], message: String((e as Error).message) });
    }
  };

  return (
    <div className="mh-page">
      <PageHeader title="Bring your own" info="byo"
        purpose="Use Many Hands on your own content: your own sentences, your own fairness limits, and your own match files." />

      <div className="mh-grid-3">
        <article className="mh-card">
          <h2>Your own sentences</h2>
          <p>Paste any script, caption or recap line and check it against a moment.</p>
          <Link to="/check" className="mh-btn">Check a sentence</Link>
        </article>
        <article className="mh-card">
          <h2><Term id="policy">Your own limits</Term></h2>
          <p>Set where Watch and Unfair begin. Open "Your fairness limits" on the Check page; the API takes the same settings.</p>
          <Link to="/check" className="mh-btn">Set limits</Link>
        </article>
        <article className="mh-card">
          <h2>Your own match</h2>
          <p>Load a rated match file below. It is read in your browser and never leaves your device.</p>
          <a href="#upload" className="mh-btn">Load a match</a>
        </article>
      </div>

      <section className="mh-section" id="upload" aria-labelledby="up">
        <h2 id="up">Load a match file</h2>
        <div
          className={`mh-drop${drag ? " is-drag" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) read(f); }}
        >
          <Document20Regular aria-hidden />
          <p><strong>Drop a file here</strong>, or choose one. Dragging is never required.</p>
          <input ref={input} type="file" accept=".csv,.json" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) read(f); }} />
          <div className="mh-row">
            <Button appearance="primary" icon={<ArrowUpload20Regular />} onClick={() => input.current?.click()}>Choose a file</Button>
            <a className="mh-btn" href="/data/sample-match.csv" download><ArrowDownload20Regular aria-hidden /> Download a sample</a>
          </div>
          <p className="mh-small mh-muted">Your file stays in this browser tab. Closing the tab deletes it.</p>
        </div>
        {report && (
          <MessageBar intent={report.ok ? "success" : "error"} className="mh-mt">
            <MessageBarBody>
              {report.message}
              {report.ok && report.id !== undefined && (
                <> <Button size="small" appearance="primary" onClick={() => nav(`/studio?match=${report.id}`)}>Open in the Studio</Button></>
              )}
            </MessageBarBody>
          </MessageBar>
        )}
      </section>

      <section className="mh-section" aria-labelledby="formats">
        <h2 id="formats">Which files work</h2>
        <div className="mh-table-wrap">
          <table className="mh-table">
            <thead><tr><th>File</th><th>Where it works</th><th>What it needs</th></tr></thead>
            <tbody>
              <tr><td><Term id="spadl">Rated match file</Term> (CSV, one action per row, in the SPADL format)</td><td>Here, in your browser</td>
                <td>period_id, time_seconds, team_id, player_id, type_name, result_name, start_x, start_y, end_x, end_y, <Term id="vaep">vaep_value</Term>. Optional: player_name, shirt, role, team_name.</td></tr>
              <tr><td>Many Hands match JSON</td><td>Here, in your browser</td><td>The format our API and exporter produce.</td></tr>
              <tr><td>Raw provider files: StatsBomb, Wyscout, Opta, Stats Perform, Sportec, Metrica and others</td><td>API and command line</td>
                <td>Converted with the open-source kloppy and socceraction libraries, then rated by our action value model.</td></tr>
            </tbody>
          </table>
        </div>
        <p className="mh-note">
          Hackathon note: every sample here is synthetic. The point is to show that a broadcaster could plug in its own feed.
          No real match data is used by the product. <Info id="synthetic_data" />
        </p>
      </section>
    </div>
  );
}
