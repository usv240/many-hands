"""Many Hands fairness gate for GitHub Actions. Standard library only.

Checks every line in the matched files against the Many Hands API, writes a table with the score,
the reason and a fair rewrite to the job summary, annotates each failing line, and exits non-zero
if any line is Unfair (or Watch, if asked). Leaves its verdicts in fairness-report.json.
"""

from __future__ import annotations

import glob
import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get("GATE_API", "").rstrip("/")
FILES = os.environ.get("GATE_FILES", "")
FAIL_ON = os.environ.get("GATE_FAIL_ON", "unfair")
DEEP = os.environ.get("GATE_DEEP", "true").lower() == "true"
ORDER = {"fair": 0, "watch": 1, "unfair": 2}


def check(chain_id: str, text: str) -> dict:
    body = json.dumps({"chain_id": chain_id, "text": text, "deep": DEEP}).encode()
    req = urllib.request.Request(f"{API}/v1/audit", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main() -> int:
    patterns = [x.strip() for x in FILES.replace(",", "\n").splitlines() if x.strip()]  # paths may contain spaces
    paths = sorted({p for pattern in patterns for p in glob.glob(pattern, recursive=True)})
    if not paths:
        print(f"::error::No files matched {FILES!r}")
        return 1
    rows, worst = [], "fair"
    for path in paths:
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
        for i, item in enumerate(items):
            try:
                r = check(item["chain_id"], item["text"])
            except (urllib.error.URLError, KeyError) as exc:
                print(f"::error file={path}::Line {i + 1} could not be checked: {exc}")
                return 1
            if ORDER[r["verdict"]] > ORDER[worst]:
                worst = r["verdict"]
            failing = ORDER[r["verdict"]] >= ORDER[FAIL_ON]
            if failing:
                print(f"::error file={path},title=Scapegoating ({r['si']:.2f})::{item['text']} | "
                      f"{' '.join(r['reasons'])} Fair version: {r['fair_rewrite']}")
            rows.append({"file": path, "line": i + 1, "text": item["text"], "si": r["si"],
                         "verdict": r["verdict"], "reason": " ".join(r["reasons"]),
                         "fair_rewrite": r["fair_rewrite"], "failing": failing})
    with open("fairness-report.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as s:
            s.write("## Many Hands fairness gate\n\n| Line | Score | Verdict | Why | Fair version |\n|---|---|---|---|---|\n")
            for r in rows:
                s.write(f"| {r['text']} | {r['si']:.2f} | {r['verdict']} | {r['reason']} | {r['fair_rewrite'] or ''} |\n")
    failed = sum(r["failing"] for r in rows)
    print(f"Checked {len(rows)} lines: {failed} failing (fail on {FAIL_ON} or worse). Worst verdict: {worst}.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
