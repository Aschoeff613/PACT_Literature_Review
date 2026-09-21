# PACT literature review: steps 1–3 decisions

Approved 28 August 2026. This file amends protocol v7 for the four decisions
below and provides the methods wording to use when describing steps 1–3. The
protocol PDF remains the baseline for everything not changed here.

## Decisions and implementation

1. **Setting overlap:** remove every PMID retrieved by both the emergency-
   medicine and primary-care searches from both pools before sampling. Record
   the overlap count and rule in the sample manifest.
2. **Broad search vocabulary:** omit `"adverse event"[tiab]`,
   `"adverse events"[tiab]`, bare triage title/abstract terms, and the Triage
   MeSH term. Retain more specific vocabulary such as `undertriage`. These are
   query-term removals, not blanket exclusions: a relevant adverse-event or
   triage paper can still enter through another retained content term.
3. **Simulated care:** exclude vignettes, simulated cases, standardised patients,
   and chart-stimulated recall, even when clinician decisions are studied. Real
   patient care is required.
4. **No clinician data:** exclude task-difficulty or theoretical papers that do
   not contain data about clinicians or clinician behaviour.
5. **Coordination MeSH precision:** restrict `"Continuity of Patient Care"[MeSH]`
   and `"Referral and Consultation"[MeSH]` to `[majr]` (major topic only), and
   drop the bare `"referral"[tiab]` and `"consultation"[tiab]` terms from the
   coordination group. Per-term counts on the live corpus showed
   `"Continuity of Patient Care"[MeSH]` alone returned 57,969 of 94,326
   primary-care coordination hits, with `"referral"[tiab]` (16,869) and
   `"consultation"[tiab]` (11,297) adding further volume — overwhelmingly
   generic health-services and referral-logistics papers, not papers about the
   coordination/communication cognitive task itself. Restricting to `[majr]`
   and dropping the bare tiab terms roughly halved both union queries
   (primary care 103,237 → 58,085; emergency medicine 39,318 → 23,379).
   `Continuity of Patient Care[majr]` still accounts for roughly 70% of the
   primary-care coordination group even after this restriction; that is
   accepted as a real property of that literature rather than restricted
   further. This trades recall (a coordination paper indexed only incidentally
   under these headings, or using "referral"/"consultation" in text without
   formal MeSH indexing, will be missed) for precision in a group that would
   otherwise be dominated by non-cognitive health-services content. This is a
   narrower reading than protocol v7's literal listing of "referral,
   consultation" as coordination-group content terms.

Decisions 1, 2, and 5 operate before sampling, as changes to the PubMed query
itself. Decisions 3–4 operate during title and abstract screening and are
stated identically in the AI prompt and human-review interface.

## Methods summary for steps 1–3

We conducted a bounded PubMed review of English-language papers published from
2005 through 2026 concerning adult emergency medicine or adult primary care.
Each record also had to match retained vocabulary concerning clinician thinking,
failures in care, or coordination and communication. Broad adverse-event and
triage search terms were omitted because preliminary counts showed that they
retrieved large volumes of nonspecific safety and triage-classification work.
Within the coordination and communication group, the Continuity of Patient
Care and Referral and Consultation MeSH headings were restricted to major
topic only, and free-text "referral"/"consultation" terms were dropped,
because preliminary counts showed they were dominated by generic
health-services and referral-logistics papers rather than papers about the
coordination or communication cognitive task itself.

The two setting searches were run separately. Records retrieved by both were
removed from both sampling frames. Using the prespecified seed 20260828, we drew
250 records with usable abstracts from each disjoint setting pool and randomly
interleaved them into a 500-record sample.

Two models from different model families independently screened every title and
abstract. A paper was eligible when it examined what clinicians notice,
interpret, decide, or communicate during real adult emergency or primary care.
Studies based on simulation, vignettes, standardised patients, or
chart-stimulated recall were excluded, as were task-difficulty or theoretical
papers without clinician or clinician-behaviour data. Uncertain cases otherwise
resolved toward inclusion. The search, sampling, code, prompt, model identifiers,
seed, and timestamps were recorded in machine-readable manifests.

## Reporting consequence

The search counts, PMID pools, and 500-paper sample were regenerated after these
changes on 28 August 2026. The current manifests carry decision identifier
`2026-08-28-method-amendment`; older pre-amendment outputs must not be reported
or screened.
