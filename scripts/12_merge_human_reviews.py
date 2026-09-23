#!/usr/bin/env python3
"""
STEP 5 - Sort out the disagreements.

Protocol v7, step 5: where both reviewers agree, that stands. Where they
disagree, a third person decides. Report agreement for each of the six pairs.

Takes the CSVs the six reviewers exported from their step 4 pages (in any
order, any filenames: each row carries its reviewer ID).

First run:
    python3 scripts/12_merge_human_reviews.py step4_review_R*.csv
  -> data/05_agreement_by_pair.csv   agreement and kappa for each pair
  -> data/05_adjudication.csv        every disagreement, for the third person
  -> data/05_human_consensus.csv     final decisions so far

The third person fills the adjudicated_decision column of 05_adjudication.csv
(include or exclude), and their name in adjudicator. Then run the same command
again: filled decisions are kept and folded into the consensus file. Nothing
already adjudicated is overwritten.
"""
import argparse
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, need, provenance, read_csv, write_csv, write_json

VALID = {"include", "exclude"}


def clean(v):
    v = (v or "").strip().lower()
    return v if v in VALID else ""


def kappa(pairs):
    """Cohen's kappa over (decision_1, decision_2) pairs."""
    n = len(pairs)
    if not n:
        return float("nan")
    po = sum(a == b for a, b in pairs) / n
    p1 = sum(a == "include" for a, _ in pairs) / n
    p2 = sum(b == "include" for _, b in pairs) / n
    pe = p1 * p2 + (1 - p1) * (1 - p2)
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def fmt(x):
    return "" if isinstance(x, float) and math.isnan(x) else f"{x:.3f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("reviews", nargs="+", help="reviewer CSV exports from step 4")
    ap.add_argument("--master", default=os.path.join(DATA, "04_validation_master.csv"))
    ap.add_argument("--adjudication", default=os.path.join(DATA, "05_adjudication.csv"))
    ap.add_argument("--output", default=os.path.join(DATA, "05_human_consensus.csv"))
    args = ap.parse_args()

    master = read_csv(need(args.master))
    by_pmid = {r["pmid"]: r for r in master}

    decisions = defaultdict(dict)    # pmid -> reviewer -> (decision, notes)
    for path in args.reviews:
        rows = read_csv(need(path))
        ids = {(r.get("reviewer") or "").strip() for r in rows} - {""}
        if len(ids) != 1:
            sys.exit(f"ERROR: {path} should hold one reviewer's export; found {sorted(ids) or 'none'}.")
        rv = ids.pop()
        if rv == "WARMUP":
            sys.exit(f"ERROR: {path} is a warm-up export. Warm-up papers do not count.")
        stray = [r["pmid"] for r in rows if r["pmid"] not in by_pmid]
        if stray:
            sys.exit(f"ERROR: {path} ({rv}) holds {len(stray)} PMIDs not in the master file.")
        for r in rows:
            if rv in decisions[r["pmid"]]:
                sys.exit(f"ERROR: two exports for reviewer {rv}. Pass each reviewer once.")
            decisions[r["pmid"]][rv] = (clean(r.get("human_decision")),
                                        (r.get("human_notes") or "").strip())

    prior = {r["pmid"]: r for r in read_csv(args.adjudication)} if os.path.exists(args.adjudication) else {}

    out, adjud, pair_rows = [], [], defaultdict(list)
    missing = defaultdict(int)
    for m in master:
        r1, r2 = m["reviewer_1"], m["reviewer_2"]
        d1, n1 = decisions[m["pmid"]].get(r1, ("", ""))
        d2, n2 = decisions[m["pmid"]].get(r2, ("", ""))
        if not d1:
            missing[r1] += 1
        if not d2:
            missing[r2] += 1
        row = dict(m)
        row.update({"decision_1": d1, "notes_1": n1, "decision_2": d2, "notes_2": n2})
        if d1 and d2:
            pair_rows[(m["block"], r1, r2)].append((d1, d2))
        if d1 and d2 and d1 == d2:
            row.update({"human_final": d1, "basis": "agreed"})
        elif d1 and d2:
            p = prior.get(m["pmid"], {})
            adj = clean(p.get("adjudicated_decision"))
            row.update({"human_final": adj, "basis": "adjudicated" if adj else "PENDING adjudication"})
            adjud.append({"val_no": m["val_no"], "block": m["block"], "pmid": m["pmid"],
                          "title": m["title"], "reviewer_1": r1, "decision_1": d1, "notes_1": n1,
                          "reviewer_2": r2, "decision_2": d2, "notes_2": n2,
                          "adjudicated_decision": adj,
                          "adjudicator": p.get("adjudicator", ""),
                          "adjudication_notes": p.get("adjudication_notes", "")})
        else:
            row.update({"human_final": "", "basis": "PENDING review"})
        out.append(row)

    agreement = []
    for (b, r1, r2), pairs in sorted(pair_rows.items(), key=lambda x: int(x[0][0])):
        n = len(pairs)
        agreement.append({"block": b, "pair": f"{r1}+{r2}", "n_both_decided": n,
                          "agree_pct": fmt(100 * sum(a == c for a, c in pairs) / n),
                          "kappa": fmt(kappa(pairs))})
    allpairs = [p for ps in pair_rows.values() for p in ps]
    if allpairs:
        agreement.append({"block": "all", "pair": "all six pairs", "n_both_decided": len(allpairs),
                          "agree_pct": fmt(100 * sum(a == c for a, c in allpairs) / len(allpairs)),
                          "kappa": fmt(kappa(allpairs))})

    write_csv(os.path.join(DATA, "05_agreement_by_pair.csv"), agreement,
              ["block", "pair", "n_both_decided", "agree_pct", "kappa"])
    write_csv(args.adjudication, adjud,
              ["val_no", "block", "pmid", "title", "reviewer_1", "decision_1", "notes_1",
               "reviewer_2", "decision_2", "notes_2", "adjudicated_decision",
               "adjudicator", "adjudication_notes"])
    write_csv(args.output, out,
              list(master[0].keys()) + ["decision_1", "notes_1", "decision_2", "notes_2",
                                        "human_final", "basis"])

    print("\n  agreement by pair:")
    for a in agreement:
        print(f"    {a['pair']:15s} n={a['n_both_decided']:>3}  agree {a['agree_pct']:>7}%  kappa {a['kappa']}")
    if missing:
        print("\n  UNDECIDED papers by reviewer (reviewer has not finished):")
        for rv, n in sorted(missing.items()):
            print(f"    {rv}: {n}")
    pend_adj = sum(1 for r in out if r["basis"] == "PENDING adjudication")
    pend_rev = sum(1 for r in out if r["basis"] == "PENDING review")
    done = len(out) - pend_adj - pend_rev
    print(f"\n  final decisions: {done}/{len(out)}   awaiting adjudication: {pend_adj}   "
          f"awaiting a reviewer: {pend_rev}")

    prov = provenance(os.path.abspath(__file__))
    prov.update({"reviewer_files": [os.path.basename(p) for p in args.reviews],
                 "final": done, "pending_adjudication": pend_adj, "pending_review": pend_rev,
                 "agreement": agreement})
    write_json(os.path.join(DATA, "05_merge_manifest.json"), prov)
    if pend_adj:
        print(f"\n  Next: the third person fills adjudicated_decision in "
              f"{os.path.relpath(args.adjudication, DATA)}, then re-run this command.")
    elif not pend_rev:
        print("\n  All 300 decided. Next: python3 scripts/07_metrics.py")


if __name__ == "__main__":
    main()
