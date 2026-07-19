# Cultural Ethics Protocol

This pipeline produces content about the **Gullah Geechee community** — a living people with a preservation mission. Every AI-generated artifact passes through review by named human cultural bearers before publication.

## Non-negotiable rules

1. **Living bearers are never quoted without written permission.**
2. **Sacred content is excluded from publication entirely** — marked as `sensitivity: "Sacred"` in entry JSON and filtered out of all outputs.
3. **Restricted content requires named-bearer approval** before appearing in any deliverable.
4. **Attribution is inline and immediate.** Every entry lists source URLs. Every source is real and verifiable.
5. **Community credit is protocol, not afterthought.** The Acknowledgments section names every bearer, scholar, and organization consulted, whether alive or in memoriam.

## Bearers we credit (updated as engagement grows)

- Lorenzo Dow Turner (posthumous)
- Queen Quet / Marquetta Goodwine
- Dr. Emory Campbell
- Sea Island Translation Team
- Virginia Mixson Geraty (posthumous)
- Salikoko Mufwene
- Dr. Michael Allen
- Sallie Ann Robinson
- Mary Jackson
- Cornelia Walker Bailey (posthumous)

## AI disclosure

Following KDP AI-content policy, every book produced by this pipeline includes on the copyright page:

> Portions of this work were produced with generative AI assistance under direct human editorial supervision. All cultural content was reviewed and approved by named community bearers listed in the Acknowledgments. Sacred and restricted material has been excluded from publication.

## Automated compliance gate

These rules are enforced automatically by a hard **compliance gate** before any
material can advance through the pipeline — including the KDP + Draft2Digital
minimum required for handoff. A failing check blocks the book (compliance hold)
rather than passing silently. See [`docs/compliance.md`](compliance.md).

## Reviewer sign-off

Every book requires signoff on:
- Dossier accuracy
- Section structure
- Full entries (all sections)
- Sample chapter
- Final kit

Signoff mechanism: named reviewer merges the corresponding GitHub Pull Request after reviewing the diff and adding any editorial notes as PR comments.
