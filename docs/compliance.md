# Compliance Gate (ruleset v1.1)

The pipeline enforces a **hard compliance gate**: only compliant material may
advance. A failing check is a *block* — the book is placed on a compliance hold
(`status: "Paused"`, `current_stage: "compliance_hold"`) and never advances
silently. The gate is implemented in [`scripts/compliance.py`](../scripts/compliance.py).

## Where the gate runs

| Point | Check | On failure |
|-------|-------|------------|
| `new_book.py` (intake) | intake-only (`scan_outputs=False`) | hold + exit non-zero |
| `state.py` `books_ready_to_advance` | intake-only per candidate | hold + excluded from queue |
| `run_pipeline.py` (before a stage) | scan assets if any exist | hold + skip stage |
| `run_pipeline.py` (after a stage) | full scan (`scan_outputs=True`) | hold |
| `stage_common.py` (after writing output) | brand/PII scan of new output | hold + stage fails, no ready status |

## What fails a title

### GGB brand / ethics (always)

- **Author must be `Darryl Elliott Brown`** and **publisher `Gullah Geechee Biz`** (exact).
- **Working title present**; `brief.md` present and not thin (< 40 chars).
- **No forbidden links / framing** (block):
  - Manus references or links
  - Steady Lane / Morgan Ellis side-catalog mix-in
  - Personal tip-jar / Venmo / CashApp / PayPal.me solicitation
  - Celebrity / Hollywood framing in brand copy (historical subjects like
    Robert Smalls or Harriet Tubman are fine)
  - Sensational true-crime framing (especially Mother Emanuel packaging)
- **No personal PII** in public-facing materials (email, phone, SSN).
- Possible **mock dialect** without a scholarly frame is a *warning* (scholarly
  Gullah language discussion is welcome).

### KDP + Draft2Digital minimum

Applied to `05-kdp-metadata.md` **when it exists** (block on failure):

- Title matches `state.working_title`
- Author `Darryl Elliott Brown` + publisher `Gullah Geechee Biz`
- Description / blurb present, ≥ 100 characters
- Keywords section with **≥ 3** items (KDP allows up to 7)
- At least one **category / BISAC** code
- **AI disclosure** (generative AI assistance under human editorial supervision)
- **Draft2Digital** note (human editing / documentation, or a D2D imprint section)
- No placeholders left (`lorem ipsum`, `TODO`, `TBD`, `[INSERT ...]`, `FIXME`)
- Content-safe: no price/earnings guarantees, no medical cure claims, no hate speech
- Cover/title contradiction is flagged as a warning

Applied to `11-rights-ip.md` when it exists: AI disclosure, copyright / rights
language, author + publisher attribution.

Applied to `10-acx-brief.md` when it exists: author credit, publisher, narrator
direction.

Applied to sample chapter / manuscript markdown: brand + PII scan (no Manus,
tip jar, PII, side catalog).

### Ready for KDP handoff

Before assembly completes or status becomes `Ready for KDP handoff`, a full
`scan_outputs=True` pass must succeed, including KDP metadata and rights.

## Running the checker manually

```bash
# Report only (exit code 2 if blocked)
python scripts/compliance.py --books-root ../ggb-books --book-id de-gullah-book

# Intake-only (skip generated-asset scan)
python scripts/compliance.py --books-root ../ggb-books --book-id de-gullah-book --no-scan-outputs

# JSON report
python scripts/compliance.py --books-root ../ggb-books --book-id de-gullah-book --json

# Persist result to state.compliance, and hold on failure
python scripts/compliance.py --books-root ../ggb-books --book-id de-gullah-book --apply --hold
```

`--apply` writes `state["compliance"] = {gate_passed, ruleset_version,
checked_at, violations}`. `--hold` additionally sets `Paused` /
`compliance_hold` and a summarizing `last_error` when a block is found.

## Clearing a hold

Fix the offending content (or metadata), then re-run with `--apply` (and set the
status back to the appropriate pipeline stage). The gate re-checks on every
pipeline tick, so a book that has been corrected will resume advancing.
