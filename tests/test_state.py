"""Smoke tests for state.py — no external deps required."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from state import (  # noqa: E402
    STATUSES,
    AUTHOR,
    PUBLISHER,
    new_state,
    save_state,
    load_state,
    all_book_ids,
    books_ready_to_advance,
)


def test_locked_constants_exact() -> None:
    assert AUTHOR == "Darryl Elliott Brown"
    assert PUBLISHER == "Gullah Geechee Biz"


def test_new_state_hardwires_author_publisher() -> None:
    s = new_state("b", "Title", "Sub", "vocabulary-reference-v1", "Brief text long enough.")
    assert s["author"] == AUTHOR
    assert s["publisher"] == PUBLISHER


def test_new_state_has_no_author_publisher_params() -> None:
    """Author/publisher must not be overridable via new_state() arguments."""
    params = inspect.signature(new_state).parameters
    assert "author" not in params
    assert "publisher" not in params


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


def _write_brief(root: Path, book_id: str, title: str) -> None:
    """The compliance gate requires a real brief, so give each book one."""
    book_dir = root / "books" / book_id
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "brief.md").write_text(
        f"# {title}\n\nA sufficiently detailed brief about the book's content and scope.\n"
    )


def test_all_book_ids_and_advance() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        brief = "A sufficiently detailed one-line brief about the book's content."
        # Book 1: ready (Brief received)
        s1 = new_state("book-1", "Book 1", "Sub", "vocabulary-reference-v1", brief)
        s1["status"] = "Brief received"
        save_state(root, "book-1", s1)
        _write_brief(root, "book-1", "Book 1")
        # Book 2: waiting for review, gate not approved
        s2 = new_state("book-2", "Book 2", "Sub", "vocabulary-reference-v1", brief)
        s2["status"] = "Dossier ready — awaiting review"
        save_state(root, "book-2", s2)
        _write_brief(root, "book-2", "Book 2")
        # Book 3: waiting for review, gate approved
        s3 = new_state("book-3", "Book 3", "Sub", "vocabulary-reference-v1", brief)
        s3["status"] = "Structure ready — awaiting review"
        s3["review_gates"]["structure_approved"] = True
        save_state(root, "book-3", s3)
        _write_brief(root, "book-3", "Book 3")

        assert sorted(all_book_ids(root)) == ["book-1", "book-2", "book-3"]
        ready = sorted(books_ready_to_advance(root))
        assert ready == ["book-1", "book-3"]
