"""Create a new book folder + state.json in the books repo.

Called by the new-book.yml GitHub Actions workflow.

Usage:
    python scripts/new_book.py \
        --books-root ggb-books \
        --book-id de-gullah-book \
        --title "De Gullah Book" \
        --subtitle "A Living Vocabulary of the Gullah Geechee Corridor" \
        --template vocabulary-reference-v1 \
        --brief "One-paragraph brief" \
        --entry-count-target 370
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as `python scripts/new_book.py ...` from repo root
sys.path.insert(0, str(Path(__file__).parent))
from state import new_state, save_state  # noqa: E402
from compliance import enforce_or_hold  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new book folder + state.json.")
    parser.add_argument("--books-root", required=True, help="Path to the books repo checkout.")
    parser.add_argument("--book-id", required=True, help="Book slug (lowercase, hyphens).")
    parser.add_argument("--title", required=True)
    parser.add_argument("--subtitle", required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--brief", required=True)
    parser.add_argument("--entry-count-target", type=int, default=370)
    parser.add_argument("--section-count", type=int, default=10)
    parser.add_argument("--book-type", default="Reference")
    parser.add_argument("--sensitivity-level", default="Elevated")
    args = parser.parse_args()

    books_root = Path(args.books_root)
    book_dir = books_root / "books" / args.book_id

    if book_dir.exists():
        print(f"[new_book] Book already exists at {book_dir}, refusing to overwrite.")
        sys.exit(1)

    book_dir.mkdir(parents=True, exist_ok=True)

    # Write brief.md alongside state.json for human reference
    (book_dir / "brief.md").write_text(
        f"# {args.title}\n\n"
        f"**Subtitle:** {args.subtitle}\n"
        f"**Template:** {args.template}\n"
        f"**Target headwords:** {args.entry_count_target}\n\n"
        f"## Brief\n\n{args.brief}\n"
    )

    state = new_state(
        book_id=args.book_id,
        working_title=args.title,
        subtitle=args.subtitle,
        prompt_template=args.template,
        one_line_brief=args.brief,
        book_type=args.book_type,
        section_count=args.section_count,
        entry_count_target=args.entry_count_target,
        cultural_sensitivity_level=args.sensitivity_level,
    )
    # Advance immediately from New → Brief received so cron picks it up
    state["status"] = "Brief received"
    save_state(books_root, args.book_id, state)

    # Hard compliance gate: only a compliant intake advances. On failure the
    # book is left on compliance hold (Paused) and we exit non-zero.
    report = enforce_or_hold(books_root, args.book_id, scan_outputs=False, apply=True, hold=True)
    if not report.gate_passed:
        print(f"[new_book] COMPLIANCE HOLD for {args.book_id}: {report.summary()}")
        for v in report.blocks:
            print(f"  [block] {v.code} ({v.path}): {v.detail}")
        sys.exit(1)

    print(f"[new_book] Created book folder at {book_dir}")
    print(f"[new_book] Compliance gate passed (ruleset {report.ruleset_version}).")
    print(f"[new_book] Status set to 'Brief received' — cron will advance on next tick.")


if __name__ == "__main__":
    main()
