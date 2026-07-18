"""Stage 04 — Generate the full sample chapter.

Picks a section (default: 'De Watuh' — the pilot chose it) and writes it as a
publication-ready markdown chapter, including opener, entry formatting, and
closing reflection.

The section to use is read from `state.sample_section` if present; otherwise
falls back to 'De Watuh'.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from stage_common import load_context, fill_placeholders, set_status  # noqa: E402
from state import load_state, save_state, record_run, mark_error  # noqa: E402
from llm import call_llm  # noqa: E402


DEFAULT_SAMPLE_SECTION = "De Watuh"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def run(books_root: Path, book_id: str) -> None:
    ctx = load_context(books_root, book_id, "sample_chapter")

    section_name = ctx.state.get("sample_section") or DEFAULT_SAMPLE_SECTION
    entries_path = ctx.book_dir / "03-entries" / f"{slugify(section_name)}.json"
    if not entries_path.exists():
        mark_error(books_root, book_id, f"Cannot generate sample chapter: {entries_path} missing.")
        raise FileNotFoundError(entries_path)

    entries = json.loads(entries_path.read_text())
    entries_json_str = json.dumps(entries, indent=2, ensure_ascii=False)

    set_status(books_root, book_id, "Sample chapter drafting", current_stage="sample_chapter")

    full_prompt = fill_placeholders(ctx.stage_prompt, {
        "TITLE": ctx.state.get("working_title", ""),
        "SUBTITLE": ctx.state.get("subtitle", ""),
        "SECTION_NAME": section_name,
    })
    # Append the entries JSON so the model has real source data
    full_prompt += f"\n\nSection entries (source material):\n```json\n{entries_json_str}\n```"

    print(f"[sample_chapter] Calling {ctx.model} for section {section_name!r}")
    try:
        result = call_llm(full_prompt, model=ctx.model, system=ctx.system_prompt, max_tokens=12000)
    except Exception as e:
        mark_error(books_root, book_id, f"Sample chapter stage failed: {e}")
        raise

    output_path = ctx.book_dir / "04-sample-chapter.md"
    output_path.write_text(result.text)

    s = load_state(books_root, book_id)
    s["assets_generated"]["sample_chapter"] = str(output_path.relative_to(books_root))
    if "sample_chapter" not in s["stages_completed"]:
        s["stages_completed"].append("sample_chapter")
    s["status"] = "Sample chapter ready — awaiting review"
    save_state(books_root, book_id, s)

    record_run(
        books_root, book_id,
        stage="sample_chapter",
        model=result.model,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        status="success",
    )
    print(f"[sample_chapter] Wrote {output_path.name} ({result.tokens_out} tokens out)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--books-root", required=True)
    parser.add_argument("--book-id", required=True)
    args = parser.parse_args()
    run(Path(args.books_root), args.book_id)


if __name__ == "__main__":
    main()
