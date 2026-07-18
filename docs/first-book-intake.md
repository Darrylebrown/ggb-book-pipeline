# First-Book Intake Payload — Ready to Paste

Paste these values into the [New book intake workflow form](https://github.com/Darrylebrown/ggb-book-pipeline/actions/workflows/new-book.yml) when you click "Run workflow".

---

## Option A — De Watuh (recommended pilot)

Best first pick — it's the same section the pilot kit already used as its sample chapter, so you'll get to see the full 37-entry version vs. the pilot's demo entries.

| Field | Value |
|---|---|
| **Book ID** | `de-watuh-vol1` |
| **Working title** | `De Watuh` |
| **Subtitle** | `A Gullah Geechee Vocabulary of Rivers, Creeks, and Tides` |
| **Template** | `vocabulary-reference-v1` |
| **Entry count target** | `370` |
| **One-line brief** | `A place-based vocabulary reference documenting Gullah Geechee terms for water — rivers, creeks, marshes, tides, seasons, and the working relationship between coastal Black communities and the waterways from Wilmington NC to Jacksonville FL.` |

---

## Option B — De Land (companion volume)

Natural sequel to De Watuh. Same corridor scope, same series, different domain.

| Field | Value |
|---|---|
| **Book ID** | `de-land-vol1` |
| **Working title** | `De Land` |
| **Subtitle** | `A Gullah Geechee Vocabulary of Soil, Field, and Woods` |
| **Template** | `vocabulary-reference-v1` |
| **Entry count target** | `370` |
| **One-line brief** | `A vocabulary reference for Gullah Geechee terms describing the land — soil types, farm work, wild plants, hunting grounds, and the ancestral geography of Gullah Geechee communities in the coastal corridor from NC to FL.` |

---

## Option C — De Praise (spiritual volume, requires extra ethics review)

More culturally sensitive. Recommended only after De Watuh proves the pipeline. The rights & IP stage will flag additional review checkpoints for spiritual/ritual content.

| Field | Value |
|---|---|
| **Book ID** | `de-praise-vol1` |
| **Working title** | `De Praise` |
| **Subtitle** | `A Gullah Geechee Vocabulary of Worship, Song, and Ancestor` |
| **Template** | `vocabulary-reference-v1` |
| **Entry count target** | `320` |
| **One-line brief** | `A reverent vocabulary reference for Gullah Geechee spiritual terms — praise house tradition, ring shout, spirituals, ancestor veneration, and the vocabulary of Gullah worship. Cultural sensitivity level: HIGH. All entries require bearer review before publication.` |

---

## What happens next

1. You submit the form → workflow creates `books/<book-id>/state.json` and `books/<book-id>/brief.md` in `ggb-books`
2. Status = `Brief received`
3. Within 30 min, cron picks it up and runs Stage 1 (dossier) → status = `Dossier ready — awaiting review`
4. PR appears in [ggb-books](https://github.com/Darrylebrown/ggb-books/pulls)
5. You merge → cron runs Stage 2 (structure) → PR appears → repeat
6. After Stage 3 (entries) approval, Stages 4-12 run automatically without review gates
7. Final `final-kit.zip` lands in `books/<book-id>/final-kit.zip` when status = `Ready for KDP handoff`

**Total human review touchpoints:** 4 PRs (dossier, structure, entries, sample chapter). Everything after is automated.
