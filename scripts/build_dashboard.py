"""Build a single-file HTML dashboard from every book's state.json.

Reads books/<id>/state.json from the ggb-books repo and renders an
overview page showing status, progress bar per stage, entry counts,
last-run timestamps, and links to the book folder + any open review PRs.

Output: dashboard/index.html — served by GitHub Pages from the pipeline repo.

Zero external dependencies. No JS frameworks. Just HTML + inline CSS.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from state import STATUSES, all_book_ids, load_state, AUTHOR, PUBLISHER  # noqa: E402


# Map each status to a progress percentage (0-100) for the progress bar
STATUS_PROGRESS: dict[str, int] = {
    "New": 0,
    "Brief received": 5,
    "Dossier drafting": 10,
    "Dossier ready — awaiting review": 15,
    "Structure drafting": 20,
    "Structure ready — awaiting review": 25,
    "Entries generating": 45,
    "Entries ready — awaiting review": 60,
    "Sample chapter drafting": 65,
    "Sample chapter ready — awaiting review": 70,
    "Sample chapter approved": 72,
    "KDP metadata drafting": 78,
    "Social assets drafting": 84,
    "ACX brief drafting": 90,
    "Rights & IP drafting": 94,
    "Package assembly": 97,
    "Ready for KDP handoff": 100,
    "Published": 100,
    "Error": 0,
    "Paused": 0,
}

STATUS_COLOR: dict[str, str] = {
    "Ready for KDP handoff": "#437A22",  # success green
    "Published": "#01696F",               # primary teal
    "Error": "#A12C7B",                   # error magenta
    "Paused": "#7A7974",                  # muted grey
}


def compliance_summary(state: dict) -> dict:
    """Extract the compliance fields the dashboard shows for one book.

    Returns a dict with a normalized gate label (PASS / HOLD / UNKNOWN), the
    ruleset version, the last checked_at timestamp, and the stamped
    author/publisher. Missing compliance data yields an UNKNOWN gate — the
    dashboard never crashes on a book that has not been scanned yet.
    """
    comp = state.get("compliance") or {}
    if "gate_passed" in comp:
        gate = "PASS" if comp.get("gate_passed") else "HOLD"
    else:
        gate = "UNKNOWN"

    checked_at = comp.get("checked_at") or ""
    if checked_at:
        checked_at = checked_at.replace("T", " ").split(".")[0].split("+")[0].strip() + " UTC"

    return {
        "gate": gate,
        "gate_class": {"PASS": "done", "HOLD": "error", "UNKNOWN": "paused"}[gate],
        "ruleset_version": comp.get("ruleset_version") or "—",
        "checked_at": checked_at or "never",
        "author": state.get("author") or "—",
        "publisher": state.get("publisher") or "—",
    }


def status_class(status: str) -> str:
    if status == "Error":
        return "error"
    if status == "Paused":
        return "paused"
    if status in ("Ready for KDP handoff", "Published"):
        return "done"
    if "awaiting review" in status:
        return "review"
    return "in-progress"


def render_book_card(book_id: str, state: dict, books_repo: str) -> str:
    status = state.get("status", "Unknown")
    progress = STATUS_PROGRESS.get(status, 0)
    color_class = status_class(status)

    title = html.escape(state.get("working_title") or book_id)
    subtitle = html.escape(state.get("subtitle") or "")
    entry_count = state.get("assets_generated", {}).get("entries_count", 0)
    target = state.get("entry_count_target", 0)
    stages_done = len(state.get("stages_completed", []))

    # Compute the entry progress separately (only meaningful during entries stage)
    entry_pct = int((entry_count / target) * 100) if target else 0

    last_run_str = "—"
    runs = state.get("last_runs", [])
    if runs:
        try:
            ts = runs[-1].get("timestamp", "")
            last_run_str = html.escape(ts.replace("T", " ").split(".")[0] + " UTC")
        except Exception:
            pass

    comp = compliance_summary(state)
    attribution_ok = comp["author"] == AUTHOR and comp["publisher"] == PUBLISHER
    attribution_class = "done" if attribution_ok else "error"

    book_url = f"https://github.com/{books_repo}/tree/master/books/{book_id}"
    kit_path = state.get("assets_generated", {}).get("final_kit")
    kit_link = ""
    if kit_path:
        kit_url = f"https://github.com/{books_repo}/blob/master/{kit_path}"
        kit_link = f'<a class="btn" href="{kit_url}">Download final kit</a>'

    return f"""
    <article class="card {color_class}">
      <header>
        <h2>{title}</h2>
        <p class="subtitle">{subtitle}</p>
      </header>
      <div class="status-row">
        <span class="pill pill-{color_class}">{html.escape(status)}</span>
        <span class="meta">Book ID: <code>{html.escape(book_id)}</code></span>
      </div>
      <div class="progress-wrap">
        <div class="progress-label">
          <span>Pipeline progress</span>
          <span>{progress}%</span>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width: {progress}%"></div></div>
      </div>
      <div class="stats">
        <div class="stat"><span class="stat-value">{entry_count} / {target}</span><span class="stat-label">Entries ({entry_pct}%)</span></div>
        <div class="stat"><span class="stat-value">{stages_done}</span><span class="stat-label">Stages complete</span></div>
        <div class="stat"><span class="stat-value">{len(runs)}</span><span class="stat-label">Total LLM runs</span></div>
      </div>
      <div class="compliance-row">
        <span class="pill pill-{comp['gate_class']}" title="Compliance gate (ruleset {html.escape(comp['ruleset_version'])})">Compliance: {comp['gate']}</span>
        <span class="pill pill-{attribution_class}" title="author: {html.escape(comp['author'])} · publisher: {html.escape(comp['publisher'])}">Attribution: {'OK' if attribution_ok else 'DRIFT'}</span>
        <span class="meta">Ruleset {html.escape(comp['ruleset_version'])} · checked {html.escape(comp['checked_at'])}</span>
      </div>
      <div class="footer-row">
        <span class="last-run">Last run: {last_run_str}</span>
        <a class="btn" href="{book_url}">View files</a>
        {kit_link}
      </div>
    </article>
    """


def build_dashboard(books_root: Path, books_repo: str) -> str:
    book_ids = sorted(all_book_ids(books_root))
    cards = "\n".join(render_book_card(bid, load_state(books_root, bid), books_repo) for bid in book_ids)
    if not cards:
        cards = '<p class="empty">No books yet. Trigger the "New book intake" workflow to seed one.</p>'

    states = {bid: load_state(books_root, bid) for bid in book_ids}
    total_books = len(book_ids)
    done = sum(1 for s in states.values() if s["status"] in ("Ready for KDP handoff", "Published"))
    in_review = sum(1 for s in states.values() if "awaiting review" in s["status"])
    holds = sum(1 for s in states.values() if compliance_summary(s)["gate"] == "HOLD")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GGB Book Pipeline — Status</title>
<style>
  :root {{
    --bg: #F7F6F2;
    --surface: #FBFBF9;
    --border: #D4D1CA;
    --text: #28251D;
    --muted: #7A7974;
    --primary: #01696F;
    --error: #A12C7B;
    --success: #437A22;
    --warning: #964219;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    margin: 0;
    line-height: 1.5;
  }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 32px 24px; }}
  header.top {{ margin-bottom: 32px; }}
  header.top h1 {{ font-size: 32px; margin: 0 0 4px; letter-spacing: -0.5px; }}
  header.top .sub {{ color: var(--muted); font-size: 14px; margin: 0; }}
  .kpi-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 24px 0; }}
  .kpi {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }}
  .kpi .value {{ font-size: 28px; font-weight: 600; display: block; font-variant-numeric: tabular-nums; }}
  .kpi .label {{ font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }}
  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }}
  .card h2 {{ font-size: 18px; margin: 0; }}
  .card .subtitle {{ color: var(--muted); font-size: 13px; margin: 4px 0 0; }}
  .status-row {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
  .pill {{ display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 500; }}
  .pill-in-progress {{ background: #FFF3E0; color: #964219; }}
  .pill-review {{ background: #FFF9DB; color: #6B5B00; }}
  .pill-done {{ background: #E8F5E9; color: var(--success); }}
  .pill-error {{ background: #FBE4F0; color: var(--error); }}
  .pill-paused {{ background: #EEEEEE; color: var(--muted); }}
  .meta {{ color: var(--muted); font-size: 12px; }}
  .meta code {{ background: #F0EFEB; padding: 2px 6px; border-radius: 4px; font-size: 11px; }}
  .progress-wrap {{ margin: 8px 0; }}
  .progress-label {{ display: flex; justify-content: space-between; font-size: 12px; color: var(--muted); margin-bottom: 6px; }}
  .progress-bar {{ background: #EAE8E1; height: 8px; border-radius: 4px; overflow: hidden; }}
  .progress-fill {{ background: var(--primary); height: 100%; transition: width 400ms ease; }}
  .stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }}
  .stat {{ display: flex; flex-direction: column; }}
  .stat-value {{ font-size: 16px; font-weight: 600; font-variant-numeric: tabular-nums; }}
  .stat-label {{ font-size: 11px; color: var(--muted); }}
  .compliance-row {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 12px; }}
  .footer-row {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; padding-top: 8px; border-top: 1px solid var(--border); }}
  .last-run {{ color: var(--muted); font-size: 12px; }}
  .btn {{ display: inline-block; padding: 6px 12px; background: var(--primary); color: white; text-decoration: none; border-radius: 4px; font-size: 13px; }}
  .btn:hover {{ background: #0C4E54; }}
  .empty {{ background: var(--surface); border: 1px dashed var(--border); border-radius: 8px; padding: 40px; text-align: center; color: var(--muted); }}
  footer {{ margin-top: 48px; padding-top: 24px; border-top: 1px solid var(--border); color: var(--muted); font-size: 12px; }}
  footer a {{ color: var(--primary); }}
</style>
</head>
<body>
<div class="container">
  <header class="top">
    <h1>GGB Book Pipeline</h1>
    <p class="sub">Zero-cost book production status · Last built {now}</p>
  </header>

  <div class="kpi-row">
    <div class="kpi"><span class="value">{total_books}</span><span class="label">Books in pipeline</span></div>
    <div class="kpi"><span class="value">{in_review}</span><span class="label">Awaiting review</span></div>
    <div class="kpi"><span class="value">{done}</span><span class="label">Ready for KDP</span></div>
    <div class="kpi"><span class="value">{holds}</span><span class="label">Compliance holds</span></div>
  </div>

  <section class="grid">
    {cards}
  </section>

  <footer>
    <p>
      Pipeline repo: <a href="https://github.com/{books_repo.split('/')[0]}/ggb-book-pipeline">ggb-book-pipeline</a> ·
      Books repo: <a href="https://github.com/{books_repo}">{books_repo}</a> ·
      Author: {AUTHOR} · Publisher: {PUBLISHER}
    </p>
    <p>Every book kit in this pipeline is produced at $0 cash cost using GitHub Actions + free-tier LLM APIs.</p>
  </footer>
</div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--books-root", required=True, help="Path to cloned ggb-books repo")
    parser.add_argument("--books-repo", default="Darrylebrown/ggb-books", help="owner/name of the books repo")
    parser.add_argument("--output", default="dashboard/index.html")
    args = parser.parse_args()

    html_str = build_dashboard(Path(args.books_root), args.books_repo)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_str)
    print(f"[dashboard] Wrote {out} ({len(html_str)} bytes)")


if __name__ == "__main__":
    main()
