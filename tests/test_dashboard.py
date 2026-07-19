"""Dashboard renderer tests."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from state import new_state, save_state, AUTHOR, PUBLISHER  # noqa: E402
from build_dashboard import (  # noqa: E402
    build_dashboard,
    build_free_stack,
    render_book_card,
    STATUS_PROGRESS,
    compliance_summary,
    FREE_STACK_LAYERS,
)
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


def test_compliance_summary_unknown_when_missing():
    s = new_state("b", "T", "S", "vocabulary-reference-v1", "brief text here", 10)
    summary = compliance_summary(s)
    assert summary["gate"] == "UNKNOWN"
    assert summary["ruleset_version"] == "—"
    assert summary["checked_at"] == "never"
    assert summary["author"] == AUTHOR


def test_compliance_summary_pass_and_hold():
    s = new_state("b", "T", "S", "vocabulary-reference-v1", "brief text here", 10)
    s["compliance"] = {"gate_passed": True, "ruleset_version": "1.1.1",
                       "checked_at": "2026-07-19T12:00:00+00:00", "violations": []}
    passed = compliance_summary(s)
    assert passed["gate"] == "PASS"
    assert passed["ruleset_version"] == "1.1.1"
    assert "2026-07-19 12:00:00 UTC" == passed["checked_at"]

    s["compliance"]["gate_passed"] = False
    assert compliance_summary(s)["gate"] == "HOLD"


def test_dashboard_renders_compliance_without_crashing_when_missing(tmp_path):
    # No compliance block at all — must still render and show UNKNOWN.
    s = new_state("book-x", "Book X", "Sub", "vocabulary-reference-v1", "A brief long enough", 100)
    save_state(tmp_path, "book-x", s)
    html = build_dashboard(tmp_path, "Darrylebrown/ggb-books")
    assert "Compliance: UNKNOWN" in html
    assert "Attribution: OK" in html
    assert "Compliance holds" in html


def test_dashboard_shows_hold_and_attribution_drift(tmp_path):
    s = new_state("book-y", "Book Y", "Sub", "vocabulary-reference-v1", "A brief long enough", 100)
    s["author"] = "Impostor"
    s["compliance"] = {"gate_passed": False, "ruleset_version": "1.1.1",
                       "checked_at": "2026-07-19T12:00:00+00:00", "violations": []}
    save_state(tmp_path, "book-y", s)
    html = build_dashboard(tmp_path, "Darrylebrown/ggb-books")
    assert "Compliance: HOLD" in html
    assert "Attribution: DRIFT" in html


def test_render_book_card_escapes_html():
    from state import new_state as _ns
    s = _ns("evil-book", "<script>alert(1)</script>", "sub", "vocabulary-reference-v1", "brief", 10)
    card = render_book_card("evil-book", s, "owner/repo")
    assert "<script>alert(1)</script>" not in card
    assert "&lt;script&gt;" in card


# --- Free Stack Map --------------------------------------------------------

def test_dashboard_has_nav_to_free_stack(tmp_path):
    html = build_dashboard(tmp_path, "test/repo")
    assert 'href="free-stack.html"' in html
    assert 'href="index.html"' in html


def test_free_stack_empty_does_not_crash(tmp_path):
    # No books at all — must still render the map.
    html = build_free_stack(tmp_path, "test/repo")
    assert "Free Stack Map" in html
    assert "LOCKED ops standard" in html
    assert "Dare to be great on free rails" in html
    # Nav back to the book status page.
    assert 'href="index.html"' in html


def test_free_stack_has_credits_and_all_layers(tmp_path):
    html = build_free_stack(tmp_path, "Darrylebrown/ggb-books")
    # Hardwired credits appear.
    assert AUTHOR in html
    assert PUBLISHER in html
    # Every stack layer is rendered.
    for layer, *_ in FREE_STACK_LAYERS:
        assert layer in html
    # Selection rules + the multi-lane pin note (documented, not fake counts).
    assert "Selection rules" in html
    assert "180" in html and "500" in html
    assert "multi-lane" in html.lower()


def test_free_stack_kpis_reflect_book_state(tmp_path):
    s1 = new_state("book-a", "Book A", "Sub A", "vocabulary-reference-v1", "A brief long enough", 100)
    s1["compliance"] = {"gate_passed": False, "ruleset_version": "1.1.1",
                        "checked_at": "2026-07-19T12:00:00+00:00", "violations": []}
    save_state(tmp_path, "book-a", s1)

    s2 = new_state("book-b", "Book B", "Sub B", "vocabulary-reference-v1", "A brief long enough", 100)
    s2["author"] = "Impostor"
    save_state(tmp_path, "book-b", s2)

    html = build_free_stack(tmp_path, "Darrylebrown/ggb-books")
    assert "Books in pipeline" in html
    assert "Compliance holds" in html
    assert "Attribution OK" in html
    # 2 books total, 1 with correct attribution.
    assert "1 / 2" in html


def test_free_stack_escapes_repo_input(tmp_path):
    # books_repo flows into href attributes; ensure the map still builds.
    html = build_free_stack(tmp_path, "owner/repo")
    assert "owner/repo" in html
    assert "$0" in html
