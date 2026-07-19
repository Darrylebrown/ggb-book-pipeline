"""Shared helpers for all stage scripts.

Every stage follows the same shape:
  1. Load state.json for the book
  2. Load prompt template + resolve the stage's prompt + model
  3. Set status to <stage> drafting
  4. Fill placeholders in the prompt
  5. Call LLM (with retry / backoff via llm.py)
  6. Write outputs to book folder
  7. Update state (assets_generated, stages_completed, status)
  8. Record run

This module abstracts the pattern so individual stages stay short.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from state import load_state, save_state, record_run, mark_error, AUTHOR, PUBLISHER  # noqa: E402
from llm import call_llm, LLMResult  # noqa: E402
from compliance import check_text, enforce_or_hold  # noqa: E402


PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


@dataclass
class StageContext:
    """Everything a stage script needs to do its job."""
    books_root: Path
    book_id: str
    state: dict
    template: dict
    book_dir: Path
    system_prompt: str
    stage_prompt: str
    model: str


def load_context(books_root: Path, book_id: str, stage_key: str) -> StageContext:
    """Load state + template + resolve stage prompt/model. Raises on missing template."""
    state = load_state(books_root, book_id)
    template_path = PROMPTS_DIR / f"{state['prompt_template']}.yaml"
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
    template = yaml.safe_load(template_path.read_text())

    system_prompt = template["system_prompt"]
    stage_prompt = template["stages"][stage_key]
    model = template["preferred_models"][stage_key]
    book_dir = books_root / "books" / book_id

    return StageContext(
        books_root=books_root,
        book_id=book_id,
        state=state,
        template=template,
        book_dir=book_dir,
        system_prompt=system_prompt,
        stage_prompt=stage_prompt,
        model=model,
    )


def fill_placeholders(prompt: str, replacements: dict[str, str]) -> str:
    """Replace {{KEY}} tokens in the prompt with values."""
    out = prompt
    for key, value in replacements.items():
        out = out.replace("{{" + key + "}}", str(value))
    return out


def set_status(books_root: Path, book_id: str, new_status: str, current_stage: Optional[str] = None) -> None:
    """Convenience: update status (and optionally current_stage) and persist."""
    s = load_state(books_root, book_id)
    s["status"] = new_status
    if current_stage:
        s["current_stage"] = current_stage
    save_state(books_root, book_id, s)


def complete_stage(
    books_root: Path,
    book_id: str,
    stage_name: str,
    new_status: str,
    assets_key: Optional[str] = None,
    assets_value: Any = None,
    llm_result: Optional[LLMResult] = None,
) -> None:
    """Common completion: update assets_generated, stages_completed, status. Log the run."""
    s = load_state(books_root, book_id)
    if assets_key is not None:
        s["assets_generated"][assets_key] = assets_value
    if stage_name not in s["stages_completed"]:
        s["stages_completed"].append(stage_name)
    s["status"] = new_status
    save_state(books_root, book_id, s)
    if llm_result is not None:
        record_run(
            books_root, book_id,
            stage=stage_name,
            model=llm_result.model,
            tokens_in=llm_result.tokens_in,
            tokens_out=llm_result.tokens_out,
            status="success",
        )


def guard_stage_output(
    books_root: Path,
    book_id: str,
    output_name: str,
    text: str,
    stage_name: str,
) -> None:
    """Compliance guard for a freshly written stage output.

    Runs a text-level brand/PII scan. On any block, sets a compliance hold
    (status=Paused, current_stage=compliance_hold) and raises SystemExit so
    the stage does NOT complete to a ready status with bad content.
    """
    blocks = [v for v in check_text(text, path=output_name) if v.severity == "block"]
    if not blocks:
        return
    s = load_state(books_root, book_id)
    s["status"] = "Paused"
    s["current_stage"] = "compliance_hold"
    codes = ", ".join(sorted({v.code for v in blocks}))
    s["last_error"] = f"Compliance hold in {stage_name} ({output_name}): {codes}"
    save_state(books_root, book_id, s)
    # Persist a full report as well (scan existing assets).
    enforce_or_hold(books_root, book_id, scan_outputs=True, apply=True, hold=True)
    detail = "; ".join(f"{v.code}: {v.detail}" for v in blocks)
    raise SystemExit(f"[{stage_name}] compliance hold — {detail}")


def run_simple_llm_stage(
    books_root: Path,
    book_id: str,
    stage_key: str,          # key into template.stages + template.preferred_models
    stage_name: str,          # canonical name for stages_completed + logs
    drafting_status: str,
    ready_status: str,
    output_filename: str,     # relative to book_dir
    assets_key: str,          # key in state.assets_generated
    placeholders: Optional[dict[str, str]] = None,
    max_tokens: int = 8000,
) -> None:
    """The canonical pattern: 1 LLM call, 1 markdown output, status transition.

    Used by dossier, structure, sample chapter, KDP metadata, ACX brief, rights & IP,
    Substack teaser. Batched or multi-output stages have their own scripts.
    """
    ctx = load_context(books_root, book_id, stage_key)

    # Set drafting status
    set_status(books_root, book_id, drafting_status, current_stage=stage_name)

    # Fill placeholders (default set — every prompt gets these)
    default_reps = {
        "TITLE": ctx.state.get("working_title", ""),
        "SUBTITLE": ctx.state.get("subtitle", ""),
        "BRIEF": ctx.state.get("one_line_brief", ""),
        # Hardwired — never read author/publisher from state, always the locked constants.
        "AUTHOR": AUTHOR,
        "PUBLISHER": PUBLISHER,
        "ENTRY_COUNT_TARGET": str(ctx.state.get("entry_count_target", 370)),
        "SECTION_COUNT": str(ctx.state.get("section_count", 10)),
    }
    if placeholders:
        default_reps.update(placeholders)
    full_prompt = fill_placeholders(ctx.stage_prompt, default_reps)

    print(f"[{stage_name}] Calling {ctx.model} for {book_id} (max_tokens={max_tokens})")
    try:
        result = call_llm(full_prompt, model=ctx.model, system=ctx.system_prompt, max_tokens=max_tokens)
    except Exception as e:
        mark_error(books_root, book_id, f"{stage_name} stage failed: {e}")
        raise

    output_path = ctx.book_dir / output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.text)

    # Hard compliance gate on the freshly written output. If the content
    # carries brand blocks or PII, place the book on compliance hold and fail
    # the stage rather than completing it to a ready status.
    guard_stage_output(books_root, book_id, output_path.name, result.text, stage_name)

    complete_stage(
        books_root, book_id,
        stage_name=stage_name,
        new_status=ready_status,
        assets_key=assets_key,
        assets_value=str(output_path.relative_to(books_root)),
        llm_result=result,
    )
    print(f"[{stage_name}] Wrote {output_path.name} ({result.tokens_out} tokens out) → status={ready_status!r}")
