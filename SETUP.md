# GGB Book Pipeline — Setup Guide

**Cost:** $0. Everything below runs on free tiers.
**Time to first book:** ~15 minutes of setup, then 30 minutes for the cron to pick it up.

---

## Step 0 — Sanity check without any keys

You can prove the pipeline works right now, before adding any secrets:

```bash
git clone https://github.com/Darrylebrown/ggb-book-pipeline
cd ggb-book-pipeline
pip install -r requirements.txt
pip install pytest
python -m pytest tests/ -v
```

You should see **15 tests pass** — including a full end-to-end dry-run that produces a `final-kit.zip` without calling any LLM.

To simulate a book locally with fake content:

```bash
export DRY_RUN=1
python scripts/new_book.py --books-root /tmp/testbooks \
    --book-id my-test --title "Test" --subtitle "Test" \
    --template vocabulary-reference-v1 --brief "Testing" --entry-count-target 10

python scripts/stage_01_dossier.py --books-root /tmp/testbooks --book-id my-test
# ...run each stage_XX in order...
```

**When `DRY_RUN=1` is set, every stage writes placeholder content instead of calling Gemini or Groq.** Zero quota consumed. Perfect for validating the plumbing.

---

## Step 1 — Get your Gemini API key (free)

1. Open [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Sign in with your Google account (any Gmail works)
3. Click **"Create API key"** → **"Create API key in new project"**
4. Copy the key that appears (starts with `AIza...`)

**Free tier limits you'll be using:**
- **Gemini 2.0 Pro:** 50 requests/day, 2 requests/min — used for long-form content
- **Gemini 2.0 Flash:** 1,500 requests/day, 15 requests/min — used for short/varied content

At 50 Pro requests/day, the pipeline can produce **~1 full book kit per day**. That's the current bottleneck.

---

## Step 2 — Get your Groq API key (free)

1. Open [console.groq.com/keys](https://console.groq.com/keys)
2. Sign in (Google/GitHub/email all work)
3. Click **"Create API Key"** → give it a name (`ggb-pipeline`)
4. Copy the key (starts with `gsk_...`)

**Free tier limits:**
- **Llama 3.3 70B:** 30 requests/min, ~14,400/day — used for TikTok/Shorts variants and quick tasks

Groq's daily cap is so generous it's effectively unlimited for this pipeline.

---

## Step 3 — Create a GitHub PAT for the books repo

The pipeline needs to push generated content and open PRs in `ggb-books`. Create a fine-grained token scoped to that one repo.

1. Open [github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new)
2. **Token name:** `ggb-pipeline-books`
3. **Expiration:** 1 year (renew annually)
4. **Resource owner:** `Darrylebrown`
5. **Repository access:** "Only select repositories" → pick **`ggb-books`** only
6. **Permissions → Repository permissions:**
   - **Contents:** Read and write
   - **Pull requests:** Read and write
   - **Metadata:** Read-only (auto-selected)
7. Click **"Generate token"** and copy it (starts with `github_pat_...`)

⚠️ **Do not** grant this token access to `ggb-book-pipeline` or any other repo. Least privilege.

---

## Step 4 — Paste all three into pipeline secrets

1. Open [ggb-book-pipeline secrets](https://github.com/Darrylebrown/ggb-book-pipeline/settings/secrets/actions)
2. Click **"New repository secret"** for each of these three:

| Secret name | Value |
|---|---|
| `GEMINI_API_KEY` | The `AIza...` key from Step 1 |
| `GROQ_API_KEY` | The `gsk_...` key from Step 2 |
| `GGB_BOOKS_TOKEN` | The `github_pat_...` token from Step 3 |

That's it. The cron is already scheduled — no other config needed.

---

## Step 5 — Launch your first book

1. Open [Actions → New book intake](https://github.com/Darrylebrown/ggb-book-pipeline/actions/workflows/new-book.yml)
2. Click **"Run workflow"** (top right, gray button)
3. Fill in the form:
   - **Book ID:** short slug like `de-watuh-vol1` (used in folder + branch names)
   - **Working title:** e.g. `De Watuh: Rivers, Creeks & Tides`
   - **Subtitle:** e.g. `A Gullah Geechee Vocabulary of Waterways`
   - **Template:** `vocabulary-reference-v1`
   - **One-line brief:** what the book is about (1-2 sentences)
   - **Entry count target:** `370` for the pilot, or lower for a shorter book
4. Click **"Run workflow"** (green button)

Within 30 minutes, the cron will pick up the new book (status: `Brief received`) and start Stage 1 (dossier). Watch [Actions](https://github.com/Darrylebrown/ggb-book-pipeline/actions) for progress.

---

## Step 6 — Reviewing what the pipeline produced

Every review-gated stage opens a PR in [`ggb-books`](https://github.com/Darrylebrown/ggb-books) on a branch like `review/de-watuh-vol1/dossier`.

**To approve:** merge the PR. The `review_gates.<stage>_approved` flag is already pre-set to `true` on the branch — merging is the signal that pushes it to `master`, and the next cron tick advances the book.

**To request changes:** add commits to the review branch (edit files directly on GitHub, or clone locally). Then merge when ready.

**To reject:** close the PR without merging. The book stays in the awaiting-review state until you re-run or intervene.

---

## Step 7 — When the book is complete

When status flips to **`Ready for KDP handoff`**, look inside the book's folder for `final-kit.zip`. That's your entire book kit — dossier, structure, 10 sections of entries, sample chapter, KDP metadata, 4 social assets, ACX brief, rights doc, README. Zip it and upload wherever you need.

---

## Troubleshooting

**Cron not running?** GitHub disables scheduled workflows after 60 days of repo inactivity. Push any commit to re-enable, or manually trigger via Actions → Pipeline dispatcher → Run workflow.

**"Rate limited" in Actions logs?** Expected once you hit 50 Gemini Pro requests/day. The pipeline pauses in place and resumes on the next cron tick after the daily reset (midnight Pacific).

**Book stuck in "Entries generating"?** That's normal — Stage 3 batches 5 entries per call and caps at 8 batches per tick. A 370-entry book takes ~2-3 days of cron ticks to fill entirely. This is the intentional zero-cost tradeoff.

**Want to run one stage manually?** Locally, with keys set:
```bash
export GEMINI_API_KEY=...
export GROQ_API_KEY=...
git clone https://github.com/Darrylebrown/ggb-books /tmp/ggb-books
python scripts/stage_02_structure.py --books-root /tmp/ggb-books --book-id de-watuh-vol1
```

**Need to nuke everything and start over?** Delete the book's folder in `ggb-books` (`books/<book-id>/`) and re-run the intake workflow with a new book ID.

---

## Cost accounting

| Item | Cost |
|---|---|
| GitHub Actions (public repo) | Unlimited free |
| Gemini API (free tier) | $0 |
| Groq API (free tier) | $0 |
| Storage (public + private repo) | $0 |
| **Total** | **$0/month, forever** |

The only paid step is optional: **ISBNs** (~$125 for 10 from Bowker, or free through KDP if you're okay with Amazon-owned ISBNs).
