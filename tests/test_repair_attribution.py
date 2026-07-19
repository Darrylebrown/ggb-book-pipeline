"""Tests for the brand-attribution repair tool."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from state import AUTHOR, PUBLISHER, new_state, save_state, load_state  # noqa: E402
from repair_attribution import repair_book, repair_all  # noqa: E402


def _seed(tmp_path, book_id="book-a"):
    s = new_state(book_id, "Book A", "Sub", "vocabulary-reference-v1", "A brief that is long enough", 100)
    save_state(tmp_path, book_id, s)
    return s


def test_repair_fixes_wrong_author_and_publisher(tmp_path):
    _seed(tmp_path)
    s = load_state(tmp_path, "book-a")
    s["author"] = "Someone Else"
    s["publisher"] = "Rogue Press"
    save_state(tmp_path, "book-a", s)

    changes = repair_book(tmp_path, "book-a")

    assert len(changes) == 2
    fixed = load_state(tmp_path, "book-a")
    assert fixed["author"] == AUTHOR
    assert fixed["publisher"] == PUBLISHER


def test_repair_noop_when_already_correct(tmp_path):
    _seed(tmp_path)
    assert repair_book(tmp_path, "book-a") == []


def test_repair_dry_run_does_not_write(tmp_path):
    _seed(tmp_path)
    s = load_state(tmp_path, "book-a")
    s["author"] = "Wrong"
    save_state(tmp_path, "book-a", s)

    changes = repair_book(tmp_path, "book-a", apply=False)

    assert changes  # reports the drift
    assert load_state(tmp_path, "book-a")["author"] == "Wrong"  # but no write


def test_repair_all_reports_only_changed_books(tmp_path):
    _seed(tmp_path, "book-a")
    _seed(tmp_path, "book-b")
    s = load_state(tmp_path, "book-b")
    s["publisher"] = "Drifted"
    save_state(tmp_path, "book-b", s)

    repaired = repair_all(tmp_path)

    assert set(repaired) == {"book-b"}
    assert load_state(tmp_path, "book-b")["publisher"] == PUBLISHER
