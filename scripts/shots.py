"""Capture the product screens (gallery and visual review) and run an accessibility scan.

Drives installed Chrome with Playwright against the live site (or --base). Interactions are real:
the agents run on Microsoft Foundry and the live feed goes through Azure Event Hubs.

Usage:
    uv run --no-project --with playwright python scripts/shots.py --out docs/gallery
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

LIVE = "https://ca-manyhands-7kzrrno7qr6zo.orangedune-9d42108b.eastus2.azurecontainerapps.io"
AXE = "https://cdn.jsdelivr.net/npm/axe-core@4.14.0/axe.min.js"


def theme(page: Page, base: str, mode: str) -> None:
    page.goto(base + "/learn")
    page.evaluate(f"localStorage.setItem('mh-theme', '{mode}')")


def axe(page: Page) -> list[str]:
    page.add_script_tag(url=AXE)
    res = page.evaluate("""async () => (await axe.run({ exclude: [['[data-tabster-dummy]']] },
        { runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'] } }))
        .violations.map(v => `${v.id} (${v.nodes.length}): ${v.nodes[0].target[0]}`)""")
    return res


def overflow(page: Page) -> int:
    return page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=LIVE)
    ap.add_argument("--out", type=Path, default=Path("docs/gallery"))
    ap.add_argument("--skip-live", action="store_true", help="skip the steps that call the agents")
    ap.add_argument("--only-scan", action="store_true", help="only accessibility and overflow")
    args = ap.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"base": args.base, "axe": {}, "overflow": {}, "timings": {}}
    b = args.base.rstrip("/")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)

        # Accessibility and overflow, every page, both themes, desktop and phone.
        pages = ["/", "/how-it-works", "/check", "/studio", "/results", "/judges", "/learn", "/developers", "/trust", "/byo"]
        for mode in ("light", "dark"):
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
            page = ctx.new_page()
            theme(page, b, mode)
            for path in pages:
                page.goto(b + path, wait_until="networkidle")
                page.wait_for_timeout(600)
                report["axe"][f"{mode} {path}"] = axe(page)
                report["overflow"][f"1440 {mode} {path}"] = overflow(page)
            ctx.close()
        for width in (360, 768):
            ctx = browser.new_context(viewport={"width": width, "height": 860})
            page = ctx.new_page()
            for path in pages:
                page.goto(b + path, wait_until="networkidle")
                page.wait_for_timeout(400)
                report["overflow"][f"{width} {path}"] = overflow(page)
            ctx.close()

        # Product screens for the gallery and for visual review.
        for mode in () if args.only_scan else ("light", "dark"):
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
            page = ctx.new_page()
            theme(page, b, mode)
            page.goto(b + "/", wait_until="networkidle")
            page.screenshot(path=str(out / f"home-{mode}.png"))
            page.goto(b + "/results", wait_until="networkidle")
            page.screenshot(path=str(out / f"results-top-{mode}.png"))
            page.goto(b + "/studio", wait_until="networkidle")
            page.wait_for_timeout(800)
            page.screenshot(path=str(out / f"studio-{mode}.png"), full_page=True)
            ctx.close()

        if not args.skip_live and not args.only_scan:
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            theme(page, b, "light")

            # 1. Home: the agents fix the pundit's line live.
            page.goto(b + "/", wait_until="networkidle")
            t0 = time.time()
            page.get_by_role("button", name="Fix it with the agents, live").click()
            page.wait_for_selector(".mh-hero-card .mh-trace", timeout=90000)
            report["timings"]["home_fix_s"] = round(time.time() - t0, 1)
            page.wait_for_timeout(1200)
            box = page.locator(".mh-hero").bounding_box()  # pad the crop so the headline does not touch the frame
            page.screenshot(path=str(out / "1-home-agents-fix-the-line.png"), full_page=True,
                            clip={"x": max(0, box["x"] - 40), "y": max(0, box["y"] - 24),
                                  "width": min(box["width"] + 80, 1440 - max(0, box["x"] - 40)),
                                  "height": box["height"] + 48})

            # 2. Studio: the evidence check, with the replay on the deciding action.
            page.goto(b + "/studio", wait_until="networkidle")
            page.wait_for_selector(".mh-evidence-check")
            page.locator(".mh-evidence").screenshot(path=str(out / "2-studio-evidence-check.png"))

            # 3. Studio: the AI desk fixes a line.
            t0 = time.time()
            page.get_by_role("button", name="Fix it with the agents").first.click()
            page.wait_for_selector(".mh-desk-region .mh-trace", timeout=90000)
            report["timings"]["desk_fix_s"] = round(time.time() - t0, 1)
            page.wait_for_timeout(1500)
            page.locator(".mh-desk-region").screenshot(path=str(out / "3-studio-ai-desk.png"))

            # 4. Studio: the live feed through Azure Event Hubs wakes the agents.
            #    Stricter policy, so the producer queue is visible: approve the first line, leave the next waiting.
            page.get_by_label("Air Fair lines automatically", exact=False).uncheck()
            page.get_by_role("button", name="Kick off the live feed").click()
            page.wait_for_selector(".mh-live-goal.is-pending", timeout=120000)
            page.locator(".mh-live-goal.is-pending").first.get_by_role("button", name="Air it").click()
            page.wait_for_function(
                "document.querySelectorAll('.mh-live-goal').length >= 2 && document.querySelector('.mh-live-goal.is-pending')",
                timeout=120000)
            page.wait_for_timeout(1500)
            page.locator(".mh-desk-region").screenshot(path=str(out / "4-studio-live-feed.png"))
            page.get_by_role("button", name="Stop the feed").click()

            # 5. Audience versions and 6. the pre-air queue asking for a reason.
            page.locator(".mh-audiences").screenshot(path=str(out / "5-studio-audience-versions.png"))
            unfair = page.locator(".mh-queue--unfair").first
            unfair.get_by_role("button", name="Approve", exact=True).click()
            page.wait_for_timeout(300)
            page.locator(".mh-queue").screenshot(path=str(out / "6-studio-reason-required.png"))
            ctx.close()

            # 7. Results: the red team.
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            page.goto(b + "/results#redteam", wait_until="networkidle")
            page.locator("#redteam").locator("xpath=..").screenshot(path=str(out / "7-results-red-team.png"))

            # 8. Phone, dark mode: Check a line.
            ctx.close()
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            page = ctx.new_page()
            theme(page, b, "dark")
            page.goto(b + "/check", wait_until="networkidle")
            page.wait_for_timeout(800)
            page.screenshot(path=str(out / "8-phone-dark-check.png"), full_page=False)
            ctx.close()

        browser.close()

    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    bad_axe = {k: v for k, v in report["axe"].items() if v}
    bad_overflow = {k: v for k, v in report["overflow"].items() if v > 0}
    print("axe violations:", json.dumps(bad_axe, indent=1) if bad_axe else "none on any page in either theme")
    print("horizontal overflow:", bad_overflow or "none")
    print("timings:", report["timings"])


if __name__ == "__main__":
    main()
