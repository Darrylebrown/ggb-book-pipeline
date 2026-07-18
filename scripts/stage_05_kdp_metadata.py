"""Stage 05 — Generate the KDP + D2D metadata pack."""
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
        stage_key="kdp_metadata",
        stage_name="kdp_metadata",
        drafting_status="KDP metadata drafting",
        ready_status="Social assets drafting",  # KDP metadata cascades directly into social
        output_filename="05-kdp-metadata.md",
        assets_key="kdp_metadata",
        max_tokens=6000,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--books-root", required=True)
    parser.add_argument("--book-id", required=True)
    args = parser.parse_args()
    run(Path(args.books_root), args.book_id)


if __name__ == "__main__":
    main()
