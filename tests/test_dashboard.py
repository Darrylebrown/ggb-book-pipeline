"""Dashboard renderer tests."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from state import new_state, save_state  # noqa: E402
from build_dashboard import build_dashboard, render_book_card, STATUS_PROGRESS  # noqa: E402
from state import STATUSES  # noqa: E402


def test_all_statuses_have_progress_mapping():
    for status in STATUSES:
        assert status in STATUS_PROGRESS, f"Status {status!r} missing from STATUS_PROGRESS"


def test_empty_dashboard(tmp_path):
    html = build_dashboard(tmp_path, "test/repo")
    assert "<title>GGB Book Pipeline" in html
    assert "No books yet" in html


def test_dashboard_with_books(tmp_path):
    s1 = new_state("book-a", "Book A", "Sub A", "vocabulary-reference-v1", "Brief A", 100)
    s1["status"] = "Dossier ready — awaiting review"
    s1["assets_generated"]["entries_count"] = 0
    save_state(tmp_path, "book-a", s1)

    s2 = new_state("book-b", "Book B", "Sub B", "vocabulary-reference-v1", "Brief B", 200)
    s2["status"] = "Ready for KDP handoff"
    s2["stages_completed"] = ["dossier", "structure", "entries", "sample_chapter", "kdp_metadata", "social", "acx_brief", "rights_ip", "assemble"]
    s2["assets_generated"]["entries_count"] = 200
    s2["assets_generated"]["final_kit"] = "books/book-b/final-kit.zip"
    save_state(tmp_path, "book-b", s2)

    html = build_dashboard(tmp_path, "Darrylebrown/ggb-books")

    # Both books appear
    assert "Book A" in html
    assert "Book B" in html
    # Status pills render
    assert "Dossier ready" in html
    assert "Ready for KDP handoff" in html
    # KPIs reflect the state (1 in-review, 1 done)
    assert "book-a" in html
    assert "book-b" in html
    # Final-kit link appears for the ready book
    assert "final-kit.zip" in html


def test_render_book_card_escapes_html():
    from state import new_state as _ns
    s = _ns("evil-book", "<script>alert(1)</script>", "sub", "vocabulary-reference-v1", "brief", 10)
    card = render_book_card("evil-book", s, "owner/repo")
    assert "<script>alert(1)</script>" not in card
    assert "&lt;script&gt;" in card
