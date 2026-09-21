# PACT literature review — steps 1 to 3

Built against **protocol v7, 18 August 2026**, as amended for steps 1–3 by the
approved decisions in `docs/DECISIONS_2026-08-28.md`. Where these sources and
the older `README.md` / `protocol.md` disagree, v7 plus the dated amendment win,
and the divergence is noted below.

Screening runs through **OpenRouter**, one key for both models.

---

## Setup

```
cd <repo>
export PACT_EMAIL="aschoeff@stanford.edu"          # NCBI requires a contact address
export OPENROUTER_API_KEY="sk-or-..."              # Austin's token
export NCBI_API_KEY="..."                          # optional, 3/sec -> 10/sec
```

No third-party packages. Python 3.8+.

Get an NCBI key if you can (NCBI account → Settings → API Key Management). It is
free and roughly triples search speed.

---

## Run order

```
python3 scripts/01_search.py --per-term      # ~5 min. Do this first, once.
                                             # then read the gate output
python3 scripts/11_neutral_sample.py         # ~2 min
python3 scripts/03_screen.py --check         # 1 record, both models
python3 scripts/03_screen.py --limit 20      # read the reasons before spending
python3 scripts/03_screen.py                 # all 500
```

Everything is resumable. If step 3 dies or you close the laptop, run it again
and it picks up where it stopped, retrying only records that errored.

---

## Step 1 — search

Protocol v7 wants: adult EM **or** primary care, AND at least one of three term
groups (how clinicians think / where things go wrong / coordination and
communication). English, 2005 to 2026.

Two queries, one per setting, each `setting AND (A OR B OR C) AND filters`. Two
rather than one because step 2 draws 250 from each setting separately, and
because the step 1 gate asks for per-setting counts.

**Outputs**

| File | What |
|---|---|
| `01_search_log.csv` | the two union queries verbatim, with hit counts |
| `01_counts_by_group.csv` | 6 rows: setting × term group |
| `01_counts_by_term.csv` | every individual term, counted alone (with `--per-term`) |
| `01_pmids_<setting>.csv` | the full PMID list per setting |
| `01_run_manifest.json` | git version, script hashes, timestamp, counts |

**The gate.** v7 says confirm the coordination terms return a usable number. The
script prints that. `--per-term` is the honest version: it shows which
individual terms carry the query and which return zero. A typo in a MeSH term
does not raise an error in PubMed, it silently returns 0, so this is the only
way to catch one.

### Decisions applied to the search

1. **Broad adverse-event and triage terms are removed.** The broad
   `"adverse event"[tiab]`, `"adverse events"[tiab]`, bare triage title/abstract,
   and Triage MeSH terms pulled large amounts of drug-safety and triage-scale
   validation work. They were removed by the approved 28 August decision.
   Specific error vocabulary such as `undertriage` remains. A triage paper can
   still be retrieved when it matches another retained content term.
2. **Coordination is new.** It does not exist in any strand of the shipped
   `01_search.py`. If it returns few records, that is a finding about v7's
   third term group, not a bug to hide.
3. **Date change.** v7 says 2005–2026; the old code said 1990–2026. I used v7's.
   Worth knowing that this cuts the naturalistic-decision-making and
   dual-process foundations the constructs descend from, which the old
   `protocol.md` handled through citation chasing. v7 has no citation chasing.
   That is a real narrowing and belongs in the limits section.

### Deliberate departures from the shipped code

- **PMIDs only, no metadata.** The old script downloaded title and abstract for
  all 11,206 hits. The v7 union queries will return more than that, and step 2
  needs 500 of them. Step 1 pulls identifiers (seconds); step 2 fetches metadata
  for the 500 actually drawn. Same result, minutes instead of hours.
- **Exclusions split between query and screen.** Publication type, language and
  date go in the query, because PubMed indexes them reliably. Paediatrics, ICU,
  nursing-only, education-only and patient-thinking papers do **not**. A
  `NOT "Child"[MeSH]` clause silently deletes in-scope papers that mention
  children once, and nobody downstream can see it happened. Step 3 handles those,
  and its instruction is to include when uncertain. Cost of this choice: the
  corpus contains out-of-scope records and the screen has to remove them. That
  is the right place for the error to live, because it is visible there.

---

## Step 2 — draw the sample

250 EM + 250 primary care, seeded, numbered in batches of 100.

**Seed: 20260828.** Fixed in the script. Do not change it once step 3 has
started. `11_sample_manifest.json` records it along with every draw decision;
commit that file.

v7 leaves three things unspecified. I decided them and made them reportable.

**1. Papers matching both settings.** A paper can match both setting blocks. The
approved rule drops every overlapping PMID from both pools before sampling, so
the setting samples are disjoint. The manifest reports the overlap count and
the `drop` rule.

**2. Records with no abstract.** About 8% of this corpus has none, and step 3
screens on title and abstract. The draw takes a 30% oversample in seeded order,
fetches metadata, drops records with no usable abstract, and keeps the first 250
that survive. Deterministic, and the count dropped is written to
`11_sample_skipped.csv`. The rule is fixed before the draw, so it is not a
post-hoc exclusion. In the pilot, the reviewers simply excluded the no-abstract
record (PMID 32188711), which wastes a slot and adds a meaningless exclude to
the agreement statistics.

**3. Ordering.** The 500 are interleaved by the seeded shuffle, not stacked by
setting. If they were stacked, every step 4 reviewer block would be
single-setting and a reviewer effect would be indistinguishable from a setting
effect.

`block_50` is also emitted alongside `batch_100`, since step 4 needs blocks of
50 for the six reviewers and step 9 needs batches of 50 for clustering. v7 step 2
says the batches of 100 are "needed in step 12", which I think is a typo — step
12 does not reference batches, and step 13's saturation plot is the thing plotted
against batch number. Worth confirming with Austin.

**Verified:** re-running with the same seed reproduces an identical 500-paper
sample, 250 per setting, no duplicate PMIDs, both settings present in every
batch and block.

---

## Step 3 — AI screening

Two models, each reading all 500 titles and abstracts independently, via
OpenRouter.

### Model IDs

Set at the top of `03_screen.py`, overridable without editing the file:

```
export PACT_MODEL_A="vendor/model"
export PACT_MODEL_B="othervendor/model"
```

The defaults are placeholders. **Check them against openrouter.ai/models before
running.** `--check` fails on call one if either ID is wrong, which is the whole
point of `--check`.

Pick the two from **different families**. Two models from one family share
training data and failure modes, so their agreement measures shared bias, not
correctness. Report their agreement as a description; step 4 is the validation.
The shipped README already says this and it is right.

### The prompt

`prompts/screen_prompt_v7.txt` is new. The old `screen_prompt.txt` asks models to
find papers that **name and define a cognitive construct**, which is not v7's
criterion. v7 step 3 says a paper is in scope when it **actually examines what a
clinician notices, decides, interprets, or communicates**. Those are different
tests, and the old one is narrower.

This matters for the pilot numbers. The human reviewers used the criteria in the
web interface (cognitive task + clinical task requiring judgment, with the
antibiotic A/B contrasts). The AI used `screen_prompt.txt`. **They were given
different rules**, so some of that AI/human disagreement is a specification
mismatch, not model error. The new prompt uses v7's test as the headline and
imports the interface's worked contrasts, which are the best operationalisation
anyone has written down. One criterion, three places.

**Two boundary rules are written into the prompt explicitly**, because they are
what the pilot actually got stuck on. Both were resolved toward exclusion on
28 August 2026:

- **Simulation and standardised patients** are out of scope, including
  vignettes, simulated cases, chart-stimulated recall, and standardised-patient
  encounters. The review now requires real patient care.
- **Task-difficulty papers with no clinician data** are out of scope. A paper
  must contain evidence about clinicians or clinician behaviour; theoretical
  task analysis, tool evaluation, or outcomes alone are insufficient.

The same exclusions are stated in the human reviewer interface so step 4 tests
the AI and humans against one criterion.

### Provenance

v7 says: record which prompt file and which version of the code were used.
Automated rather than remembered. Every run writes `03_screen_manifest.json` with
the git commit, SHA-256 of the script, of `common.py` and of the prompt file, the
two model IDs, the endpoint and a UTC timestamp. If the repo has uncommitted
changes, the version string says `-dirty` and the script warns you. Commit before
a real run so the stamp means something.

### Extra column worth having

Each model also reports `setting_seen`: its read of what setting the **paper** is
in, independent of which query retrieved it. This is not used to decide anything.
It exists because in the pilot, several records labelled `source_setting: primary
care` were neither PC nor ED — deformity spine surgery, hip and knee
arthroplasty, an HIV-testing EMR study — and both reviewers excluded them on
setting grounds. Those labels are query provenance, not validated setting.

If the `setting_mismatch` count comes back large, that is important before step
4: the balanced 300-paper check would then be partly measuring "can you tell this
isn't ED or primary care" rather than "can you tell this has cognitive content",
which flatters the AI screen. The script prints the count.

### Cost

Roughly 5% of the token volume the old README budgeted for, because that design
screened all 10,767 records and v7 screens 500. Screening is now cents. The
README's cost table describes the superseded design; don't quote it. Extraction
becomes the dominant cost from step 7 onward.

---

## What to check before step 4

1. `01_counts_by_term.csv` — any term returning 0 is a typo; any term dominating
   its group is a sampling problem.
2. Coordination group counts. New in v7, and the whole third of the search.
3. `11_sample_skipped.csv` — how many records lost to missing abstracts.
4. Skim 20 rows of `a_reason` / `b_reason`. Cheapest possible signal that the
   prompt is being read the way you meant.
5. The `setting_mismatch` count.
6. Whether the two models' include rates are wildly different. In the pilot GPT
   flagged 9 and Claude 7 against a human consensus of 5–6. Over-inclusion is by
   design; a large gap **between** the two models is not, and points at one of
   them not following the prompt.
7. Commit `01_search_log.csv`, all three manifests, the prompt file, and the
   scripts. Not the PMID lists or the screening CSV.

## Open questions for Austin

- Is `batch_100` really needed in step 12, or is that step 13's saturation plot?
- 2005 as the start date, given v7 has no citation chasing to recover the
  pre-2005 foundations?
- Which two OpenRouter models, and is there a budget ceiling on the token?
