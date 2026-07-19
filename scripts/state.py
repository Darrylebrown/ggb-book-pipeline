"""state.json read/write helpers. Git is the version control layer.

Each book has exactly one state.json at books/<book_id>/state.json inside the
ggb-books private repo. This module reads and writes those files.

Callers pass an explicit `books_root` so tests can point at a temp dir and the
production pipeline can point at the checked-out ggb-books path.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# --- Locked brand attribution (single source of truth) ---------------------
# These are hardwired and MUST NOT be configurable anywhere in the pipeline.
# Every module that needs the author/publisher imports these constants; the
# compliance gate imports the same names so the strings can never drift.
AUTHOR = "Darryl Elliott Brown"
PUBLISHER = "Gullah Geechee Biz"


# The 20 canonical pipeline statuses. Do not add new ones without updating STAGE_MAP too.
STATUSES = [
    "New",
    "Brief received",
    "Dossier drafting",
    "Dossier ready — awaiting review",
    "Structure drafting",
    "Structure ready — awaiting review",
    "Entries generating",
    "Entries ready — awaiting review",
    "Sample chapter drafting",
    "Sample chapter ready — awaiting review",
    "Sample chapter approved",
    "KDP metadata drafting",
    "Social assets drafting",
    "ACX brief drafting",
    "Rights & IP drafting",
    "Package assembly",
    "Ready for KDP handoff",
    "Published",
    "Error",
    "Paused",
]

# Which statuses the pipeline can advance from without human intervention.
ADVANCEABLE_STATUSES = {
    "Brief received",
    "Structure drafting",
    "Entries generating",
    "Sample chapter drafting",
    "KDP metadata drafting",
    "Social assets drafting",
    "ACX brief drafting",
    "Rights & IP drafting",
    "Package assembly",
}

# Statuses that require a review-gate check before advancing.
REVIEW_GATED = {
    "Dossier ready — awaiting review": "dossier_approved",
    "Structure ready — awaiting review": "structure_approved",
    "Entries ready — awaiting review": "entries_approved",
    "Sample chapter ready — awaiting review": "sample_chapter_approved",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state(books_root: Path, book_id: str) -> dict:
    path = books_root / "books" / book_id / "state.json"
    if not path.exists():
        raise FileNotFoundError(f"No state.json for book '{book_id}' at {path}")
    return json.loads(path.read_text())


def save_state(books_root: Path, book_id: str, state: dict) -> None:
    state["last_modified"] = _now_iso()
    path = books_root / "books" / book_id / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def all_book_ids(books_root: Path) -> list[str]:
    books_dir = books_root / "books"
    if not books_dir.exists():
        return []
    return sorted(
        p.name for p in books_dir.iterdir()
        if p.is_dir() and (p / "state.json").exists()
    )


def books_ready_to_advance(books_root: Path) -> list[str]:
    """Return book_ids whose status allows advancement AND pass compliance.

    A book only advances if it clears the compliance gate. If a prior gate
    result exists in ``state.compliance`` and it blocked, the book is skipped.
    Otherwise a lightweight intake check runs (scan_outputs=False); on failure
    the book is placed on compliance hold and excluded.
    """
    # Imported lazily to avoid a circular import at module load time.
    from compliance import check_book, enforce_or_hold

    ready: list[str] = []
    for book_id in all_book_ids(books_root):
        s = load_state(books_root, book_id)
        status = s.get("status")

        status_ok = status in ADVANCEABLE_STATUSES
        if not status_ok:
            gate = REVIEW_GATED.get(status)
            status_ok = bool(gate and s.get("review_gates", {}).get(gate))
        if not status_ok:
            continue

        book_dir = books_root / "books" / book_id
        report = check_book(s, book_dir, scan_outputs=False)
        if report.gate_passed:
            ready.append(book_id)
        else:
            # Persist the hold so the book stops advancing and is visible.
            enforce_or_hold(books_root, book_id, scan_outputs=False, apply=True, hold=True)
    return ready


def new_state(
    book_id: str,
    working_title: str,
    subtitle: str,
    prompt_template: str,
    one_line_brief: str,
    book_type: str = "Reference",
    section_count: int = 10,
    entry_count_target: int = 370,
    cultural_sensitivity_level: str = "Elevated",
    corridor_scope: Optional[list[str]] = None,
    formats: Optional[list[str]] = None,
    series: str = "GGB Reference Library",
    edition: str = "Edition 1",
    target_publish_date: Optional[str] = None,
) -> dict:
    """Create a fresh state.json dict for a new book.

    Author and publisher are hardwired to the locked ``AUTHOR`` / ``PUBLISHER``
    constants and are intentionally NOT parameters — brand attribution can
    never be overridden at intake.
    """
    return {
        "book_id": book_id,
        "working_title": working_title,
        "subtitle": subtitle,
        "series": series,
        "edition": edition,
        "formats": formats or ["Paperback", "eBook", "Audiobook"],
        "author": AUTHOR,
        "publisher": PUBLISHER,
        "book_type": book_type,
        "prompt_template": prompt_template,
        "corridor_scope": corridor_scope or ["NC", "SC", "GA", "FL"],
        "section_count": section_count,
        "entry_count_target": entry_count_target,
        "cultural_sensitivity_level": cultural_sensitivity_level,
        "one_line_brief": one_line_brief,
        "target_publish_date": target_publish_date,
        "status": "New",
        "current_stage": "intake",
        "stages_completed": [],
        "stages_failed": [],
        "last_error": None,
        "review_gates": {
            "dossier_approved": False,
            "structure_approved": False,
            "entries_approved": False,
            "sample_chapter_approved": False,
            "final_kit_approved": False,
        },
        "assets_generated": {
            "dossier": None,
            "structure": None,
            "entries_count": 0,
            "sample_chapter": None,
            "kdp_metadata": None,
            "pins": [],
            "tiktok": None,
            "shorts": None,
            "substack": None,
            "acx_brief": None,
            "rights_ip": None,
            "final_kit": None,
        },
        "runs": [],
        "created": _now_iso(),
        "last_modified": _now_iso(),
    }


def mark_error(books_root: Path, book_id: str, error_msg: str) -> None:
    """Convenience: set status to Error and record the message."""
    s = load_state(books_root, book_id)
    s["status"] = "Error"
    s["last_error"] = error_msg
    save_state(books_root, book_id, s)


def record_run(
    books_root: Path,
    book_id: str,
    stage: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    status: str = "success",
    error: str = "",
) -> None:
    """Append a run record to state.runs."""
    s = load_state(books_root, book_id)
    s.setdefault("runs", []).append({
        "stage": stage,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": 0.0,
        "status": status,
        "error": error,
        "at": _now_iso(),
    })
    save_state(books_root, book_id, s)
