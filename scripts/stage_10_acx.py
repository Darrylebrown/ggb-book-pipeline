"""Stage 10 — Generate the ACX narrator direction sheet."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from stage_common import run_simple_llm_stage  # noqa: E402


def run(books_root: Path, book_id: str) -> None:
    run_simple_llm_stage(
        books_root=books_root,
        book_id=book_id,
        stage_key="acx_brief",
        stage_name="acx_brief",
        drafting_status="ACX brief drafting",
        ready_status="Rights & IP drafting",
        output_filename="10-acx-brief.md",
        assets_key="acx_brief",
        max_tokens=5000,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--books-root", required=True)
    parser.add_argument("--book-id", required=True)
    args = parser.parse_args()
    run(Path(args.books_root), args.book_id)


if __name__ == "__main__":
    main()
