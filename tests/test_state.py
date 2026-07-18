"""Smoke tests for state.py — no external deps required."""
from __future__ import annotations

import sys
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from state import (  # noqa: E402
    STATUSES,
    new_state,
    save_state,
    load_state,
    all_book_ids,
    books_ready_to_advance,
)


def test_statuses_count() -> None:
    assert len(STATUSES) == 20, f"Expected 20 canonical statuses, got {len(STATUSES)}"


def test_new_state_defaults() -> None:
    s = new_state(
        book_id="test-book",
        working_title="Test",
        subtitle="A Test",
        prompt_template="vocabulary-reference-v1",
        one_line_brief="Test brief.",
    )
    assert s["author"] == "Darryl Elliott Brown"
    assert s["publisher"] == "Gullah Geechee Biz"
    assert s["status"] == "New"
    assert s["review_gates"]["dossier_approved"] is False
    assert s["assets_generated"]["entries_count"] == 0


def test_save_and_load_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        s = new_state("book-a", "Book A", "Sub", "vocabulary-reference-v1", "Brief A")
        save_state(root, "book-a", s)
        loaded = load_state(root, "book-a")
        assert loaded["book_id"] == "book-a"
        assert loaded["working_title"] == "Book A"


def test_all_book_ids_and_advance() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Book 1: ready (Brief received)
        s1 = new_state("book-1", "Book 1", "Sub", "vocabulary-reference-v1", "b")
        s1["status"] = "Brief received"
        save_state(root, "book-1", s1)
        # Book 2: waiting for review, gate not approved
        s2 = new_state("book-2", "Book 2", "Sub", "vocabulary-reference-v1", "b")
        s2["status"] = "Dossier ready — awaiting review"
        save_state(root, "book-2", s2)
        # Book 3: waiting for review, gate approved
        s3 = new_state("book-3", "Book 3", "Sub", "vocabulary-reference-v1", "b")
        s3["status"] = "Structure ready — awaiting review"
        s3["review_gates"]["structure_approved"] = True
        save_state(root, "book-3", s3)

        assert sorted(all_book_ids(root)) == ["book-1", "book-2", "book-3"]
        ready = sorted(books_ready_to_advance(root))
        assert ready == ["book-1", "book-3"]
