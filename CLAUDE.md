# PACT targeted literature review — Task 1.1.1, literature stream

## Read this first

**`docs/PACT_LitReview_Plan.pdf` (protocol v7, 18 Aug 2026) is the baseline
authoritative document.** For steps 1–3 it is amended by the approved decisions
in **`docs/DECISIONS_2026-08-28.md`** and **`docs/DECISIONS_2026-09-22.md`**. `docs/README_superseded.md` and
`docs/protocol_superceded.md` are earlier generations of the same project,
kept for the methods write-up. Do not follow them and do not "fix" code to match
them. If they disagree with v7, v7 wins except for the five explicitly approved
amendments in the dated decision record.

Andrew is working on **steps 1 to 3 only**. Do not build, refactor, or propose
work on steps 4 onward unless asked.

## What the project is for

An earlier PACT phase generated candidate clinician cognitive tasks by eliciting
them from frontier models. This literature stream derives a task list
*independently* from published papers so the two can be cross-tabulated: tasks
the models produced and the literature confirms, tasks the models produced with
no literature support, and tasks only the literature found. That third set is the
scientific payload.

This is why v7 blinds every step to the existing PACT task list, and why step 12
locks the list before any comparison happens. Independence is the whole claim.
Any suggestion that would let the PACT task list leak into screening, extraction,
or grouping breaks the study.

## Steps 1 to 3 as v7 defines them

**Step 1, `scripts/01_search.py`.** Adult emergency medicine OR adult primary
care, AND at least one of three term groups: how clinicians think / where things
go wrong / coordination and communication. English, 2005–2026. Gate before
moving on: record hits per setting, and confirm the coordination terms return a
usable number.

**Step 2, `scripts/11_neutral_sample.py`.** 250 papers from emergency medicine,
250 from primary care. Random draw, seed recorded. Numbered in batches of 100.

**Step 3, `scripts/03_screen.py`.** Two models read all 500 titles and abstracts
separately. In scope means the paper *actually examines what a clinician notices,
decides, interprets, or communicates*; merely mentioning a clinical decision in
passing is not. When a model is unsure, it includes. Record which prompt file and
code version were used.

## Environment

```
export PACT_EMAIL="<stanford address>"      # required, NCBI throttles without it
export NCBI_API_KEY="..."                   # optional, 3/sec -> 10/sec
export OPENROUTER_API_KEY="sk-or-..."       # step 3 only, Austin's token
export PACT_MODEL_A="vendor/model"          # optional override
export PACT_MODEL_B="othervendor/model"     # optional override
```

Screening goes through **OpenRouter** (one key, both models), not separate
OpenAI and Anthropic keys. The superseded README describes the two-key setup.

Python 3.8+, standard library only. Do not add third-party dependencies without
asking — the scripts have to run on a collaborator's machine with no setup.
This is also why PubMed access is hand-rolled E-utilities calls in
`common.py` rather than an MCP PubMed connector: an MCP tool only works
inside a configured Claude session, not as a standalone script Austin runs
with plain `python3`. It also would not give the fine control the scripts
need over POST vs GET, pagination past NCBI's 9,999-record cap, or exact
abstract/DOI parsing — all of which needed custom fixes.

Steps 1 and 2 need no API key at all, only `PACT_EMAIL`. Andrew can run those
himself. Step 3 needs Austin's token, and **Austin runs the code**, so
correctness and legibility matter more than convenience.

## Run order

```
python3 scripts/01_search.py --per-term    # then stop and read the gate output
python3 scripts/11_neutral_sample.py
python3 scripts/03_screen.py --check       # 1 record, both models
python3 scripts/03_screen.py --limit 20    # read the reasons before the full run
python3 scripts/03_screen.py               # all 500
```

All resumable. Step 3 re-run picks up where it stopped and retries only records
that errored.

## Conventions that must hold

- **Paths.** `scripts/common.py` derives `data/` and `prompts/` from its own
  location, one level up from `scripts/`. Never flatten the tree — flat layout
  writes outputs above the repo root.
- **Seed.** `SEED = 20260828` in `11_neutral_sample.py`. Once step 3 has started,
  changing it invalidates the sample. Do not touch it.
- **Provenance.** Every script writes a `*_manifest.json` with git commit, script
  and prompt SHAs, and timestamp. v7 requires this at every step. Don't remove it,
  and warn if the repo is dirty before a real run.
- **No silent exclusions.** Population and setting exclusions (ICU,
  nursing-only, other specialties) stay out of the PubMed query and are handled at
  screening, where a human can see them. A bare `NOT "Child"[MeSH]` clause deletes
  in-scope mixed-age papers invisibly. The two exceptions, approved 22 Sept 2026,
  are children-only records (guarded with `NOT "Adult"[MeSH]` so mixed-age studies
  survive) and dental records. Don't widen these without a new dated decision.
- **One screening criterion.** `prompts/screen_prompt_v7.txt` (AI) and
  `validation/Lit_Review_Web_Interface.html` (humans) must state the same test. If
  one changes, the other changes. Step 4 measures the AI against the humans, so
  divergent criteria make that comparison meaningless.

## Approved decisions, 28 August 2026

- Drop papers retrieved by both the emergency-medicine and primary-care
  searches from both sampling pools.
- Remove broad `adverse event(s)` and `triage` terms from the PubMed search.
  Specific error terms such as `undertriage` remain, and triage papers can still
  enter through another retained thinking, failure, or coordination term.
- Exclude simulations, vignettes, standardised patients, and chart-stimulated
  recall; real patient care is required.
- Exclude task-difficulty/theory papers with no clinician or
  clinician-behaviour data.
- Restrict `Continuity of Patient Care`[MeSH] and `Referral and Consultation`[MeSH]
  to `[majr]` in the coordination term group, and drop the bare `referral`/
  `consultation` title/abstract terms. Per-term counts showed these terms were
  dominated by generic health-services and referral-logistics papers, not
  cognitive coordination/communication papers. This reads narrower than v7's
  literal list, which names referral and consultation as coordination-group
  content; the tradeoff is recorded with counts in `docs/DECISIONS_2026-08-28.md`.
- The step 1 and 2 outputs were regenerated after these decisions on 28 August
  2026 and are current for screening. See `data/README.md` for counts and status.

## Approved decisions, 22 September 2026

- Remove children-only records from the search, guarded so mixed-age studies stay.
- Remove dental records from the search; dentistry added to the prompt and the
  human interface as out of scope.
- Restrict `"Primary Health Care"[MeSH]` to `[majr]`.
- Evidence: a 20-paper screening trial found 55% of papers were in neither
  setting (64% of the primary-care arm). Details and measured effect in
  `docs/DECISIONS_2026-09-22.md`. Decision id `2026-09-22-search-tightening`.

## Known open issues

- v7 step 2 says batches of 100 are "needed in step 12". Probably a typo for step
  13 (the saturation plot). Unconfirmed.
- The pilot reviewer files label `source_setting` from which query retrieved a
  paper, not from the paper itself. Several were neither ED nor primary care.
  Step 3 records `setting_seen` separately to quantify this.
- Prior pilot: Austin/Anastasia kappa 0.875 on n=20 (one disagreement, fragile).
  Both AI screeners were far more inclusive than either human; AI sensitivity
  0.5–0.83. Over-inclusion is by design; the low sensitivity is not resolved.

## Not in this repo yet

The pilot validation spreadsheets (Austin's, Anastasia's, and the agreement
workbook computing kappa) exist only as a Drive export. They are the calibration
evidence v7 requires reporting. They belong in `validation/`.
