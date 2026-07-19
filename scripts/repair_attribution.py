"""Force-set brand attribution on every book so it can never drift.

The locked brand attribution lives in [`state.py`](state.py) as the `AUTHOR` /
`PUBLISHER` constants. This tool walks every book's state.json and rewrites
`state["author"]` / `state["publisher"]` to those constants whenever they
differ. It is a repair, not a check: it always exits 0 unless something
catastrophic prevents it from reading the books tree.

Used by the daily compliance workflow *before* the compliance apply/hold pass,
so an accidental hand-edit is corrected rather than merely flagged.

CLI:
    python scripts/repair_attribution.py --books-root <root> [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from state import AUTHOR, PUBLISHER, all_book_ids, load_state, save_state  # noqa: E402


def repair_book(books_root: Path, book_id: str, apply: bool = True) -> list[str]:
    """Fix author/publisher for a single book.

    Returns a list of human-readable descriptions of what changed (empty if
    already correct). When ``apply`` is False the state is not written.
    """
    state = load_state(books_root, book_id)
    changes: list[str] = []

    if state.get("author") != AUTHOR:
        changes.append(f"author {state.get('author')!r} -> {AUTHOR!r}")
        state["author"] = AUTHOR
    if state.get("publisher") != PUBLISHER:
        changes.append(f"publisher {state.get('publisher')!r} -> {PUBLISHER!r}")
        state["publisher"] = PUBLISHER

    if changes and apply:
        save_state(books_root, book_id, state)
    return changes


def repair_all(books_root: Path, apply: bool = True) -> dict[str, list[str]]:
    """Repair every book. Returns {book_id: [changes]} for books that changed."""
    repaired: dict[str, list[str]] = {}
    for book_id in all_book_ids(books_root):
        changes = repair_book(books_root, book_id, apply=apply)
        if changes:
            repaired[book_id] = changes
    return repaired


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Force brand attribution (author/publisher) on every book."
    )
    parser.add_argument("--books-root", required=True)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change without writing.")
    args = parser.parse_args(argv)

    books_root = Path(args.books_root)
    repaired = repair_all(books_root, apply=not args.dry_run)

    verb = "Would repair" if args.dry_run else "Repaired"
    if not repaired:
        print("[repair] All books already carry the locked attribution.")
    else:
        for book_id, changes in sorted(repaired.items()):
            print(f"[repair] {verb} {book_id}: " + "; ".join(changes))
        print(f"[repair] {verb} {len(repaired)} book(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
