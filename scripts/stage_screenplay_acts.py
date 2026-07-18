"""Stage 3 (screenplay mode) — generate the 5 Acts, one per cron tick.

Reads the 5-act structure from Stage 2, then iterates writing each Act as its
own markdown file. Resumes across cron ticks — one Act per invocation to stay
under Gemini's 50-request/day cap and leave headroom for other stages.

Outputs:
  books/<id>/03-acts/act-1-{slug}.md
  books/<id>/03-acts/act-2-{slug}.md
  ...
  books/<id>/03-acts/act-5-{slug}.md

Status transitions:
  Structure ready — awaiting review → Entries generating (on first call)
  Entries generating → stays until all 5 Acts done
  After Act 5 → Entries ready — awaiting review
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from stage_common import load_context, fill_placeholders, set_status  # noqa: E402
from state import load_state, save_state, record_run, mark_error  # noqa: E402
from llm import call_llm  # noqa: E402


MAX_ACTS_PER_RUN = 1  # one Act per cron tick — quality + quota

# Fallback Act titles if structure parse fails
DEFAULT_ACTS = [
    ("Beginning", 15),
    ("Rising Action", 20),
    ("Defining Moment", 25),
    ("Rebuilding", 25),
    ("Legacy", 15),
]


def parse_acts_from_structure(structure_md: str) -> list[tuple[str, int]]:
    """Extract (act_title, runtime_min) from the Stage 2 structure doc.

    Looks for lines like: `## ACT I — Beaufort Born` and `Runtime: 15 min`
    or `~15 min`.

    Returns exactly 5 acts. Falls back to DEFAULT_ACTS if parse yields <5.
    """
    # Match `## ACT I — Title` or `## ACT 1 — Title` or `# ACT I: Title`
    pattern = re.compile(
        r"#+\s*ACT\s+([IVX0-9]+)\s*[—:–\-]\s*([^\n]+?)\s*\n"
        r"(?:[\s\S]*?(?:runtime|~)\s*[:\s]*?(\d+)\s*(?:min|minute))?",
        re.IGNORECASE,
    )
    matches = pattern.findall(structure_md)
    acts: list[tuple[str, int]] = []
    for _roman, title, runtime in matches:
        title = title.strip().strip("*").strip('"').strip()
        rt = int(runtime) if runtime else 20
        acts.append((title, rt))
        if len(acts) == 5:
            break

    if len(acts) < 5:
        return DEFAULT_ACTS
    return acts


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]


def act_number_word(n: int) -> str:
    return {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}.get(n, str(n))


def run(books_root: Path, book_id: str) -> None:
    ctx = load_context(books_root, book_id, "entries")

    structure_path = ctx.book_dir / "02-structure.md"
    if not structure_path.exists():
        mark_error(books_root, book_id, "Cannot generate Acts: 02-structure.md missing.")
        raise FileNotFoundError(structure_path)

    acts = parse_acts_from_structure(structure_path.read_text())
    acts_dir = ctx.book_dir / "03-acts"
    acts_dir.mkdir(parents=True, exist_ok=True)

    set_status(books_root, book_id, "Entries generating", current_stage="acts")

    acts_this_run = 0
    for i, (act_title, runtime) in enumerate(acts, start=1):
        if acts_this_run >= MAX_ACTS_PER_RUN:
            print(f"[acts] Hit MAX_ACTS_PER_RUN — will resume next tick.")
            break

        act_path = acts_dir / f"act-{i}-{slugify(act_title)}.md"
        if act_path.exists() and act_path.stat().st_size > 500:
            print(f"[acts] Act {i} '{act_title}' already exists — skipping.")
            continue

        print(f"[acts] Generating Act {i} '{act_title}' ({runtime} min)")
        full_prompt = fill_placeholders(ctx.stage_prompt, {
            "TITLE": ctx.state.get("working_title", ""),
            "SUBTITLE": ctx.state.get("subtitle", ""),
            "ACT_NUMBER": act_number_word(i),
            "ACT_TITLE": act_title,
            "ACT_RUNTIME": str(runtime),
        })

        try:
            result = call_llm(full_prompt, model=ctx.model, system=ctx.system_prompt, max_tokens=12000)
        except Exception as e:
            mark_error(books_root, book_id, f"Act {i} generation failed: {e}")
            raise

        act_path.write_text(result.text)
        record_run(
            books_root, book_id,
            stage=f"act_{i}",
            model=result.model,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            status="success",
        )

        s = load_state(books_root, book_id)
        s["assets_generated"]["entries_count"] = i  # Reuse this counter (1-5 for screenplay)
        save_state(books_root, book_id, s)
        acts_this_run += 1

    # Are all 5 done?
    completed = sum(1 for i in range(1, 6)
                    if any(acts_dir.glob(f"act-{i}-*.md")))

    s = load_state(books_root, book_id)
    s["assets_generated"]["entries_count"] = completed
    if completed >= 5:
        s["status"] = "Entries ready — awaiting review"
        if "acts" not in s["stages_completed"]:
            s["stages_completed"].append("acts")
        print(f"[acts] All 5 Acts complete → Entries ready — awaiting review")
    else:
        print(f"[acts] Progress: {completed}/5 Acts. Resume next tick.")
    save_state(books_root, book_id, s)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--books-root", required=True)
    parser.add_argument("--book-id", required=True)
    args = parser.parse_args()
    run(Path(args.books_root), args.book_id)


if __name__ == "__main__":
    main()
