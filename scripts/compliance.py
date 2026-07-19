"""GGB compliance gate — ruleset v1.1.

Only compliant material may advance through the pipeline. A failing check
produces a *block*: the book is held (status ``Paused``, current_stage
``compliance_hold``) and is never allowed to advance silently.

Two layers of rules:

1. **GGB brand / ethics** — hard author + publisher strings, no forbidden
   links or framing (Manus, side catalog, tip jar, Hollywood/celebrity,
   true-crime sensationalism), no personal PII in public-facing material.
2. **KDP + Draft2Digital minimum** — when the relevant asset exists
   (``05-kdp-metadata.md``, ``11-rights-ip.md``, ``10-acx-brief.md``,
   sample chapter / manuscript), the asset must carry the fields KDP and
   Draft2Digital require before a title can be handed off.

Public API:
    check_text(text, path)                  -> list[Violation]
    check_book(state, book_dir, scan_outputs) -> ComplianceReport
    apply_report_to_state(state, report)    -> dict (mutated state)
    enforce_or_hold(books_root, book_id, ...) -> ComplianceReport
    is_advance_allowed(books_root, book_id) -> bool

CLI:
    python scripts/compliance.py --books-root <root> --book-id <id> \
        [--apply] [--hold] [--json] [--no-scan-outputs]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

RULESET_VERSION = "1.1"

# --- Brand constants (hard) -------------------------------------------------
EXPECTED_AUTHOR = "Darryl Elliott Brown"
EXPECTED_PUBLISHER = "Gullah Geechee Biz"

# --- Forbidden brand markers (block) ----------------------------------------
# Each entry: (regex, code, human detail). Case-insensitive.
FORBIDDEN_PATTERNS: list[tuple[str, str, str]] = [
    (r"\bmanus\b", "brand.manus_link", "Manus reference/link is not allowed in GGB materials."),
    (r"manus\.\w+", "brand.manus_link", "Manus link is not allowed in GGB materials."),
    (r"steady\s*lane", "brand.side_catalog", "Steady Lane side catalog must not be mixed into GGB titles."),
    (r"morgan\s*ellis", "brand.side_catalog", "Morgan Ellis side catalog must not be mixed into GGB titles."),
    (r"tip\s*jar", "brand.tip_jar", "Personal tip-jar framing is off-brand; use a culture-first soft CTA."),
    (r"\bvenmo\b|\bcashapp\b|cash\s*app|\bpaypal\.me\b", "brand.tip_jar", "Personal payment/tip solicitation is off-brand."),
    (r"red\s*carpet|a-?list\s+celebrit|hollywood\s+(blockbuster|glamour|star)", "brand.hollywood_frame",
     "Celebrity/Hollywood framing is not allowed in brand copy."),
    (r"true[-\s]?crime|blood[-\s]?soaked|massacre\s+thriller|killer['’]?s\s+tale", "brand.true_crime",
     "Sensational true-crime framing is not allowed (esp. Mother Emanuel packaging)."),
]

# --- PII patterns (block in public-facing materials) ------------------------
PII_PATTERNS: list[tuple[str, str, str]] = [
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "pii.email", "Personal email address present."),
    (r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "pii.phone", "Phone number present."),
    (r"\b\d{3}-\d{2}-\d{4}\b", "pii.ssn", "Social Security Number present."),
]

# --- Placeholder / unfinished markers (block in metadata) -------------------
PLACEHOLDER_PATTERNS: list[tuple[str, str]] = [
    (r"lorem\s+ipsum", "lorem ipsum"),
    (r"\bTODO\b", "TODO"),
    (r"\bTBD\b", "TBD"),
    (r"\[INSERT[^\]]*\]", "[INSERT ...]"),
    (r"\bFIXME\b", "FIXME"),
    (r"\bXXX\b", "XXX placeholder"),
]

# --- Content-safety markers for KDP/D2D (block) -----------------------------
CONTENT_SAFETY_PATTERNS: list[tuple[str, str, str]] = [
    (r"guaranteed\s+(?:sales|income|bestseller|profit|return)|price\s+guarantee|money[-\s]?back\s+guarantee",
     "safety.price_guarantee", "Price/earnings guarantees are not permitted in KDP metadata."),
    (r"\bcures?\b.{0,20}\b(cancer|disease|illness|covid)|miracle\s+cure|guaranteed\s+cure",
     "safety.medical_claim", "Medical cure claims are not permitted."),
    (r"\b(?:kike|spic|wetback|coon)\b", "safety.hate_speech", "Hate-speech marker present."),
]

# Mock-dialect heuristic: only warn (scholarly framing is fine and hard to
# distinguish automatically).
SCHOLARLY_FRAME_MARKERS = (
    "gullah", "creole", "linguist", "vocabulary", "lexicon", "language",
    "scholar", "turner", "mufwene", "dialect study", "orthograph",
)


@dataclass
class Violation:
    code: str
    severity: str  # "block" | "warn"
    detail: str
    path: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ComplianceReport:
    gate_passed: bool = True
    ruleset_version: str = RULESET_VERSION
    checked_at: str = ""
    violations: list[Violation] = field(default_factory=list)

    def add(self, v: Violation) -> None:
        self.violations.append(v)
        if v.severity == "block":
            self.gate_passed = False

    @property
    def blocks(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == "block"]

    @property
    def warnings(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == "warn"]

    def summary(self) -> str:
        if self.gate_passed:
            n = len(self.warnings)
            return f"PASS (ruleset {self.ruleset_version}), {n} warning(s)"
        codes = ", ".join(sorted({v.code for v in self.blocks}))
        return f"BLOCKED (ruleset {self.ruleset_version}): {codes}"

    def to_dict(self) -> dict:
        return {
            "gate_passed": self.gate_passed,
            "ruleset_version": self.ruleset_version,
            "checked_at": self.checked_at,
            "violations": [v.to_dict() for v in self.violations],
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Text-level scanning (brand + PII), reusable for any asset
# ---------------------------------------------------------------------------

def check_text(text: str, path: str = "") -> list[Violation]:
    """Scan arbitrary text for forbidden brand markers and PII. Blocks only."""
    out: list[Violation] = []
    if not text:
        return out
    low = text.lower()

    for pattern, code, detail in FORBIDDEN_PATTERNS:
        if re.search(pattern, low):
            out.append(Violation(code=code, severity="block", detail=detail, path=path))

    for pattern, code, detail in PII_PATTERNS:
        if re.search(pattern, text):
            out.append(Violation(code=code, severity="block", detail=detail, path=path))

    # Mock dialect: warn only, and only if no scholarly framing is nearby.
    if re.search(r"\b(y'?all|gwine|dey|dat|dese|nuff)\b", low):
        if not any(m in low for m in SCHOLARLY_FRAME_MARKERS):
            out.append(Violation(
                code="brand.mock_dialect",
                severity="warn",
                detail="Possible mock dialect without scholarly framing — review for cultural framing.",
                path=path,
            ))
    return out


def _dedupe(violations: list[Violation]) -> list[Violation]:
    seen: set[tuple[str, str, str]] = set()
    out: list[Violation] = []
    for v in violations:
        key = (v.code, v.severity, v.path)
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def _has_placeholder(text: str) -> Optional[str]:
    for pattern, label in PLACEHOLDER_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return label
    return None


def _has_ai_disclosure(low: str) -> bool:
    """True if text carries real AI-disclosure phrasing (not just a heading)."""
    subject = re.search(r"generativ|ai[-\s]?generat|artificial intelligence|ai\s+assist", low)
    context = re.search(r"assist|supervis|editorial|human", low)
    return bool(subject and context)


def _content_safety(text: str, path: str) -> list[Violation]:
    out: list[Violation] = []
    for pattern, code, detail in CONTENT_SAFETY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            out.append(Violation(code=code, severity="block", detail=detail, path=path))
    return out


def _section_body(text: str, *markers: str) -> str:
    """Return the text following any of the given section markers up to the
    next markdown heading. Used to size Description/Blurb sections."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        low = line.lower()
        if any(m in low for m in markers):
            body: list[str] = []
            for nxt in lines[i + 1:]:
                if nxt.lstrip().startswith("#"):
                    break
                body.append(nxt)
            joined = "\n".join(body).strip()
            # If nothing followed on subsequent lines, maybe it's inline
            # (e.g. "Description: ...").
            if not joined:
                for m in markers:
                    idx = low.find(m)
                    if idx != -1:
                        joined = line[idx + len(m):].lstrip(" :\t")
            if joined:
                return joined
    return ""


# ---------------------------------------------------------------------------
# Asset-specific checks
# ---------------------------------------------------------------------------

def check_kdp_metadata_file(text: str, state: dict, path: str) -> list[Violation]:
    """KDP + Draft2Digital minimum checks for 05-kdp-metadata.md."""
    out: list[Violation] = []
    low = text.lower()

    def block(code: str, detail: str) -> None:
        out.append(Violation(code=code, severity="block", detail=detail, path=path))

    # Title match
    working_title = (state.get("working_title") or "").strip()
    if working_title and working_title.lower() not in low:
        block("kdp.title_mismatch",
              f"KDP metadata does not mention working title {working_title!r}.")

    # Author + publisher
    if EXPECTED_AUTHOR.lower() not in low:
        block("kdp.author_missing", f"KDP metadata must credit author {EXPECTED_AUTHOR!r}.")
    if EXPECTED_PUBLISHER.lower() not in low:
        block("kdp.publisher_missing", f"KDP metadata must name publisher {EXPECTED_PUBLISHER!r}.")

    # Description present + reasonable length
    desc = _section_body(text, "description", "book description", "blurb")
    if len(desc) < 100:
        block("kdp.description_thin",
              "KDP description/blurb missing or under 100 characters.")

    # Keywords: a Keywords section with >= 3 items
    kw_body = _section_body(text, "keywords", "search keywords")
    kw_items = [k for k in re.split(r"[,\n;]|^\s*[-*]\s*", kw_body, flags=re.MULTILINE) if k.strip()]
    if "keyword" not in low or len(kw_items) < 3:
        block("kdp.keywords_insufficient",
              "KDP requires a Keywords section with at least 3 keyword items.")

    # Categories / BISAC present
    if not re.search(r"categor|bisac", low):
        block("kdp.categories_missing", "KDP metadata must list at least one category / BISAC code.")

    # AI disclosure — require real disclosure phrasing, not just a heading.
    if not _has_ai_disclosure(low):
        block("kdp.ai_disclosure_missing",
              "KDP AI-content disclosure language is required (generative AI under human editorial supervision).")

    # Draft2Digital friendliness
    if not re.search(r"draft2digital|\bd2d\b|human\s+edit|documentation", low):
        block("d2d.notes_missing",
              "Draft2Digital note missing — mention human editing/documentation or a D2D imprint section.")

    # Placeholders
    ph = _has_placeholder(text)
    if ph:
        block("kdp.placeholder", f"Placeholder text left in metadata: {ph}.")

    # Content safety
    out.extend(_content_safety(text, path))

    # Cover/title contradiction
    cover = _section_body(text, "cover")
    if cover and working_title:
        # Only flag if a cover *title* line clearly names a different title.
        m = re.search(r"title[:\s]+(.+)", cover, re.IGNORECASE)
        if m and working_title.lower() not in m.group(1).lower():
            out.append(Violation(
                code="kdp.cover_title_mismatch", severity="warn",
                detail="Cover section references a title that differs from working_title.",
                path=path,
            ))
    return out


def check_rights_file(text: str, state: dict, path: str) -> list[Violation]:
    """Checks for 11-rights-ip.md."""
    out: list[Violation] = []
    low = text.lower()

    def block(code: str, detail: str) -> None:
        out.append(Violation(code=code, severity="block", detail=detail, path=path))

    if not _has_ai_disclosure(low):
        block("rights.ai_disclosure_missing", "Rights & IP doc must contain AI disclosure language.")
    if not re.search(r"copyright|©|\(c\)|all rights reserved", low):
        block("rights.copyright_missing", "Rights & IP doc must contain copyright / rights language.")
    if EXPECTED_AUTHOR.lower() not in low:
        block("rights.author_missing", f"Rights & IP doc must credit {EXPECTED_AUTHOR!r}.")
    if EXPECTED_PUBLISHER.lower() not in low:
        block("rights.publisher_missing", f"Rights & IP doc must name {EXPECTED_PUBLISHER!r}.")
    return out


def check_acx_file(text: str, state: dict, path: str) -> list[Violation]:
    """Checks for 10-acx-brief.md."""
    out: list[Violation] = []
    low = text.lower()

    def block(code: str, detail: str) -> None:
        out.append(Violation(code=code, severity="block", detail=detail, path=path))

    if EXPECTED_AUTHOR.lower() not in low:
        block("acx.author_missing", f"ACX brief must credit author {EXPECTED_AUTHOR!r}.")
    if EXPECTED_PUBLISHER.lower() not in low:
        block("acx.publisher_missing", f"ACX brief must name publisher {EXPECTED_PUBLISHER!r}.")
    if not re.search(r"narrat", low):
        block("acx.narrator_missing", "ACX brief must include narrator direction.")
    return out


# ---------------------------------------------------------------------------
# Book-level orchestration
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def check_book(state: dict, book_dir: Path, scan_outputs: bool = True) -> ComplianceReport:
    """Run the full ruleset for a single book.

    ``scan_outputs=False`` runs only the lightweight always-on intake checks
    (author/publisher strings, working title, brief presence + brand scan of
    the brief). ``scan_outputs=True`` additionally scans all generated assets
    and applies the asset-specific KDP/D2D/rights/ACX checks.
    """
    report = ComplianceReport(checked_at=_now_iso())

    # --- Always: identity strings ---
    author = (state.get("author") or "").strip()
    publisher = (state.get("publisher") or "").strip()
    if author != EXPECTED_AUTHOR:
        report.add(Violation("intake.author_mismatch", "block",
                             f"Author must be {EXPECTED_AUTHOR!r}, got {author!r}.", "state.json"))
    if publisher != EXPECTED_PUBLISHER:
        report.add(Violation("intake.publisher_mismatch", "block",
                             f"Publisher must be {EXPECTED_PUBLISHER!r}, got {publisher!r}.", "state.json"))

    # --- Always: working title present ---
    if not (state.get("working_title") or "").strip():
        report.add(Violation("intake.title_missing", "block",
                             "Working title is missing.", "state.json"))

    # --- Always: brief present and not thin ---
    brief_path = book_dir / "brief.md"
    brief_text = _read(brief_path)
    one_liner = (state.get("one_line_brief") or "").strip()
    if not brief_text and not one_liner:
        report.add(Violation("intake.brief_missing", "block",
                             "brief.md is missing and one_line_brief is empty.", "brief.md"))
    elif len((brief_text + " " + one_liner).strip()) < 40:
        report.add(Violation("intake.brief_thin", "block",
                             "Brief is too thin (< 40 chars).", "brief.md"))

    # --- Always: brand scan of intake text ---
    for v in check_text(brief_text + "\n" + one_liner, path="brief.md"):
        report.add(v)

    if not scan_outputs:
        report.violations = _dedupe(report.violations)
        return report

    # --- Output scan: every markdown asset gets a brand/PII scan ---
    md_files = sorted(book_dir.rglob("*.md")) if book_dir.exists() else []
    for md in md_files:
        rel = md.name
        text = _read(md)
        for v in check_text(text, path=rel):
            report.add(v)

    # --- Asset-specific KDP/D2D/rights/ACX checks ---
    kdp = book_dir / "05-kdp-metadata.md"
    if kdp.exists():
        for v in check_kdp_metadata_file(_read(kdp), state, "05-kdp-metadata.md"):
            report.add(v)

    rights = book_dir / "11-rights-ip.md"
    if rights.exists():
        for v in check_rights_file(_read(rights), state, "11-rights-ip.md"):
            report.add(v)

    acx = book_dir / "10-acx-brief.md"
    if acx.exists():
        for v in check_acx_file(_read(acx), state, "10-acx-brief.md"):
            report.add(v)

    report.violations = _dedupe(report.violations)
    # Recompute gate_passed after dedupe.
    report.gate_passed = not any(v.severity == "block" for v in report.violations)
    return report


# ---------------------------------------------------------------------------
# State integration
# ---------------------------------------------------------------------------

def apply_report_to_state(state: dict, report: ComplianceReport) -> dict:
    """Persist the compliance report into state['compliance']. Mutates + returns."""
    state["compliance"] = report.to_dict()
    return state


def enforce_or_hold(
    books_root: Path,
    book_id: str,
    scan_outputs: bool = True,
    apply: bool = True,
    hold: bool = True,
) -> ComplianceReport:
    """Check a book and, on failure, place it on compliance hold.

    - Always writes ``state['compliance']`` when ``apply`` is True.
    - On block with ``hold`` True: status -> ``Paused``,
      current_stage -> ``compliance_hold``, last_error summarizes blocks.
    """
    from state import load_state, save_state  # local import to avoid cycles

    state = load_state(books_root, book_id)
    book_dir = books_root / "books" / book_id
    report = check_book(state, book_dir, scan_outputs=scan_outputs)

    if apply:
        apply_report_to_state(state, report)
        if not report.gate_passed and hold:
            state["status"] = "Paused"
            state["current_stage"] = "compliance_hold"
            state["last_error"] = "Compliance hold — " + report.summary()
        save_state(books_root, book_id, state)

    return report


def is_advance_allowed(books_root: Path, book_id: str, scan_outputs: bool = False) -> bool:
    """Lightweight gate check used by the dispatcher. Does not mutate state."""
    from state import load_state

    state = load_state(books_root, book_id)
    book_dir = books_root / "books" / book_id
    return check_book(state, book_dir, scan_outputs=scan_outputs).gate_passed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="GGB compliance gate (ruleset v%s)." % RULESET_VERSION)
    parser.add_argument("--books-root", required=True)
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--apply", action="store_true", help="Persist state['compliance'].")
    parser.add_argument("--hold", action="store_true", help="On failure, set Paused/compliance_hold.")
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    parser.add_argument("--no-scan-outputs", action="store_true",
                        help="Intake-only check (skip generated asset scan).")
    args = parser.parse_args(argv)

    books_root = Path(args.books_root)
    scan_outputs = not args.no_scan_outputs

    if args.apply or args.hold:
        report = enforce_or_hold(
            books_root, args.book_id,
            scan_outputs=scan_outputs, apply=True, hold=args.hold,
        )
    else:
        from state import load_state
        state = load_state(books_root, args.book_id)
        book_dir = books_root / "books" / args.book_id
        report = check_book(state, book_dir, scan_outputs=scan_outputs)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"[compliance] {args.book_id}: {report.summary()}")
        for v in report.violations:
            print(f"  [{v.severity}] {v.code} ({v.path}): {v.detail}")

    return 0 if report.gate_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
