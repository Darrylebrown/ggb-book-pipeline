"""Stage 01 — Generate the research dossier for a book.

Reads state.json for the book, loads the prompt template, calls the configured
model, saves `01-dossier.md`, updates state to "Dossier ready — awaiting review".

Usage:
    python scripts/stage_01_dossier.py --books-root ggb-books --book-id de-gullah-book
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from state import load_state, save_state, record_run, mark_error  # noqa: E402
from llm import call_llm  # noqa: E402


PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def run(books_root: Path, book_id: str) -> None:
    state = load_state(books_root, book_id)
    book_dir = books_root / "books" / book_id

    # Load prompt template
    template_path = PROMPTS_DIR / f"{state['prompt_template']}.yaml"
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
    template = yaml.safe_load(template_path.read_text())

    system_prompt = template["system_prompt"]
    stage_prompt = template["stages"]["dossier"]
    model = template["preferred_models"]["dossier"]

    # Fill placeholders
    full_prompt = (
        stage_prompt
        .replace("{{TITLE}}", state["working_title"])
        .replace("{{SUBTITLE}}", state["subtitle"])
        .replace("{{BRIEF}}", state["one_line_brief"])
    )

    # Move status → drafting
    state["status"] = "Dossier drafting"
    state["current_stage"] = "dossier"
    save_state(books_root, book_id, state)

    print(f"[dossier] Calling {model} for {book_id}...")
    try:
        result = call_llm(full_prompt, model=model, system=system_prompt, max_tokens=12000)
    except Exception as e:
        mark_error(books_root, book_id, f"Dossier stage failed: {e}")
        raise

    # Save output
    dossier_path = book_dir / "01-dossier.md"
    dossier_path.write_text(result.text)

    # Update state
    state = load_state(books_root, book_id)  # reload — mark_error may have modified
    state["assets_generated"]["dossier"] = str(dossier_path.relative_to(books_root))
    if "dossier" not in state["stages_completed"]:
        state["stages_completed"].append("dossier")
    state["status"] = "Dossier ready — awaiting review"
    save_state(books_root, book_id, state)

    record_run(
        books_root, book_id,
        stage="dossier",
        model=result.model,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        status="success",
    )
    print(f"[dossier] Wrote {dossier_path} ({result.tokens_out} tokens out)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate research dossier for a book.")
    parser.add_argument("--books-root", required=True)
    parser.add_argument("--book-id", required=True)
    args = parser.parse_args()
    run(Path(args.books_root), args.book_id)


if __name__ == "__main__":
    main()
