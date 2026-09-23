"""
STEP 8 - Human check: are these tasks really in the papers?

Protocol v7, step 8.

Automatic, on everything: every quote was checked word for word against its
source text in step 7. This script reports how many failed, by kind:
verbatim / found but too short / NOT in the paper. Only verbatim rows can go
on to grouping.

By hand, 120 rows, weighted toward tasks that appeared in only one or two
papers (a made-up task can only survive into the final list from there).
Before grouping there are no tasks yet, so "a task" here is a task name as
the papers wrote it, normalised for case and spacing, counted by the number
of papers using it. 80 rows come from names used by one or two papers, 40
from the rest (if there are fewer rare rows, the balance comes from common).
One reviewer per row; 30 rows are read by both reviewers so agreement can be
reported. Three questions per row:

  q1_paper_wording   Is this the paper's wording, or did the AI supply the
                     name?                                (yes = paper's own)
  q2_quote_supports  Does the quote actually support it?  (yes / no)
  q3_kind            Thinking process or clinical activity?
                     (thinking / clinical)

Rows failing q1 or q2 (either reviewer, for the 30 read twice) are deleted
before grouping. A q3 answer overrides the AI's classification.

Build the sheets:
    python3 scripts/14_extraction_check.py build
  -> validation/step8/check_A.csv, check_B.csv   one per reviewer
  -> data/08_check_master.csv                    which rows, who reads them
Apply the answers:
    python3 scripts/14_extraction_check.py apply validation/step8/check_A.csv validation/step8/check_B.csv
  -> data/08_rows_for_grouping.csv    thinking-process rows that go to step 9
  -> data/08_clinical_activities.csv  the separate clinical activity list
  -> data/08_check_report.json        failure counts and agreement
"""
import os
import random
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, VALIDATION, need, provenance, read_csv,
                    write_csv, write_json)

SEED = 20260923
N_CHECK, N_RARE, N_DOUBLE = 120, 80, 30
ROWS = os.path.join(DATA, "07_extraction_rows.csv")
SAMPLE = os.path.join(DATA, "11_sample_500.csv")
SHEET_DIR = os.path.join(VALIDATION, "step8")
MASTER = os.path.join(DATA, "08_check_master.csv")
SHEET_FIELDS = ["check_no", "reviewer", "row_id", "pmid", "title", "source",
                "task_name", "definition", "quote", "kind_as_extracted",
                "where_to_check", "q1_paper_wording", "q2_quote_supports",
                "q3_kind", "notes"]


def norm_name(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()


def rows_in_force(rows):
    """Full-text rows replace a paper's abstract rows."""
    ft = {r["pmid"] for r in rows if r["source"] == "fulltext"}
    return [r for r in rows if r["source"] == "fulltext" or r["pmid"] not in ft]


def eligible(rows):
    return [r for r in rows if r.get("quote_check") == "verbatim"
            and r.get("rejected_vague") != "yes"
            and r.get("kind") in ("thinking_process", "clinical_activity")]


def build():
    rows = rows_in_force(read_csv(need(ROWS)))
    sample = {r["pmid"]: r for r in read_csv(need(SAMPLE))}
    qc = defaultdict(int)
    for r in rows:
        qc[r.get("quote_check", "unknown")] += 1
    pool = eligible(rows)
    papers_per_name = defaultdict(set)
    for r in pool:
        papers_per_name[norm_name(r["task_name"])].add(r["pmid"])
    rare = [r for r in pool if len(papers_per_name[norm_name(r["task_name"])]) <= 2]
    common = [r for r in pool if r not in rare]

    rng = random.Random(SEED)
    rng.shuffle(rare)
    rng.shuffle(common)
    take_rare = rare[:min(N_RARE, len(rare))]
    take_common = common[:min(N_CHECK - len(take_rare), len(common))]
    if len(take_rare) + len(take_common) < N_CHECK:
        take_rare += rare[len(take_rare):len(take_rare) + N_CHECK - len(take_rare) - len(take_common)]
    chosen = take_rare + take_common
    rng.shuffle(chosen)
    n = len(chosen)
    n_double = min(N_DOUBLE, n)
    # First n_double rows go to both; the rest alternate A, B.
    master, sheets = [], {"A": [], "B": []}
    for i, r in enumerate(chosen, 1):
        readers = ["A", "B"] if i <= n_double else (["A"] if i % 2 else ["B"])
        rec = sample.get(r["pmid"], {})
        where = ("abstract below" if r["source"] == "abstract"
                 else f"data/fulltext/{r['pmid']}.txt")
        master.append({"check_no": i, "row_id": r["row_id"], "pmid": r["pmid"],
                       "readers": "+".join(readers),
                       "stratum": "rare" if r in take_rare else "common"})
        for rv in readers:
            sheets[rv].append({
                "check_no": i, "reviewer": rv, "row_id": r["row_id"], "pmid": r["pmid"],
                "title": rec.get("title", ""), "source": r["source"],
                "task_name": r["task_name"], "definition": r["definition"],
                "quote": r["quote"], "kind_as_extracted": r["kind"],
                "where_to_check": where + ((" | ABSTRACT: " + rec.get("abstract", ""))
                                           if r["source"] == "abstract" else ""),
                "q1_paper_wording": "", "q2_quote_supports": "", "q3_kind": "", "notes": ""})
    os.makedirs(SHEET_DIR, exist_ok=True)
    for rv, s in sheets.items():
        write_csv(os.path.join(SHEET_DIR, f"check_{rv}.csv"), s, SHEET_FIELDS)
    write_csv(MASTER, master, ["check_no", "row_id", "pmid", "readers", "stratum"])

    prov = provenance(os.path.abspath(__file__))
    prov.update({"seed": SEED, "rows_in_force": len(rows), "quote_check": dict(qc),
                 "eligible": len(pool), "rare_rows_available": len(rare),
                 "checked": n, "rare_checked": len(take_rare), "double_read": n_double})
    write_json(os.path.join(DATA, "08_check_build_manifest.json"), prov)
    print(f"\n  automatic check on {len(rows)} rows in force: " +
          ", ".join(f"{k} {v}" for k, v in sorted(qc.items())))
    print(f"  eligible for the hand check (verbatim, not vague): {len(pool)}")
    print(f"  hand check: {n} rows ({len(take_rare)} from rare names), {n_double} read by both")
    print(f"  reviewer A reads {len(sheets['A'])}, reviewer B reads {len(sheets['B'])}")


def yes(v):
    return (v or "").strip().lower() in ("yes", "y")


def no(v):
    return (v or "").strip().lower() in ("no", "n")


def apply(paths):
    rows = rows_in_force(read_csv(need(ROWS)))
    pool = eligible(rows)
    answers = defaultdict(dict)   # row_id -> reviewer -> answer row
    for p in paths:
        for a in read_csv(need(p)):
            answers[a["row_id"]][a["reviewer"]] = a
    master = read_csv(need(MASTER))
    unanswered = [m["check_no"] for m in master
                  for rv in m["readers"].split("+")
                  if not (answers[m["row_id"]].get(rv, {}).get("q1_paper_wording")
                          and answers[m["row_id"]].get(rv, {}).get("q2_quote_supports"))]
    if unanswered:
        sys.exit(f"ERROR: {len(unanswered)} checks unanswered (q1 or q2 blank), e.g. check_no "
                 f"{unanswered[:5]}. Finish the sheets first.")

    deleted, reclassified, agree = set(), {}, {"q1": [], "q2": [], "q3": []}
    for m in master:
        got = answers[m["row_id"]]
        if any(no(a.get("q1_paper_wording")) or no(a.get("q2_quote_supports")) for a in got.values()):
            deleted.add(m["row_id"])
        kinds = {(a.get("q3_kind") or "").strip().lower() for a in got.values()} - {""}
        if len(kinds) == 1:
            k = kinds.pop()
            reclassified[m["row_id"]] = "thinking_process" if k.startswith("think") else "clinical_activity"
        if len(got) == 2:
            a, b = list(got.values())
            for q, col in (("q1", "q1_paper_wording"), ("q2", "q2_quote_supports"), ("q3", "q3_kind")):
                va, vb = (a.get(col) or "").strip().lower(), (b.get(col) or "").strip().lower()
                if va and vb:
                    agree[q].append(va == vb)

    kept = []
    for r in pool:
        if r["row_id"] in deleted:
            continue
        r = dict(r)
        if r["row_id"] in reclassified:
            r["kind_final"] = reclassified[r["row_id"]]
            r["checked_by_human"] = "yes"
        else:
            r["kind_final"] = r["kind"]
            r["checked_by_human"] = "no"
        kept.append(r)
    thinking = [r for r in kept if r["kind_final"] == "thinking_process"]
    clinical = [r for r in kept if r["kind_final"] == "clinical_activity"]
    fields = list(pool[0].keys()) + ["kind_final", "checked_by_human"] if pool else []
    write_csv(os.path.join(DATA, "08_rows_for_grouping.csv"), thinking, fields)

    acts = defaultdict(lambda: {"papers": set(), "examples": []})
    for r in clinical:
        k = norm_name(r["task_name"])
        acts[k]["papers"].add(r["pmid"])
        if len(acts[k]["examples"]) < 3:
            acts[k]["examples"].append(r["task_name"])
    write_csv(os.path.join(DATA, "08_clinical_activities.csv"),
              [{"activity": v["examples"][0], "n_papers": len(v["papers"]),
                "pmids": "; ".join(sorted(v["papers"]))}
               for v in sorted(acts.values(), key=lambda v: -len(v["papers"]))],
              ["activity", "n_papers", "pmids"])

    pct = lambda xs: round(100 * sum(xs) / len(xs), 1) if xs else None
    report = {"checked": len(master), "deleted_q1_or_q2": len(deleted),
              "deleted_rare": sum(1 for m in master if m["row_id"] in deleted and m["stratum"] == "rare"),
              "kind_overridden": sum(1 for r in pool if r["row_id"] in reclassified
                                     and reclassified[r["row_id"]] != r["kind"]),
              "double_read_agreement_pct": {q: pct(v) for q, v in agree.items()},
              "to_grouping_thinking_rows": len(thinking),
              "clinical_activity_rows": len(clinical)}
    prov = provenance(os.path.abspath(__file__))
    prov.update({"sheets": [os.path.basename(p) for p in paths], **report})
    write_json(os.path.join(DATA, "08_check_report.json"), prov)
    print(f"\n  hand-checked {len(master)}: deleted {len(deleted)} "
          f"({report['deleted_rare']} of them from rare names); "
          f"kind changed on {report['kind_overridden']}")
    print(f"  agreement on the double-read rows: {report['double_read_agreement_pct']}")
    print(f"  to grouping: {len(thinking)} thinking-process rows; "
          f"clinical activities listed separately: {len(clinical)} rows")
    print("\nNext: python3 scripts/08_cluster.py")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "build":
        build()
    elif len(sys.argv) >= 3 and sys.argv[1] == "apply":
        apply(sys.argv[2:])
    else:
        sys.exit(__doc__)
