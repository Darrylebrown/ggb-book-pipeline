"""Dry-run integration test — proves the full pipeline runs end-to-end with NO API keys.

Sets DRY_RUN=1 and executes every stage in sequence against a fresh book.
Verifies the final ZIP exists and the state ends in "Ready for KDP handoff".
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _run(module: str, tmp_path: Path, book_id: str, env: dict) -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / f"{module}.py"),
         "--books-root", str(tmp_path), "--book-id", book_id],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"{module} failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"


def test_full_pipeline_dry_run(tmp_path):
    env = {**os.environ, "DRY_RUN": "1", "PYTHONPATH": str(REPO_ROOT / "scripts")}
    book_id = "dry-run-book"

    # 1. Intake
    result = subprocess.run([
        sys.executable, str(REPO_ROOT / "scripts" / "new_book.py"),
        "--books-root", str(tmp_path),
        "--book-id", book_id,
        "--title", "Dry Run Test",
        "--subtitle", "No API Calls",
        "--template", "vocabulary-reference-v1",
        "--brief", "End-to-end pipeline test with no LLM.",
        "--entry-count-target", "10",
    ], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    # 2. Run all stages in order
    from state import load_state, save_state

    _run("stage_01_dossier", tmp_path, book_id, env)
    assert load_state(tmp_path, book_id)["status"] == "Dossier ready — awaiting review"

    _run("stage_02_structure", tmp_path, book_id, env)
    assert load_state(tmp_path, book_id)["status"] == "Structure ready — awaiting review"

    # Entries may need to be run more than once (batching) — loop until done
    for _ in range(5):
        _run("stage_03_entries", tmp_path, book_id, env)
        s = load_state(tmp_path, book_id)
        if s["status"] == "Entries ready — awaiting review":
            break
    assert load_state(tmp_path, book_id)["status"] == "Entries ready — awaiting review"

    _run("stage_04_sample_chapter", tmp_path, book_id, env)
    _run("stage_05_kdp_metadata", tmp_path, book_id, env)
    _run("stage_06_social", tmp_path, book_id, env)
    _run("stage_10_acx", tmp_path, book_id, env)
    _run("stage_11_rights", tmp_path, book_id, env)
    _run("stage_12_assemble", tmp_path, book_id, env)

    # Verify final state
    s = load_state(tmp_path, book_id)
    assert s["status"] == "Ready for KDP handoff"

    kit = tmp_path / "books" / book_id / "final-kit.zip"
    assert kit.exists(), "Final kit ZIP was not produced"
    assert kit.stat().st_size > 500, "Final kit is suspiciously small"

    # Verify every expected file made it into the book folder
    book_dir = tmp_path / "books" / book_id
    for expected in [
        "00-README.md",
        "01-dossier.md",
        "02-structure.md",
        "04-sample-chapter.md",
        "05-kdp-metadata.md",
        "06-pins.md",
        "07-tiktok-script.md",
        "08-shorts-script.md",
        "09-substack-teaser.md",
        "10-acx-brief.md",
        "11-rights-ip.md",
    ]:
        assert (book_dir / expected).exists(), f"Missing {expected}"
