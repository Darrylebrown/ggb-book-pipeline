"""Stage 06 — Generate all social assets in one run.

Produces four separate output files so review PRs stay focused:
  - 06-pins.md
  - 07-tiktok-script.md
  - 08-shorts-script.md
  - 09-substack-teaser.md

Uses different models per sub-stage to stay under Gemini Pro quota:
  - Pins:      Flash (varied, structural)
  - TikTok:    Groq Llama (fast headline variants)
  - Shorts:    Groq Llama (fast)
  - Substack:  Gemini Pro (long-form marketing copy)

If any single sub-stage fails, we log it and continue — the whole social bundle
should not block on one missing piece.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from stage_common import load_context, fill_placeholders, set_status  # noqa: E402
from state import load_state, save_state, record_run  # noqa: E402
from llm import call_llm  # noqa: E402


SUBSTAGES = [
    # (template_key, output_filename, assets_key, max_tokens)
    ("pins",      "06-pins.md",              "pins_doc",         4000),
    ("tiktok",    "07-tiktok-script.md",     "tiktok",           3000),
    ("shorts",    "08-shorts-script.md",     "shorts",           2500),
    ("substack",  "09-substack-teaser.md",   "substack",         5000),
]


def run(books_root: Path, book_id: str) -> None:
    set_status(books_root, book_id, "Social assets drafting", current_stage="social")

    for template_key, output_filename, assets_key, max_tokens in SUBSTAGES:
        ctx = load_context(books_root, book_id, template_key)
        full_prompt = fill_placeholders(ctx.stage_prompt, {
            "TITLE": ctx.state.get("working_title", ""),
            "SUBTITLE": ctx.state.get("subtitle", ""),
            "BRIEF": ctx.state.get("one_line_brief", ""),
        })

        print(f"[social:{template_key}] Calling {ctx.model}")
        try:
            result = call_llm(full_prompt, model=ctx.model, system=ctx.system_prompt, max_tokens=max_tokens)
        except Exception as e:
            print(f"[social:{template_key}] FAILED: {e}")
            record_run(
                books_root, book_id,
                stage=f"social_{template_key}",
                model=ctx.model,
                tokens_in=0,
                tokens_out=0,
                status="failed",
                error=str(e)[:200],
            )
            continue

        output_path = ctx.book_dir / output_filename
        output_path.write_text(result.text)

        s = load_state(books_root, book_id)
        s["assets_generated"][assets_key] = str(output_path.relative_to(books_root))
        save_state(books_root, book_id, s)

        record_run(
            books_root, book_id,
            stage=f"social_{template_key}",
            model=result.model,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            status="success",
        )
        print(f"[social:{template_key}] Wrote {output_filename} ({result.tokens_out} tokens)")

    # Advance to next stage
    s = load_state(books_root, book_id)
    if "social" not in s["stages_completed"]:
        s["stages_completed"].append("social")
    s["status"] = "ACX brief drafting"
    save_state(books_root, book_id, s)
    print("[social] All sub-stages complete → status=ACX brief drafting")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--books-root", required=True)
    parser.add_argument("--book-id", required=True)
    args = parser.parse_args()
    run(Path(args.books_root), args.book_id)


if __name__ == "__main__":
    main()
