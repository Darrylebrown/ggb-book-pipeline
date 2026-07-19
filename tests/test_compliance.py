"""Tests for the compliance gate (ruleset v1.1)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from compliance import (  # noqa: E402
    RULESET_VERSION,
    check_text,
    check_book,
    check_kdp_metadata_file,
    enforce_or_hold,
    is_advance_allowed,
)
from state import new_state, save_state, load_state, books_ready_to_advance  # noqa: E402


VALID_KDP = """# KDP + Draft2Digital Metadata

Title: Test Book
Author: Darryl Elliott Brown
Publisher: Gullah Geechee Biz

## Description
This is a thorough and reasonably long book description that comfortably
exceeds one hundred characters so that the description length check passes
without any trouble at all.

## Keywords
Gullah, Geechee, Lowcountry, Sea Islands, corridor

## Categories / BISAC
SOC001000 Social Science / Ethnic Studies / African American Studies

## AI Disclosure
Portions of this work were produced with generative AI assistance under direct
human editorial supervision.

## Draft2Digital
Human editing and documentation retained; imprint Gullah Geechee Biz.
"""


def _make_book(root: Path, book_id: str = "test-book", title: str = "Test Book", **over) -> dict:
    s = new_state(book_id, title, "Sub", "vocabulary-reference-v1",
                  "A sufficiently detailed one-line brief about the book.")
    s.update(over)
    save_state(root, book_id, s)
    book_dir = root / "books" / book_id
    (book_dir / "brief.md").write_text(f"# {title}\n\nA sufficiently detailed brief about the book content.\n")
    return s


# --- check_text -------------------------------------------------------------

def test_clean_text_passes() -> None:
    assert check_text("A clean description of Gullah Geechee culture.") == []


def test_manus_link_blocks() -> None:
    vs = check_text("Visit manus.im for more")
    assert any(v.code == "brand.manus_link" and v.severity == "block" for v in vs)


def test_steady_lane_blocks() -> None:
    vs = check_text("Also check out Steady Lane by Morgan Ellis")
    assert any(v.code == "brand.side_catalog" and v.severity == "block" for v in vs)


def test_tip_jar_blocks() -> None:
    vs = check_text("Support my tip jar on Venmo")
    assert any(v.code == "brand.tip_jar" and v.severity == "block" for v in vs)


def test_pii_email_blocks() -> None:
    vs = check_text("Contact me at someone@example.com")
    assert any(v.code == "pii.email" and v.severity == "block" for v in vs)


# --- check_book intake ------------------------------------------------------

def test_intake_pass() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        s = _make_book(root)
        report = check_book(s, root / "books" / "test-book", scan_outputs=False)
        assert report.gate_passed, report.summary()
        assert report.ruleset_version == RULESET_VERSION


def test_intake_wrong_author_blocks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        s = _make_book(root, author="Somebody Else")
        report = check_book(s, root / "books" / "test-book", scan_outputs=False)
        assert not report.gate_passed
        assert any(v.code == "intake.author_mismatch" for v in report.blocks)


def test_intake_manus_in_brief_blocks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        s = _make_book(root)
        (root / "books" / "test-book" / "brief.md").write_text("Brief with a manus.im link inside it.")
        report = check_book(s, root / "books" / "test-book", scan_outputs=False)
        assert not report.gate_passed
        assert any(v.code == "brand.manus_link" for v in report.blocks)


# --- KDP metadata -----------------------------------------------------------

def test_kdp_valid_passes() -> None:
    s = new_state("b", "Test Book", "Sub", "vocabulary-reference-v1", "brief text long enough here")
    vs = check_kdp_metadata_file(VALID_KDP, s, "05-kdp-metadata.md")
    assert [v for v in vs if v.severity == "block"] == [], [v.code for v in vs]


def test_kdp_missing_ai_disclosure_blocks() -> None:
    s = new_state("b", "Test Book", "Sub", "vocabulary-reference-v1", "brief")
    text = VALID_KDP.replace(
        "Portions of this work were produced with generative AI assistance under direct\nhuman editorial supervision.",
        "No disclosure here.",
    )
    vs = check_kdp_metadata_file(text, s, "05-kdp-metadata.md")
    assert any(v.code == "kdp.ai_disclosure_missing" for v in vs)


def test_kdp_missing_keywords_blocks() -> None:
    s = new_state("b", "Test Book", "Sub", "vocabulary-reference-v1", "brief")
    text = VALID_KDP.replace("## Keywords\nGullah, Geechee, Lowcountry, Sea Islands, corridor\n", "")
    vs = check_kdp_metadata_file(text, s, "05-kdp-metadata.md")
    assert any(v.code == "kdp.keywords_insufficient" for v in vs)


def test_kdp_author_mismatch_blocks() -> None:
    s = new_state("b", "Test Book", "Sub", "vocabulary-reference-v1", "brief")
    text = VALID_KDP.replace("Author: Darryl Elliott Brown", "Author: Someone Else")
    vs = check_kdp_metadata_file(text, s, "05-kdp-metadata.md")
    assert any(v.code == "kdp.author_missing" for v in vs)


def test_kdp_placeholder_blocks() -> None:
    s = new_state("b", "Test Book", "Sub", "vocabulary-reference-v1", "brief")
    text = VALID_KDP + "\nTODO: finish this section\n"
    vs = check_kdp_metadata_file(text, s, "05-kdp-metadata.md")
    assert any(v.code == "kdp.placeholder" for v in vs)


def test_kdp_title_mismatch_blocks() -> None:
    s = new_state("b", "A Completely Different Title", "Sub", "vocabulary-reference-v1", "brief")
    vs = check_kdp_metadata_file(VALID_KDP, s, "05-kdp-metadata.md")
    assert any(v.code == "kdp.title_mismatch" for v in vs)


def test_full_book_with_valid_kdp_passes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        s = _make_book(root)
        (root / "books" / "test-book" / "05-kdp-metadata.md").write_text(VALID_KDP)
        report = check_book(s, root / "books" / "test-book", scan_outputs=True)
        assert report.gate_passed, report.summary()


# --- integration with state.books_ready_to_advance -------------------------

def test_books_ready_excludes_compliance_failures() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Good book, advanceable
        good = _make_book(root, book_id="good", title="Good Book")
        good["status"] = "Brief received"
        save_state(root, "good", good)
        # Bad book, advanceable status but wrong author
        bad = _make_book(root, book_id="bad", title="Bad Book", author="Wrong Name")
        bad["status"] = "Brief received"
        save_state(root, "bad", bad)

        ready = books_ready_to_advance(root)
        assert "good" in ready
        assert "bad" not in ready
        # The bad book should have been placed on hold.
        held = load_state(root, "bad")
        assert held["status"] == "Paused"
        assert held["current_stage"] == "compliance_hold"
        assert held["compliance"]["gate_passed"] is False


def test_enforce_or_hold_persists_and_holds() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        s = _make_book(root, author="Nope")
        s["status"] = "Brief received"
        save_state(root, "test-book", s)
        report = enforce_or_hold(root, "test-book", scan_outputs=False, apply=True, hold=True)
        assert not report.gate_passed
        held = load_state(root, "test-book")
        assert held["status"] == "Paused"
        assert held["compliance"]["ruleset_version"] == RULESET_VERSION


def test_is_advance_allowed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_book(root)
        assert is_advance_allowed(root, "test-book") is True
