# PACT literature review — running the pipeline (protocol v7)

Steps 1–3 were built by Andrew (Aug 2026) and amended by
`docs/DECISIONS_2026-08-28.md` and `docs/DECISIONS_2026-09-22.md`. Steps 4–13
were rebuilt against protocol v7 on 22 Sept 2026; the earlier scripts for those
steps followed a superseded design and did not run against the rewritten
steps 1–3.

Script numbers are historical and do not match protocol step numbers. This
table is the map.

| v7 step | What | Who | Script | Model spend |
|---|---|---|---|---|
| 1 | PubMed search | script | `01_search.py` | none |
| 2 | Draw the sample (2,000; decision 9) | script | `11_neutral_sample.py` | none |
| 3 | AI screening, two models | script | `03_screen.py` | **done: $18.90** |
| 4 | Human check of the screen, 300 papers | **6 reviewers** | `04_validate_sample.py` builds the pages | none |
| 5 | Merge reviewers, adjudicate | script + **third person** | `12_merge_human_reviews.py` | none |
| 6 | Can the AI screen be trusted? | **team decides tier** | `07_metrics.py` | none |
| 7 | Extract tasks | script (+ **manual full-text fetch**) | `06_extract.py`, `05_fulltext.py` | ~$12–17 |
| 8 | Check extracted tasks, 120 rows | **2 reviewers** | `14_extraction_check.py` | none |
| 9–10 | Grouping, two rounds | script | `08_cluster.py` | ~$2 |
| 11 | Check the combining, ~60 pairs; **lock** | **2 reviewers + tiebreaker** | `15_grouping_check.py` | none |
| 12 | Do the groups hold together? | reviewers | `16_intrusion_check.py` | none |
| 13 | Saturation plot; stability | script | `17_summary_checks.py` | ~$4 |

Spend so far (screening plus pipeline testing): **$21.19 of the $50 ceiling.**
Remaining estimate ~$18–23, so the ceiling holds with a margin of roughly
$6–10. Every script from step 7 on checks total spend on the key before each
batch and stops before crossing `PACT_BUDGET_USD` (default 50).

## Setup (once per terminal)

```sh
cd ~/PACT_Literature_Review
set -a; . ./.env; set +a      # PACT_EMAIL, OPENROUTER_API_KEY, model names
```

## Run order

**Step 4.** Already built. Send each reviewer their page from
`validation/step4/` (`review_R1.html` … `review_R6.html`) and everyone
`review_warmup.html` first. Pages open in any browser, work offline, and
**do not save** — reviewers must press *Export CSV* before closing, and can
resume later with *Resume from file*. Pages carry no AI decisions.

**Step 5.**
```sh
python3 scripts/12_merge_human_reviews.py step4_review_R*.csv
```
The third person fills `adjudicated_decision` in `data/05_adjudication.csv`;
re-run the same command. Agreement per pair: `data/05_agreement_by_pair.csv`.

**Step 6.**
```sh
python3 scripts/07_metrics.py                         # read the report
python3 scripts/07_metrics.py --decision as_is        # or missed_some / missed_a_lot
```
Use the **"estimated for whole sample"** figure, not the "in the 300" figure:
the 300 are half AI-kept by design, so the raw figure flatters the AI.

**Step 7.**
```sh
python3 scripts/06_extract.py --workers 4
python3 scripts/05_fulltext.py
#   ...save any manual full texts as data/fulltext/<pmid>.txt ...
python3 scripts/06_extract.py --fulltext --workers 4
```

**Step 8.**
```sh
python3 scripts/14_extraction_check.py build          # sheets in validation/step8/
python3 scripts/14_extraction_check.py apply validation/step8/check_A.csv validation/step8/check_B.csv
```

**Steps 9–10.** `python3 scripts/08_cluster.py`

**Step 11.**
```sh
python3 scripts/15_grouping_check.py build            # sheets in validation/step11/
python3 scripts/15_grouping_check.py apply validation/step11/pairs_A.csv validation/step11/pairs_B.csv
```
Disagreements go to `data/11_tiebreak.csv`; re-run after the tiebreaker
fills it. This locks the list (`data/11_lock.json`). Steps 12 and 13 refuse
to run if the locked list is edited afterwards.

**Step 12.**
```sh
python3 scripts/16_intrusion_check.py build           # sheets in validation/step12/
python3 scripts/16_intrusion_check.py score validation/step12/items.csv -- validation/step12/name_fit.csv
```

**Step 13.**
```sh
python3 scripts/17_summary_checks.py saturation
python3 scripts/17_summary_checks.py stability
```

## Decisions the team needs to make — ideally before step 4 finishes

1. **Who are R1–R6**, and who is the step 5 adjudicator.
2. **The step 6 tier.** If the result is "AI missed some", the protocol has a
   human check every AI-dropped paper not already checked. With the 2,000
   sample that is **1,621 papers** (it was about 200 under the original 500).
   Decide in advance whether that workload is acceptable.
3. **Full text is the norm, not the exception.** v7 keeps a task only if the
   paper *names and defines* it. In testing, all 8 trial abstracts named
   tasks without defining them and were flagged for full text. About 60%
   came from PubMed Central automatically; the rest need someone to save the
   paper as text (free links are listed where they exist). Expect roughly
   80–100 manual retrievals. The alternative — relaxing "defines" for
   abstracts — would be a protocol amendment.
4. **Step 11 tiebreaker**, named before the reviewers start.
5. **Step 12 threshold.** The script flags a task as weak when its hit rate
   is not distinguishable from chance (one-sided binomial, p > 0.05). With 10
   items that means a task needs **7 or more** correct. v7 says "most of the
   time" and says to agree the rule in advance; confirm or change this before
   scoring.

## Things learned in testing (22 Sept 2026)

- **Hidden model reasoning is switched off** for every call from step 7 on.
  Left on, Claude Sonnet 5 spent entire replies reasoning on long papers and
  returned empty answers while billing every token, and ignored a reasoning
  cap. With reasoning off, the same paper returned 10 complete rows for about
  a third of the cost. The 9 malformed replies during step 3 screening were
  probably the same effect; all resolved on retry.
- **Quote verification** classes every quote as `verbatim`, `too_short`
  (found, but under 6 words — e.g. checklist items) or `not_found`
  (paraphrased or invented). In 29 test rows: 26 verbatim, 3 too short, 0 not
  found. Only verbatim rows go on to grouping.
- **The step 4 master file stays out of the public repo** until the reviews
  are done: it holds the AI decisions for the 300 validation papers.

## Test mode

Any script can run against a scratch copy of the data without touching the
real outputs:

```sh
PACT_DATA_DIR=/tmp/pact_test python3 scripts/<script>.py ...
```
Reviewer sheets then go to `/tmp/pact_test/_validation/` instead of
`validation/`.

## Superseded, kept for the record

`00_diagnose_api.py`, `02_dedupe.py`, `09_crosswalk.py`,
`10_targeted_search.py`, `13_rapid_abstract_map.py`, `split_reviewer_html.py`,
`templates/pact_reviewer_template.html`, the root
`pact_validation_review_*.html` pages, and `prompts/screen_prompt.txt`,
`extract_prompt.txt`, `neutral_inductive_screen_prompt.txt`,
`rapid_abstract_map_prompt.txt`, `targeted_screen_prompt.txt`. They follow the
earlier design. The comparison against the PACT task list
(`taxonomy/pact_17_tasks.json`) happens only after step 11 locks the list, and
is not part of steps 1–13.
