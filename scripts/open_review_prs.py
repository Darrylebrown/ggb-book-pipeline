"""Open a GitHub PR in ggb-books whenever a book enters a review-awaiting status.

Design:
  - For each book in a review-awaiting status where the gate is still False,
    create branch `review/<book-id>/<stage>` in ggb-books (if not exists).
  - Update state.json ON THAT BRANCH to set the corresponding gate to True.
    (This makes 'merge = approve' — merging the PR is the human's approval action.)
  - Push the branch.
  - Open a PR against master with a review checklist referencing the artifact.

Requires `gh` CLI installed on the runner and `GH_TOKEN` in env pointing at
GGB_BOOKS_TOKEN (so it has push+PR permission on ggb-books).

Usage:
    python scripts/open_review_prs.py --books-root ggb-books
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from state import all_book_ids, load_state, save_state  # noqa: E402


# Which review states get a PR, and what to link to in the PR body.
REVIEW_STATES: dict[str, dict] = {
    "Dossier ready — awaiting review": {
        "gate": "dossier_approved",
        "artifact": "01-dossier.md",
        "stage_slug": "dossier",
    },
    "Structure ready — awaiting review": {
        "gate": "structure_approved",
        "artifact": "02-structure.md",
        "stage_slug": "structure",
    },
    "Entries ready — awaiting review": {
        "gate": "entries_approved",
        "artifact": "03-entries/",
        "stage_slug": "entries",
    },
    "Sample chapter ready — awaiting review": {
        "gate": "sample_chapter_approved",
        "artifact": "04-sample-chapter.md",
        "stage_slug": "sample-chapter",
    },
}


def sh(cmd: list[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def pr_already_open(books_root: Path, branch: str) -> bool:
    try:
        result = sh(["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number"],
                    cwd=books_root, check=False)
        return result.returncode == 0 and result.stdout.strip() not in ("", "[]")
    except FileNotFoundError:
        print("[review] gh CLI not available — cannot open PR")
        return False


def branch_exists_remote(books_root: Path, branch: str) -> bool:
    result = sh(["git", "ls-remote", "--heads", "origin", branch], cwd=books_root, check=False)
    return bool(result.stdout.strip())


def open_pr_for_book(books_root: Path, book_id: str, state: dict, review_info: dict) -> None:
    branch = f"review/{book_id}/{review_info['stage_slug']}"
    artifact = review_info["artifact"]
    gate_field = review_info["gate"]
    current_status = state["status"]

    if pr_already_open(books_root, branch):
        print(f"[review] {book_id}: PR already open for {branch}")
        return

    # Ensure we're on master, create the review branch
    sh(["git", "checkout", "master"], cwd=books_root)
    sh(["git", "pull", "origin", "master"], cwd=books_root)

    if branch_exists_remote(books_root, branch):
        sh(["git", "fetch", "origin", branch], cwd=books_root)
        sh(["git", "checkout", branch], cwd=books_root)
    else:
        sh(["git", "checkout", "-b", branch], cwd=books_root)

    # Update state.json on the branch: pre-flip the gate to True.
    # Merging the PR = approval. The reviewer can also edit further before merging.
    s = load_state(books_root, book_id)
    s["review_gates"][gate_field] = True
    save_state(books_root, book_id, s)

    sh(["git", "config", "user.name", "GGB Pipeline Bot"], cwd=books_root)
    sh(["git", "config", "user.email", "bot@gullahgeecheebiz.com"], cwd=books_root)
    sh(["git", "add", f"books/{book_id}/state.json"], cwd=books_root)
    try:
        sh(["git", "commit", "-m", f"Review gate: {book_id} — {review_info['stage_slug']}"],
           cwd=books_root, check=False)
    except subprocess.CalledProcessError:
        print(f"[review] {book_id}: nothing to commit on branch — continuing")
    sh(["git", "push", "-u", "origin", branch], cwd=books_root, check=False)

    # PR body
    body = f"""## Review: {state.get('working_title', book_id)} — {review_info['stage_slug']}

**Book:** `{book_id}`
**Current status:** `{current_status}`
**Artifact to review:** [`{artifact}`](../blob/{branch}/books/{book_id}/{artifact})

### What to check

- [ ] Content is accurate and well-sourced
- [ ] No fabricated sources or citations
- [ ] Cultural sensitivity respected (no bearers quoted without permission)
- [ ] KDP / Draft2Digital compliant
- [ ] Editorial voice consistent with GGB standards
- [ ] Corridor scope maintained (Wilmington NC → Jacksonville FL)

### How to approve

**Merge this PR.** That's the approval signal.
The `review_gates.{gate_field}` has been pre-flipped to `true` on this branch.
When you merge, the next pipeline cron tick will advance this book to the next stage.

### If you want changes

Add commits to this branch with your edits, then merge when ready.
Or close the PR without merging to reject.

---
_Generated by the GGB Book Pipeline. Every book kit produced at $0._
"""
    body_path = books_root / f".pr-body-{book_id}.md"
    body_path.write_text(body)
    try:
        sh([
            "gh", "pr", "create",
            "--base", "master",
            "--head", branch,
            "--title", f"Review: {book_id} — {review_info['stage_slug']}",
            "--body-file", str(body_path),
            "--label", "book-review",
        ], cwd=books_root, check=False)
    finally:
        body_path.unlink(missing_ok=True)
    print(f"[review] {book_id}: opened PR for {review_info['stage_slug']}")

    # Return to master so the caller's normal flow continues
    sh(["git", "checkout", "master"], cwd=books_root)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--books-root", required=True)
    args = parser.parse_args()
    books_root = Path(args.books_root)

    for book_id in all_book_ids(books_root):
        s = load_state(books_root, book_id)
        info = REVIEW_STATES.get(s["status"])
        if not info:
            continue
        if s["review_gates"].get(info["gate"]):
            continue
        try:
            open_pr_for_book(books_root, book_id, s, info)
        except Exception as e:
            print(f"[review] {book_id}: PR creation failed: {e}")


if __name__ == "__main__":
    main()
