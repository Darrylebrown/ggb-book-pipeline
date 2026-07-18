# GGB Book Pipeline — Architecture

The full v3.0 specification lives in the workspace at
`gullah-geechee-biz/book-pipeline/airtable-book-pipeline-spec-v3.md`.

This file will be updated with the canonical committed version once the pipeline
runs its first end-to-end book. For now, treat the workspace spec as the source
of truth.

## Quick reference

- **Engine:** Google Gemini free tier + Groq free tier
- **Orchestrator:** GitHub Actions cron (every 15 min)
- **Database:** `state.json` in `ggb-books` private repo, one folder per book
- **Review UI:** GitHub Pull Requests
- **20 pipeline statuses** — see `scripts/state.py::STATUSES`
- **10 book templates planned** — currently ships with `vocabulary-reference-v1`

## Rate limit budget

| Provider | Free tier | Per-book cost |
|----------|-----------|---------------|
| Gemini 2.0 Pro | 50 requests/day | ~15 calls (spread over 1 day) |
| Gemini 2.0 Flash | 1,500 requests/day | ~10 calls |
| Groq Llama 3.3 70B | ~14,400 requests/day | ~5 calls |
| GitHub Actions | Unlimited (public repo) | ~2 min per cron tick |

Bottleneck: Gemini Pro at 50 requests/day. Effective capacity: **1 full book per day**.
