"""Stage 4 (screenplay mode) — polish Act I as the review-ready sample.

Reads books/<id>/03-acts/act-1-*.md, sends it to the model with the
sample_chapter prompt (which asks for producer summary + narrator notes +
editor notes), writes the enriched version as 04-act-1-review.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from stage_common import load_context, fill_placeholders, set_status  # noqa: E402
from state import load_state, save_state, record_run, mark_error  # noqa: E402
from llm import call_llm  # noqa: E402


def run(books_root: Path, book_id: str) -> None:
    ctx = load_context(books_root, book_id, "sample_chapter")

    acts_dir = ctx.book_dir / "03-acts"
    act_1_files = list(acts_dir.glob("act-1-*.md"))
    if not act_1_files:
        mark_error(books_root, book_id, "Cannot polish sample: no Act I file found in 03-acts/")
        raise FileNotFoundError(f"No act-1-*.md in {acts_dir}")

    act_1_draft = act_1_files[0].read_text()

    set_status(books_root, book_id, "Sample chapter drafting", current_stage="sample")

    full_prompt = fill_placeholders(ctx.stage_prompt, {
        "TITLE": ctx.state.get("working_title", ""),
        "SUBTITLE": ctx.state.get("subtitle", ""),
    })
    full_prompt += f"\n\n---\n\nAct I draft to polish:\n\n{act_1_draft}"

    print(f"[sample] Polishing Act I via {ctx.model}")
    try:
        result = call_llm(full_prompt, model=ctx.model, system=ctx.system_prompt, max_tokens=14000)
    except Exception as e:
        mark_error(books_root, book_id, f"Sample stage failed: {e}")
        raise

    output_path = ctx.book_dir / "04-act-1-review.md"
    output_path.write_text(result.text)

    s = load_state(books_root, book_id)
    s["assets_generated"]["sample_chapter"] = str(output_path.relative_to(books_root))
    if "sample" not in s["stages_completed"]:
        s["stages_completed"].append("sample")
    s["status"] = "Sample chapter ready — awaiting review"
    save_state(books_root, book_id, s)

    record_run(
        books_root, book_id,
        stage="sample",
        model=result.model,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        status="success",
    )
    print(f"[sample] Wrote {output_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--books-root", required=True)
    parser.add_argument("--book-id", required=True)
    args = parser.parse_args()
    run(Path(args.books_root), args.book_id)


if __name__ == "__main__":
    main()
