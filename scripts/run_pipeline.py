"""Main pipeline dispatcher — invoked by the cron workflow.

Finds books ready to advance, routes each to the correct stage script,
and records outcomes in state.runs.

Only Stage 1 (dossier) is wired today. As more stages ship, add entries
to STAGE_MAP.

Usage:
    python scripts/run_pipeline.py --books-root ggb-books
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from state import books_ready_to_advance, load_state, mark_error  # noqa: E402


# Map "current status" → the stage script to run next.
# Statuses appearing here MUST be either in ADVANCEABLE_STATUSES or
# REVIEW_GATED (with the gate approved) — see state.py.
STAGE_MAP: dict[str, str] = {
    "Brief received": "stage_01_dossier.py",
    # Approved-and-ready-to-advance states:
    "Dossier ready — awaiting review": "stage_02_structure.py",   # TODO: not written yet
    "Structure ready — awaiting review": "stage_03_entries.py",   # TODO
    "Entries ready — awaiting review": "stage_04_sample_chapter.py",  # TODO
    "Sample chapter ready — awaiting review": "stage_05_kdp_metadata.py",  # TODO
    # Auto-advancing drafting states:
    "Structure drafting": "stage_02_structure.py",
    "Entries generating": "stage_03_entries.py",
    "Sample chapter drafting": "stage_04_sample_chapter.py",
    "KDP metadata drafting": "stage_05_kdp_metadata.py",
    "Social assets drafting": "stage_06_social.py",
    "ACX brief drafting": "stage_10_acx.py",
    "Rights & IP drafting": "stage_11_rights.py",
    "Package assembly": "stage_12_assemble.py",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline dispatcher — advances books one stage.")
    parser.add_argument("--books-root", required=True)
    parser.add_argument("--dry-run", action="store_true", help="List work but do not execute.")
    args = parser.parse_args()

    books_root = Path(args.books_root)
    ready = books_ready_to_advance(books_root)
    if not ready:
        print("[pipeline] No books ready to advance.")
        return

    print(f"[pipeline] {len(ready)} book(s) ready to advance: {', '.join(ready)}")

    for book_id in ready:
        state = load_state(books_root, book_id)
        status = state["status"]
        script_name = STAGE_MAP.get(status)
        if not script_name:
            print(f"[pipeline] {book_id}: no mapping for status {status!r} — skipping")
            continue

        script_path = Path(__file__).parent / script_name
        if not script_path.exists():
            print(f"[pipeline] {book_id}: {script_name} not implemented yet — skipping")
            continue

        if args.dry_run:
            print(f"[pipeline] DRY RUN — would run {script_name} for {book_id}")
            continue

        print(f"[pipeline] {book_id}: running {script_name} (status={status!r})")
        try:
            subprocess.run(
                [sys.executable, str(script_path),
                 "--books-root", str(books_root),
                 "--book-id", book_id],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"[pipeline] {book_id}: {script_name} FAILED ({e})")
            try:
                mark_error(books_root, book_id, f"{script_name} exited with {e.returncode}")
            except Exception as inner:
                print(f"[pipeline] {book_id}: could not mark error: {inner}")


if __name__ == "__main__":
    main()
