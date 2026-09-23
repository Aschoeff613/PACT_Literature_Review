# PACT literature review: search tightening, 22 September 2026

Approved 22 September 2026 by the PI. Amends protocol v7 and the
28 August 2026 decisions (`docs/DECISIONS_2026-08-28.md`) for steps 1 and 2. New
decision identifier: `2026-09-22-search-tightening`. Steps 2 and 3 refuse to
consume outputs that do not carry it.

## Why

A 20-paper screening trial on the 28 August sample (both models, full
agreement, archived in `data/archive/`) found 11 of 20 papers (55%) that both
models read as neither emergency medicine nor primary care: 9 of 14 in the
primary-care arm (64%), 2 of 6 in the emergency-medicine arm. Tracing each
back to the term that retrieved it showed passing mentions of primary care
("Primary Health Care"[MeSH] as a non-major tag, "general practitioners"
used for dentists) combined with broad coordination headings.

Screening excluded all of these correctly, so this is a yield and validation
problem rather than a screening error. At those rates the 500-paper sample
yields roughly 75 in-scope papers, and step 4's human check would partly
measure setting detection rather than cognitive content.

## Decisions

6. **Children-only papers are removed from the search.** Clause:
   `NOT (("Infant"[MeSH] OR "Child"[MeSH] OR "Adolescent"[MeSH]) NOT "Adult"[MeSH])`.
   The `NOT "Adult"` guard keeps mixed-age studies, which are common in adult
   emergency medicine (e.g. patients aged 16 and over). Records without MeSH
   age indexing (mostly recent) pass through; screening still excludes
   paediatric-only work. This is a deliberate, bounded exception to the
   28 August principle of keeping population exclusions out of the query.
7. **Dental papers are removed from the search.** Clause:
   `NOT ("Dentistry"[MeSH] OR "Dentists"[MeSH])`. Dentistry is also added to the
   out-of-scope list in the AI prompt and the human review interface, which
   state the same criterion.
8. **`"Primary Health Care"[MeSH]` is restricted to `[majr]`**, the same
   treatment decision 5 gave the coordination headings. `"primary care"`,
   `"general practice"` and `"general practitioner(s)"` title/abstract terms
   and the other primary-care MeSH headings are unchanged: general practitioner
   is the British and Commonwealth term for a primary care physician.

9. **Sample raised from 250 + 250 to 1,000 + 1,000.** Screening trials on
   70 papers put the either-model include rate near 10% (7 of 70; 4 of 50 on
   the current search). At that rate 500 papers yield roughly 40-50 AI-kept
   papers, which cannot fill step 4's design of 75 AI-kept papers per setting
   and is thin for the step 13 saturation plot. 1,000 per setting is the
   smallest round size that fills step 4 at that rate. Same seed (20260828):
   because the draw takes a prefix of a seeded shuffle, the 1,000-per-setting
   sample contains the earlier 250-per-setting sample, so papers already
   screened carry over. Budget: the whole pipeline must stay under $50 of
   model spend; screening 2,000 papers is estimated at about $18.

## Measured effect before adoption

Applied to the 28 August 500-paper sample, the three changes removed 67
records (13%): 43 children-only, 4 dental, 21 primary-care papers whose only
primary-care signal was the non-major heading. Manual title review of all
three groups found no in-scope paper removed (the 21 were ICU, stroke
rehabilitation, oncology, inpatient rehabilitation, fertility and telestroke
work). None of the 3 papers included in the 20-paper trial was removed.

## Known limit

These changes remove a slice of the off-setting material, not most of it.
Of the 11 off-setting papers in the trial, only 1 would have been removed.
The remainder retrieve through passing text mentions of primary care or
emergency care, which PubMed indexing cannot separate from studies set there.
Screening remains the main filter for setting.

## Methods wording

Records indexed exclusively to paediatric age groups, and records indexed to
dentistry, were excluded at the search stage; mixed-age records were retained.
The Primary Health Care MeSH heading was restricted to major topic because, as
a minor heading, it predominantly retrieved papers that mentioned primary care
without being set in it. The search and 500-record sample were regenerated
after these changes.
