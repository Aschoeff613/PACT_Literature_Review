# PACT rapid targeted literature review protocol

PACT Task 1.1.1, literature stream · Version 1.1, 6 August 2026

This is a rapid targeted taxonomy-validation review. It is not a systematic review
or scoping review, does not claim exhaustive coverage, and does not require duplicate
full-text screening or duplicate extraction.

## 1. Purpose

Identify published adult emergency-medicine and primary-care studies that directly
examine clinician reasoning, decision-making, communication, or judgment-dependent
work. Use this evidence to check the final 17-task PACT taxonomy and identify possible
gaps.

## 2. Operational inclusion rule

Ask what the paper is actually studying.

Include when clinician reasoning, choices, behavior, communication, or another
judgment-dependent clinical process is an object of study. The paper should contain
both:

1. a cognitive task—the thinking or communication itself; and
2. a clinical task—the care activity where that thinking occurs.

Exclude when the paper only evaluates a disease, treatment, test, risk score,
prevalence, safety outcome, or patient outcome while clinician work is incidental.

Examples:

- “Is antibiotic A more effective than antibiotic B?” — exclude.
- “Why do clinicians select antibiotic A rather than antibiotic B?” — include.
- “How often does antibiotic A cause adverse effects?” — exclude.
- “Does a decision-support alert change antibiotic selection?” — include.

When genuinely uncertain at abstract screening, include for later review.

## 3. Eligibility

| | Include | Exclude |
|---|---|---|
| Setting | Adult emergency medicine or adult primary care; admission, discharge, or transition work linking them | Pediatric, ICU or established inpatient care, prehospital, nursing-only, or specialty-only work |
| Content | Empirical examination of clinician cognition, decisions, communication, or judgment-dependent workflow | Treatment/test efficacy or safety only; prevalence or outcomes only; no clinician cognitive work studied |
| Publication | Empirical studies and reviews with an applicable clinical process | Case reports, editorials, comments, letters, education-only studies |
| Language | English | Other languages |
| Dates | 2005–2026 | Outside this range |

## 4. Source and search

PubMed is the sole database for this bounded targeted scan. Emergency medicine and
primary care were searched separately. Each setting block was crossed with broad
clinician-cognition terms or diagnostic-error and patient-safety signals.

The search did not contain the names of the 17 PACT tasks. It was therefore
category-neutral relative to the final taxonomy, although it was intentionally seeded
with broad cognition and safety terminology.

The exact queries and counts are preserved in `data/11_neutral_sample_log.csv`.

| Setting | PubMed results | Random sample target | Usable records |
|---|---:|---:|---:|
| Emergency medicine | 2,878 | 250 | 250 |
| Primary care | 3,026 | 250 | 249 |
| **Total** | — | **500** | **499** |

Sampling used the fixed seed `20260803`. One sampled PubMed identifier did not return
usable record details, leaving the 499-record bounded corpus.

## 5. AI abstract screening

GPT and Claude independently screened all 499 titles and abstracts using the same
operational boundary. A record was provisionally retained when either model said
include.

- At least one model included: 214
- Both models excluded: 285

These AI results were used to build the human-validation strata. They were not shown
as decisions in the reviewer interface.

## 6. Human-validation sample

The 300-paper sample was drawn in four equal cells:

| AI stratum | Emergency medicine | Primary care | Total |
|---|---:|---:|---:|
| At least one AI included | 75 | 75 | 150 |
| Both AIs excluded | 75 | 75 | 150 |
| **Total** | **150** | **150** | **300** |

The 300 records were shuffled after sampling. This enrichment provides a practical
check for missed papers. It must not be used to estimate the prevalence of relevant
studies in the original PubMed results.

## 7. Four-reviewer assignment and agreement

Four people each review 150 abstracts, producing two independent decisions per paper:

- Reviewers 1 and 2: records 1–150
- Reviewers 3 and 4: records 151–300

Before independent review, all four discuss 5–10 practice abstracts. Formal decisions
are then made independently. `scripts/12_merge_human_reviews.py` merges the four
exports, calculates percent agreement and Cohen’s kappa for each reviewer pair, and
creates a disagreement file. Agreements become the consensus decision; only
disagreements are adjudicated.

The browser hides model decisions but displays optional AI-assisted amber evidence
cues. The method is therefore described as AI-assisted human validation, not fully
AI-blinded validation.

## 8. Rapid abstract mapping

After adjudication:

1. Use the final human decision for the 300 reviewed papers.
2. For the remaining 199 papers, retain those included by either AI model, provided
   the validation result is adequate for this targeted purpose.
3. Run `scripts/13_rapid_abstract_map.py` once. One model maps each retained abstract
   to one to three of the final 17 tasks.
4. For every mapped paper, retain the concrete clinical task, taxonomy task IDs, an
   exact supporting abstract sentence, confidence, and a possible-new-task flag.
5. One human scans the table and corrects obvious errors.

The final taxonomy names and definitions used for mapping are version-controlled in
`taxonomy/pact_17_tasks.json`.

## 9. Selective full-text retrieval

There is no routine full-text review of every retained paper. Retrieve a PDF only when:

- the abstract is too vague to map confidently;
- the paper may describe cognitive work outside the 17-task taxonomy; or
- an especially important paper requires stronger supporting detail.

The abstract-mapping script writes these papers to `data/13_pdf_shortlist.csv`. A human
checks any extracted full-text evidence. There is no second large human-validation
round and no duplicate full-text extraction.

## 10. Deliverable and reporting

The deliverable is a compact evidence table grouped by the final 17 cognitive tasks.
Each row contains the citation, setting, clinical task, mapped cognitive task, exact
supporting sentence, and human-check fields. Possible new tasks are reviewed separately
rather than forced into the taxonomy.

Report this accurately as a rapid targeted taxonomy-validation review. State the
PubMed-only source, search dates, bounded 499-record corpus, stratified 300-paper
validation sample, four-reviewer assignment, agreement and adjudication counts,
inclusive AI rule for remaining records, AI-assisted evidence cues and mapping, and
number of selectively retrieved PDFs. Do not imply exhaustive coverage.
