# Targeted literature review protocol

PACT Task 1.1.1, literature stream · Version 1.0, [DATE]

A targeted review, not systematic and not a scoping review. Purpose is to identify named cognitive constructs for a candidate codebook, so the search is defined and documented but not exhaustive, and screening stops at construct saturation rather than at the end of the record set.

---

## 1. Question

Which cognitive processes and cognitively demanding clinical tasks have been named and defined in the literature on physician reasoning in adult emergency medicine and adult primary care, and what failure modes are described for each?

## 2. Construct retention rule

A construct is retained if a source **names it and either defines it or operationalizes it as a measured or coded variable.**

Decided in advance:

- A named bias (anchoring, premature closure) is recorded as a **failure mode**, attached to the construct it degrades, not as a construct itself.
- A clinical activity with no stated cognitive demand (for example "order a CT") is not a construct.
- Umbrella terms with no definition in the source ("clinical intuition", "gestalt") are recorded but flagged `undefined` and are not eligible for the codebook without a second source that defines them.

## 3. Eligibility

| | Include | Exclude |
|---|---|---|
| Type | Empirical studies, reviews, framework and theory papers | Editorials without a framework, conference abstracts, letters |
| Population | Practising physicians, attending or resident | Students only; non-physician clinicians only |
| Setting | Adult ED, adult primary care, general practice; generic physician reasoning where transferable | Paediatric only, ICU only, single inpatient specialty only |
| Content | Meets the retention rule in Section 2 | Clinical outcome studies with no cognitive construct |
| Language | English, Dutch | Other |
| Dates | 1990 to present | Pre-1990 unless a seed or cited by one |

Date rationale: the naturalistic decision making and dual-process literature these constructs descend from postdates the late 1980s. Pre-1990 landmarks enter through citation chasing rather than through the database search.

## 4. Sources

**PubMed/MEDLINE** and **Embase** for the clinical literature. **PsycINFO** for cognitive psychology, macrocognition, and naturalistic decision making, which MEDLINE indexes poorly and which is where a large share of these constructs originate. **ACM Digital Library** and **IEEE Xplore** for automation bias and human-AI interaction constructs, which mostly appear in CS venues. Hand search of human factors book chapters, recorded as a separate grey stratum.

## 5. Search strings

Run verbatim in PubMed. Counts are as of 3 August 2026; record your own on the day you run them.

**Strand 1, cognition in setting.** 2,555 records.

```
("Clinical Reasoning"[MeSH] OR "Clinical Decision-Making"[MeSH] OR "clinical reasoning"[tiab]
OR "diagnostic reasoning"[tiab] OR "cognitive task analysis"[tiab] OR macrocognition[tiab]
OR "naturalistic decision making"[tiab] OR sensemaking[tiab] OR "situation awareness"[tiab]
OR metacognition[tiab] OR "cognitive load"[tiab])
AND
("Emergency Medicine"[MeSH] OR "Emergency Service, Hospital"[MeSH] OR "Primary Health Care"[MeSH]
OR "General Practice"[MeSH] OR "emergency department"[tiab] OR "primary care"[tiab]
OR "general practice"[tiab])
```

**Strand 2, failure modes in setting.** 5,158 records.

```
("Diagnostic Errors"[MeSH] OR "diagnostic error"[tiab] OR "diagnostic errors"[tiab]
OR "cognitive bias"[tiab] OR "cognitive biases"[tiab] OR "premature closure"[tiab]
OR "anchoring bias"[tiab] OR "therapeutic inertia"[tiab] OR "clinical inertia"[tiab]
OR "missed diagnosis"[tiab])
AND
("Emergency Medicine"[MeSH] OR "Emergency Service, Hospital"[MeSH] OR "Primary Health Care"[MeSH]
OR "General Practice"[MeSH] OR "emergency department"[tiab] OR "primary care"[tiab]
OR "general practice"[tiab])
```

**Strand 3, cognition crossed with failure.** 893 records. Highest construct density per record; screen this strand first.

```
("Clinical Reasoning"[MeSH] OR "Clinical Decision-Making"[MeSH] OR "clinical reasoning"[tiab]
OR "diagnostic reasoning"[tiab] OR "cognitive task analysis"[tiab] OR macrocognition[tiab]
OR metacognition[tiab])
AND
("Diagnostic Errors"[MeSH] OR "diagnostic error"[tiab] OR "cognitive bias"[tiab]
OR "premature closure"[tiab] OR "dual process"[tiab])
```

**Strand 4, human-AI interaction.** 2,885 records.

```
("automation bias"[tiab] OR "trust calibration"[tiab] OR "appropriate reliance"[tiab]
OR "Decision Support Systems, Clinical"[MeSH] OR "large language model"[tiab]
OR "large language models"[tiab])
AND
("clinical reasoning"[tiab] OR "diagnostic reasoning"[tiab] OR "Clinical Decision-Making"[MeSH]
OR "Diagnostic Errors"[MeSH] OR "emergency department"[tiab] OR "primary care"[tiab])
```

**Adaptations.** In Embase, swap MeSH for the Emtree equivalents and `[tiab]` for `:ti,ab`. In PsycINFO, run Strand 1 term block alone without the setting block, which otherwise strangles the yield, and add `"clinical judgment"` and `"expert systems"`. In ACM and IEEE, run the Strand 4 term block alone.

**Citation chasing.** Backward and forward from the seed set and from every included review or framework paper. One generation. Stop earlier if a generation yields no new construct.

## 6. Seed set

Fixed before searching. All verified against PubMed.

| Source | Construct territory |
|---|---|
| Graber, Franklin, Gordon. *Arch Intern Med.* 2005;165(13):1493-1499. doi:10.1001/archinte.165.13.1493 | Cognitive taxonomy of diagnostic error; premature closure, faulty synthesis |
| Croskerry, Singhal, Mamede. *BMJ Qual Saf.* 2013;22(Suppl 2):ii58-ii64. doi:10.1136/bmjqs-2012-001712 | Dual-process theory; bias origins and debiasing |
| Croskerry. *Diagnosis (Berl).* 2014;1(1):23-27. doi:10.1515/dx-2013-0028 | Metacognition; bias as normal operating characteristic |
| Schubert, Denmark, Crandall, Grome, Pappas. *Ann Emerg Med.* 2013;61(1):96-109. doi:10.1016/j.annemergmed.2012.08.034 | Macrocognition; novice-expert sensemaking in the ED |
| Graham, Gray, Wagner, et al. *Health Serv Res.* 2023;58(2):415-422. doi:10.1111/1475-6773.14106 | Cognitive task analysis method |
| Walter, Raban, Dunsmuir, Douglas, Westbrook. *Appl Ergon.* 2016;58:454-460. doi:10.1016/j.apergo.2016.07.020 | Interruption, task-switching, multitasking, workload strategy |
| Zwaan, Rodman, Shimizu. *NEJM AI.* 2026;3(5). doi:10.1056/AIe2600354 | Human-AI interaction strategy; trust calibration |
| Bedi, Liu, Orr-Ewing, et al. *JAMA.* 2025;333(4):319-328. doi:10.1001/jama.2024.21700 | What current benchmarks measure and omit |

## 7. Screening

Deduplicate across databases, then screen by strand in relevance-sorted batches of 100, Strand 3 first, then 1, 4, 2.

**Stopping rule: stop a strand after two consecutive batches yield no new canonical construct.** Record the batch number where each strand stopped and the number of records left unscreened. This is what makes the review targeted rather than incomplete, so report both numbers rather than implying full coverage.

Two reviewers independently screen the first batch of Strand 3, compute Cohen's kappa, and reconcile. If kappa is below 0.6, revise Section 2 or 3 and recalibrate. After that, one reviewer screens and the second reviews all inclusions plus any exclusion marked uncertain.

Screening is not blind to the candidate constructs already generated in the model-elicitation phase. State this in the write-up.

## 8. Extraction

One row per construct per source.

`construct label as given` · `verbatim definition` · `citation` · `altitude: cognitive process or clinical task` · `setting studied` · `operationalization, if any` · `associated failure modes` · `produced in model-elicitation phase? Y/N` · `flags: undefined`

Definitions extracted verbatim, not paraphrased.

## 9. Synthesis

Map surface labels to canonical constructs in a synonym table, keeping original labels so merges can be checked. Classify every canonical construct by altitude.

Then cross-tabulate provenance:

| | In literature | Not in literature |
|---|---|---|
| **Produced by models** | Corroborated; core of the codebook | Unsupported; report count and drop |
| **Not produced by models** | Model coverage gaps | n/a |

Also report the number of model-supplied citations that failed bibliographic verification.

## 10. Reported in the manuscript

Search strings with database, interface, and date run. Records screened and left unscreened per strand, with the saturation batch. Calibration kappa. Canonical construct list with definitions and sources. Synonym table. Provenance table. Discarded constructs with reasons. One Methods sentence giving the true order: model elicitation first, targeted review second, designed to verify and extend rather than to generate.
