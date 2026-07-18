# GGB Book Pipeline

> Zero-cost publishing pipeline for [Gullah Geechee Biz](https://gullahgeecheebiz.com).
> One brief → full production kit (dossier, structure, entries, sample chapter, KDP metadata, social scripts, ACX brief, rights & IP).

**Publisher:** Gullah Geechee Biz
**Author of record:** Darryl Elliott Brown
**Architecture:** GitHub Actions + Google Gemini free tier + Groq free tier + Git as database
**Cost:** $0/month

---

## What this is

A publishing pipeline that turns a one-paragraph book brief into a complete production kit — with no paid software, no paid APIs, and no infrastructure to maintain.

Built for the Gullah Geechee Biz reference library. Currently piloting *De Gullah Book: A Living Vocabulary of the Gullah Geechee Corridor* (Edition 1).

## Companion repo

Actual book manuscript content lives in the **private** [`ggb-books`](https://github.com/Darrylebrown/ggb-books) repo. This public repo hosts the scripts, workflows, and prompt templates. GitHub Actions here check out both repos when running.

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full specification.

Short version:

- **Engine:** Google Gemini (free tier — 50 Pro requests/day) + Groq Llama 3.3 70B (free tier — effectively unlimited)
- **Orchestrator:** GitHub Actions on cron (every 15 min)
- **Database:** `state.json` per book in the private books repo
- **Review UI:** GitHub Pull Requests
- **Publishing endpoint:** Manual to KDP + ACX; Make.com free tier fires Blotato + Substack + GDrive on launch day

## Repo layout

```
ggb-book-pipeline/           (this repo, public)
├── scripts/                 Pipeline stage scripts (Python)
├── prompts/                 Book type templates (YAML)
├── .github/workflows/       GitHub Actions cron + intake + launch
├── tests/                   Pytest for scripts
└── docs/                    Architecture + operations guide

ggb-books/                   (companion repo, private)
└── books/
    └── <book-id>/           One folder per book
        ├── state.json       Pipeline status
        ├── brief.md         Human intake
        ├── 01-dossier.md    AI generated
        ├── 02-structure.md
        ├── 03-entries/      JSON per section
        ├── 04-sample-chapter.md
        ├── 05-kdp-metadata.md
        ├── 06-pins/
        ├── 07-tiktok-script.md
        ├── 08-shorts-script.md
        ├── 09-substack-teaser.md
        ├── 10-acx-brief.md
        ├── 11-rights-ip.md
        └── final-kit.zip
```

## Getting started

1. Fork or clone this repo
2. Add these secrets to your repo settings:
   - `GEMINI_API_KEY` — from [Google AI Studio](https://aistudio.google.com/apikey)
   - `GROQ_API_KEY` — from [Groq Cloud](https://console.groq.com)
   - `GGB_BOOKS_TOKEN` — a fine-grained PAT with read/write access to `ggb-books`
   - `MAKE_LAUNCH_WEBHOOK` — Make.com scenario webhook (optional, launch day only)
3. Trigger `.github/workflows/new-book.yml` via workflow_dispatch to intake your first book
4. Cron will pick it up within 15 minutes and start advancing it through the pipeline

## Cultural ethics

This pipeline produces content about the Gullah Geechee community — a living people with a preservation mission. Every AI-generated artifact passes through human review by named cultural bearers before publication. See [`docs/cultural-ethics.md`](docs/cultural-ethics.md).

## License

Scripts and workflows: MIT.
Prompt templates: MIT.
Any book content produced by the pipeline is the copyrighted work of Darryl Elliott Brown and Gullah Geechee Biz — not covered by this repo's license.

---

*Mus tek cyear a de root, fa heal de tree.*
