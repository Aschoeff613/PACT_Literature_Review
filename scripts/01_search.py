"""
STEP 1 - Search PubMed.

Protocol v7, step 1. Papers must be about adult emergency medicine OR adult
primary care, AND involve at least one of three term groups:

    A. how clinicians think
    B. where things go wrong
    C. coordination and communication

Structure of the search
-----------------------
Two queries, one per setting:

    (setting terms) AND (group A OR group B OR group C) AND filters

Two rather than one because step 2 draws 250 papers from emergency medicine and
250 from primary care separately, so the two pools have to exist separately.
This is also what satisfies the step 1 gate: "record how many papers each
setting returns."

What this script does NOT do
---------------------------
It does not download titles and abstracts. It downloads PMIDs only. The union
queries return tens of thousands of records and step 2 only needs 500 of them,
so fetching metadata here would waste hours and produce a file nobody reads.
11_neutral_sample.py fetches metadata for the 500 papers actually drawn.

This is a deliberate departure from the old 01_search.py, which downloaded
every hit. Recorded here so it appears in the methods write-up.

Usage
-----
    python3 scripts/01_search.py                # counts + PMID lists
    python3 scripts/01_search.py --counts-only  # counts only, no PMID download
    python3 scripts/01_search.py --per-term     # also count every term singly

--per-term is worth running once. It tells you which individual terms are
carrying the query and which are contributing nothing, which is the honest
version of "confirm the coordination terms return a usable number."
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, esearch_all_pmids, esearch_count, provenance,
                    require_email, write_csv, write_json)

DECISION_ID = "2026-08-28-method-amendment"

# ---------------------------------------------------------------------------
# Filters applied inside the query
# ---------------------------------------------------------------------------
# Protocol v7 excludes: paediatrics, ICU, other specialties, nursing-only,
# education-only, case reports, editorials, patient-thinking papers.
#
# Only some of those belong in a PubMed query. Publication type, language and
# date are indexed reliably, so they go here. Population and setting exclusions
# do NOT go here: a NOT clause on "Child"[MeSH] or "Intensive Care Units"[MeSH]
# silently drops papers that are squarely in scope but mention children or the
# ICU once. Step 3 screening handles those, and its instruction is to include
# when uncertain. Putting them in the query would be a silent, unrecoverable
# exclusion with no reviewer able to see it.
#
# Consequence to accept: the corpus contains out-of-scope records and the
# screen has to remove them. That is the right place for the error to live.
FILTERS = (
    '("2005"[dp] : "2026"[dp]) '
    'AND English[la] '
    'NOT ("Case Reports"[pt] OR "Editorial"[pt] OR "Comment"[pt] '
    'OR "Letter"[pt] OR "News"[pt] OR "Published Erratum"[pt])'
)

SETTINGS = {
    "emergency_medicine": [
        '"Emergency Medicine"[MeSH]',
        '"Emergency Service, Hospital"[MeSH]',
        '"emergency department"[tiab]',
        '"emergency departments"[tiab]',
        '"emergency physician"[tiab]',
        '"emergency physicians"[tiab]',
        '"emergency medicine"[tiab]',
        '"emergency room"[tiab]',
        '"acute medical unit"[tiab]',
    ],
    "primary_care": [
        '"Primary Health Care"[MeSH]',
        '"General Practice"[MeSH]',
        '"General Practitioners"[MeSH]',
        '"Physicians, Primary Care"[MeSH]',
        '"Physicians, Family"[MeSH]',
        '"primary care"[tiab]',
        '"general practice"[tiab]',
        '"general practitioner"[tiab]',
        '"general practitioners"[tiab]',
        '"family medicine"[tiab]',
        '"family practice"[tiab]',
        '"family physician"[tiab]',
        '"family physicians"[tiab]',
        '"outpatient clinic"[tiab]',
    ],
}

# ---------------------------------------------------------------------------
# The three term groups, transcribed from protocol v7 step 1.
# ---------------------------------------------------------------------------
TERM_GROUPS = {
    # A. How clinicians think.
    "thinking": [
        '"Clinical Reasoning"[MeSH]',
        '"Clinical Decision-Making"[MeSH]',
        '"Judgment"[MeSH]',
        '"Uncertainty"[MeSH]',
        '"Delayed Diagnosis"[MeSH]',
        '"clinical reasoning"[tiab]',
        '"diagnostic reasoning"[tiab]',
        '"clinical judgment"[tiab]',
        '"clinical judgement"[tiab]',
        '"clinical decision making"[tiab]',
        '"clinical gestalt"[tiab]',
        '"gestalt"[tiab]',
        '"clinical intuition"[tiab]',
        '"diagnostic uncertainty"[tiab]',
        '"tolerance of uncertainty"[tiab]',
        '"cognitive load"[tiab]',
        '"cognitive burden"[tiab]',
        '"situation awareness"[tiab]',
        '"situational awareness"[tiab]',
        '"sensemaking"[tiab]',
        '"metacognition"[tiab]',
        '"macrocognition"[tiab]',
        '"naturalistic decision making"[tiab]',
        '"cognitive task analysis"[tiab]',
        '"dual process"[tiab]',
        '"cognitive bias"[tiab]',
        '"cognitive biases"[tiab]',
        '"anchoring bias"[tiab]',
        '"premature closure"[tiab]',
        '"availability bias"[tiab]',
        '"confirmation bias"[tiab]',
        '"missed diagnosis"[tiab]',
        '"delayed diagnosis"[tiab]',
        '"diagnostic delay"[tiab]',
    ],
    # B. Where things go wrong.
    "failure": [
        '"Diagnostic Errors"[MeSH]',
        '"Medical Errors"[MeSH]',
        '"Malpractice"[MeSH]',
        '"Failure to Rescue, Health Care"[MeSH]',
        '"diagnostic error"[tiab]',
        '"diagnostic errors"[tiab]',
        '"medical error"[tiab]',
        '"medical errors"[tiab]',
        '"misdiagnosis"[tiab]',
        '"misdiagnosed"[tiab]',
        '"malpractice"[tiab]',
        '"malpractice claim"[tiab]',
        '"malpractice claims"[tiab]',
        '"near miss"[tiab]',
        '"near misses"[tiab]',
        '"undertriage"[tiab]',
        '"under-triage"[tiab]',
        '"failure to rescue"[tiab]',
        '"preventable harm"[tiab]',
        '"preventable adverse"[tiab]',
    ],
    # C. Coordination and communication.
    # This group does not exist at all in the old 01_search.py. It is the
    # single largest substantive change in v7's search.
    #
    # 2026-08-28: per-term counts showed "Continuity of Patient Care"[MeSH]
    # (57,969 of 94,326 primary_care hits), "referral"[tiab] (16,869),
    # "consultation"[tiab] (11,297) and "triage"[tiab]/"Triage"[MeSH] swamping
    # this group with generic health-services papers, not cognitive
    # coordination/communication papers. Restricted the three MeSH terms to
    # [majr] (major topic, not incidental) and dropped the bare
    # referral/consultation/triage tiab terms, which have no majr equivalent
    # and would otherwise swamp the group regardless. The Triage MeSH/tiab
    # removal is approved decision 2; the majr restriction on Continuity of
    # Patient Care / Referral and Consultation and the dropped bare
    # referral/consultation terms are approved decision 5. The failure group
    # likewise drops the broad "adverse event(s)" title/abstract terms
    # (decision 2). Specific terms such as undertriage remain. All of these
    # are recorded in docs/DECISIONS_2026-08-28.md.
    "coordination": [
        '"Patient Handoff"[MeSH]',
        '"Continuity of Patient Care"[majr]',
        '"Referral and Consultation"[majr]',
        '"Decision Making, Shared"[MeSH]',
        '"Patient Care Planning"[MeSH]',
        '"handoff"[tiab]',
        '"handoffs"[tiab]',
        '"hand-off"[tiab]',
        '"handover"[tiab]',
        '"handovers"[tiab]',
        '"care transition"[tiab]',
        '"care transitions"[tiab]',
        '"transition of care"[tiab]',
        '"transitions of care"[tiab]',
        '"test result follow-up"[tiab]',
        '"test result followup"[tiab]',
        '"missed test result"[tiab]',
        '"missed test results"[tiab]',
        '"result notification"[tiab]',
        '"shared decision making"[tiab]',
        '"shared decision-making"[tiab]',
        '"goals of care"[tiab]',
        '"interruption"[tiab]',
        '"interruptions"[tiab]',
        '"communication failure"[tiab]',
        '"communication failures"[tiab]',
        '"communication breakdown"[tiab]',
        '"disposition decision"[tiab]',
        '"disposition decisions"[tiab]',
        '"alert override"[tiab]',
        '"alert overrides"[tiab]',
        '"alert fatigue"[tiab]',
    ],
}


def block(terms):
    return "(" + " OR ".join(terms) + ")"


def query(setting, groups=None):
    """setting AND (one or more term groups) AND filters."""
    groups = groups or list(TERM_GROUPS)
    content = "(" + " OR ".join(block(TERM_GROUPS[g]) for g in groups) + ")"
    return f"{block(SETTINGS[setting])} AND {content} AND ({FILTERS})"


def main():
    require_email()
    counts_only = "--counts-only" in sys.argv
    per_term = "--per-term" in sys.argv

    prov = provenance(os.path.abspath(__file__))
    log, group_counts, term_counts, pool = [], [], [], {}

    print("\n=== Term group counts per setting (the step 1 gate) ===")
    for setting in SETTINGS:
        for g in TERM_GROUPS:
            n = esearch_count(query(setting, [g]))
            group_counts.append({"setting": setting, "term_group": g, "hits": n})
            print(f"  {setting:20s} {g:14s} {n:>8,}")

    if per_term:
        print("\n=== Per-term counts (which terms are actually carrying the query) ===")
        for setting in SETTINGS:
            for g, terms in TERM_GROUPS.items():
                for t in terms:
                    q = f"{block(SETTINGS[setting])} AND {t} AND ({FILTERS})"
                    n = esearch_count(q)
                    term_counts.append({"setting": setting, "term_group": g,
                                        "term": t, "hits": n})
                    flag = "  <- returns nothing" if n == 0 else ""
                    print(f"  {setting:20s} {g:12s} {t:38s} {n:>7,}{flag}")
        write_csv(os.path.join(DATA, "01_counts_by_term.csv"), term_counts,
                  ["setting", "term_group", "term", "hits"])

    print("\n=== Union query per setting ===")
    for setting in SETTINGS:
        q = query(setting)
        if counts_only:
            n = esearch_count(q)
            ids = []
        else:
            print(f"  [{setting}] downloading PMID list")
            ids, n = esearch_all_pmids(q)
            pool[setting] = ids
        print(f"  {setting:20s} {n:>8,} records")
        log.append({"setting": setting, "hits": n, "pmids_downloaded": len(ids),
                    "query": q})

    write_csv(os.path.join(DATA, "01_search_log.csv"), log,
              ["setting", "hits", "pmids_downloaded", "query"])
    write_csv(os.path.join(DATA, "01_counts_by_group.csv"), group_counts,
              ["setting", "term_group", "hits"])

    if not counts_only:
        for setting, ids in pool.items():
            write_csv(os.path.join(DATA, f"01_pmids_{setting}.csv"),
                      [{"pmid": p, "setting": setting} for p in ids],
                      ["pmid", "setting"])

    prov.update({
        "decision_id": DECISION_ID,
        "filters": FILTERS,
        "approved_search_exclusions": [
            '"adverse event"[tiab]',
            '"adverse events"[tiab]',
            '"triage"[tiab]',
            '"Triage"[MeSH/majr]',
        ],
        "approved_search_restrictions_decision_5": [
            '"Continuity of Patient Care"[MeSH] restricted to [majr]',
            '"Referral and Consultation"[MeSH] restricted to [majr]',
            'bare "referral"[tiab] dropped',
            'bare "consultation"[tiab] dropped',
        ],
        "settings": {k: len(v) for k, v in SETTINGS.items()},
        "term_group_sizes": {k: len(v) for k, v in TERM_GROUPS.items()},
        "counts_only": counts_only,
        "per_term": per_term,
        "union_hits": {r["setting"]: r["hits"] for r in log},
    })
    write_json(os.path.join(DATA, "01_run_manifest.json"), prov)

    # ---- the gate ----------------------------------------------------------
    print("\n=== Before moving to step 2, check these ===")
    coord = {r["setting"]: r["hits"] for r in group_counts
             if r["term_group"] == "coordination"}
    for setting, n in coord.items():
        verdict = ("usable" if n >= 500 else
                   "THIN - the coordination group may not be pulling its weight")
        print(f"  coordination, {setting}: {n:,} ({verdict})")
    print("  Also confirm: both settings return enough records to draw 250 from,")
    print("  and no single term in --per-term is returning zero (a typo shows up")
    print("  as a zero, not as an error).")
    print("\nDone. Next: python3 scripts/11_neutral_sample.py")


if __name__ == "__main__":
    main()
