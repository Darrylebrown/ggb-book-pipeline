"""Stage 03 — Generate vocabulary entries in batches, one section at a time.

Reads the 10-section structure produced in Stage 2, extracts section names and
target headword counts, then batches Gemini calls (5 entries per call) until the
target is met.

Outputs one JSON file per section under `books/<book>/03-entries/`.
Updates `assets_generated.entries_count` as it goes so the cron can resume
mid-batch if it gets rate-limited.

Rate-limit strategy: Gemini 2.0 Pro is 50 requests/day. For a 370-headword book
at 5 entries/call, that's 74 calls — more than 1 day of quota. The stage is
DESIGNED to resume across cron ticks: it re-runs the same stage_03 script on
each 30-min tick until entry_count_target is reached, then transitions status.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from stage_common import load_context, fill_placeholders, set_status  # noqa: E402
from state import load_state, save_state, record_run, mark_error  # noqa: E402
from llm import call_llm  # noqa: E402


ENTRIES_PER_BATCH = 5
MAX_BATCHES_PER_RUN = 8  # cap so one cron tick stays under 15 min

# Canonical 10 sections for the vocabulary reference template.
# If the AI structure doc deviates, we fall back to this list.
CANONICAL_SECTIONS = [
    ("De Land", 37),
    ("De Watuh", 37),
    ("De People", 37),
    ("De Fiah De Pot", 37),
    ("De Praise", 37),
    ("De Wuk", 37),
    ("De Talk", 37),
    ("De Story", 37),
    ("De Chirren Lern", 37),
    ("De Provuhbs", 37),
]


def parse_sections_from_structure(structure_md: str, total_target: int) -> list[tuple[str, int]]:
    """Extract (section_name, target_count) pairs from the AI-generated structure doc.

    Falls back to CANONICAL_SECTIONS proportionally scaled to total_target if
    parsing fails.
    """
    # Pattern: look for "## <n>. <Section Name>" or "### <Section Name>" with a "target: N" hint
    pattern = re.compile(
        r"(?:^|\n)#+\s*\d*\.?\s*(De\s+[A-Z][\w\s]+?)(?:\s+—\s+.*?)?\n"
        r"[\s\S]*?(?:target(?:\s+headword)?\s*(?:count)?[:\s]+(\d+))",
        re.IGNORECASE,
    )
    matches = pattern.findall(structure_md)
    if len(matches) >= 8:
        return [(name.strip(), int(count)) for name, count in matches]

    # Fallback: canonical list, proportionally scaled
    total_default = sum(c for _, c in CANONICAL_SECTIONS)
    scale = total_target / total_default if total_default else 1.0
    return [(name, max(1, round(count * scale))) for name, count in CANONICAL_SECTIONS]


def load_existing_entries(section_dir: Path, section_slug: str) -> list[dict]:
    path = section_dir / f"{section_slug}.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return []


def save_entries(section_dir: Path, section_slug: str, entries: list[dict]) -> None:
    section_dir.mkdir(parents=True, exist_ok=True)
    path = section_dir / f"{section_slug}.json"
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False))


def parse_llm_json_array(text: str) -> list[dict]:
    """Extract a JSON array from LLM output. Tolerates markdown code fences and prose."""
    # Strip code fences
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    # Find the first [ ... ] JSON array in the text
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON array found in LLM output. First 200 chars: {text[:200]!r}")
    return json.loads(text[start:end + 1])


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def run(books_root: Path, book_id: str) -> None:
    ctx = load_context(books_root, book_id, "entries")
    total_target = ctx.state.get("entry_count_target", 370)

    structure_path = ctx.book_dir / "02-structure.md"
    if not structure_path.exists():
        mark_error(books_root, book_id, "Cannot generate entries: 02-structure.md missing.")
        raise FileNotFoundError(structure_path)

    structure_md = structure_path.read_text()
    sections = parse_sections_from_structure(structure_md, total_target)
    entries_dir = ctx.book_dir / "03-entries"

    set_status(books_root, book_id, "Entries generating", current_stage="entries")

    batches_this_run = 0
    total_entries_across_book = 0

    for section_name, section_target in sections:
        if batches_this_run >= MAX_BATCHES_PER_RUN:
            print(f"[entries] Hit MAX_BATCHES_PER_RUN ({MAX_BATCHES_PER_RUN}) — will resume next tick.")
            break

        section_slug = slugify(section_name)
        existing = load_existing_entries(entries_dir, section_slug)
        total_entries_across_book += len(existing)

        while len(existing) < section_target and batches_this_run < MAX_BATCHES_PER_RUN:
            batch_size = min(ENTRIES_PER_BATCH, section_target - len(existing))
            existing_headwords = ", ".join(e.get("headword", "") for e in existing) or "(none yet)"

            full_prompt = fill_placeholders(ctx.stage_prompt, {
                "TITLE": ctx.state.get("working_title", ""),
                "SUBTITLE": ctx.state.get("subtitle", ""),
                "BATCH_SIZE": str(batch_size),
                "SECTION_NAME": section_name,
                "EXISTING_HEADWORDS": existing_headwords,
            })

            print(f"[entries] {section_name}: {len(existing)}/{section_target} — batch of {batch_size}")
            try:
                result = call_llm(full_prompt, model=ctx.model, system=ctx.system_prompt, max_tokens=6000)
            except Exception as e:
                mark_error(books_root, book_id, f"Entries stage failed on {section_name}: {e}")
                raise

            try:
                new_entries = parse_llm_json_array(result.text)
            except ValueError as e:
                print(f"[entries] {section_name}: JSON parse failed, skipping batch. {e}")
                # Log a failed run but don't kill the whole stage
                record_run(
                    books_root, book_id,
                    stage="entries",
                    model=result.model,
                    tokens_in=result.tokens_in,
                    tokens_out=result.tokens_out,
                    status="parse_error",
                    error=str(e)[:200],
                )
                batches_this_run += 1
                continue

            # Attach section metadata to each entry
            for e in new_entries:
                if isinstance(e, dict):
                    e.setdefault("section", section_name)
                    e.setdefault("status", "Draft")

            existing.extend(new_entries)
            save_entries(entries_dir, section_slug, existing)
            total_entries_across_book += len(new_entries)

            record_run(
                books_root, book_id,
                stage="entries",
                model=result.model,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                status="success",
            )

            # Update state.assets_generated.entries_count
            s = load_state(books_root, book_id)
            s["assets_generated"]["entries_count"] = total_entries_across_book
            save_state(books_root, book_id, s)

            batches_this_run += 1

    # Are we done?
    final_count = 0
    for section_name, _ in sections:
        final_count += len(load_existing_entries(entries_dir, slugify(section_name)))

    s = load_state(books_root, book_id)
    s["assets_generated"]["entries_count"] = final_count
    if final_count >= total_target:
        s["status"] = "Entries ready — awaiting review"
        if "entries" not in s["stages_completed"]:
            s["stages_completed"].append("entries")
        print(f"[entries] Target met: {final_count}/{total_target}. Status → Entries ready — awaiting review.")
    else:
        # Stay in "Entries generating" so the next cron tick picks us up
        print(f"[entries] Progress: {final_count}/{total_target}. Will resume next tick.")
    save_state(books_root, book_id, s)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--books-root", required=True)
    parser.add_argument("--book-id", required=True)
    args = parser.parse_args()
    run(Path(args.books_root), args.book_id)


if __name__ == "__main__":
    main()
