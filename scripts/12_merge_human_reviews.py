#!/usr/bin/env python3
"""Merge four 150-record reviewer exports into one 300-paper consensus file.

Recommended assignment:
  reviewers 1 and 2 -> pact_validation_review_001-150.html
  reviewers 3 and 4 -> pact_validation_review_151-300.html

Each paper therefore receives exactly two independent decisions. Agreements become
the consensus decision; disagreements are written to a short adjudication file.

Example:
  python3 scripts/12_merge_human_reviews.py \
    reviewer_1.csv reviewer_2.csv reviewer_3.csv reviewer_4.csv
"""

import argparse
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, need, read_csv, write_csv


VALID_DECISIONS = {"include", "exclude"}


def clean_decision(value):
    value = (value or "").strip().lower()
    return value if value in VALID_DECISIONS else ""


def kappa(rows):
    """Cohen's kappa for rows containing decision_a and decision_b."""
    if not rows:
        return float("nan")
    n = len(rows)
    agree = sum(r["decision_a"] == r["decision_b"] for r in rows)
    a_include = sum(r["decision_a"] == "include" for r in rows) / n
    b_include = sum(r["decision_b"] == "include" for r in rows) / n
    expected = a_include * b_include + (1 - a_include) * (1 - b_include)
    return (agree / n - expected) / (1 - expected) if expected < 1 else float("nan")


def fmt_rate(value):
    return "" if math.isnan(value) else f"{value:.3f}"


def main():
    parser = argparse.ArgumentParser(
        description="Merge four independent reviewer exports and identify disagreements."
    )
    parser.add_argument("reviews", nargs=4, help="four CSV files exported by the browser reviewers")
    parser.add_argument("--names", nargs=4, metavar=("R1", "R2", "R3", "R4"),
                        help="optional reviewer names; defaults to the four filenames")
    parser.add_argument("--master", default=os.path.join(DATA, "11_neutral_validation_sample.csv"),
                        help="original 300-record validation sample")
    parser.add_argument("--output", default=os.path.join(DATA, "12_human_consensus.csv"),
                        help="merged 300-record output")
    parser.add_argument("--disagreements", default=os.path.join(DATA, "12_disagreements.csv"),
                        help="papers that require adjudication")
    parser.add_argument("--adjudications", default=None,
                        help="optional edited disagreement CSV to merge on a rerun")
    parser.add_argument("--summary", default=os.path.join(DATA, "12_agreement_summary.csv"),
                        help="agreement summary by reviewer pair")
    parser.add_argument("--expected-per-reviewer", type=int, default=150,
                        help="required completed decisions per reviewer (default: 150; use 0 to disable)")
    parser.add_argument("--expected-ratings-per-paper", type=int, default=2,
                        help="required ratings per paper (default: 2)")
    parser.add_argument("--allow-incomplete", action="store_true",
                        help="write partial outputs instead of stopping for missing decisions")
    args = parser.parse_args()

    master = read_csv(need(args.master))
    master_by_pmid = {str(r.get("pmid", "")).strip(): r for r in master}
    if len(master) != len(master_by_pmid):
        sys.exit("ERROR: the master validation sample contains duplicate or blank PMIDs.")

    names = args.names or [Path(path).stem for path in args.reviews]
    if len(set(names)) != 4:
        sys.exit("ERROR: reviewer names must be unique.")

    ratings = defaultdict(list)
    reviewer_counts = {}
    problems = []
    for reviewer, path in zip(names, args.reviews):
        rows = read_csv(need(path))
        seen = set()
        completed = 0
        for row in rows:
            pmid = str(row.get("pmid", "")).strip()
            if not pmid or pmid not in master_by_pmid:
                problems.append(f"{reviewer}: unknown or blank PMID {pmid!r}")
                continue
            if pmid in seen:
                problems.append(f"{reviewer}: duplicate PMID {pmid}")
                continue
            seen.add(pmid)
            decision = clean_decision(row.get("human_decision"))
            if not decision:
                if not args.allow_incomplete:
                    problems.append(f"{reviewer}: PMID {pmid} has no include/exclude decision")
                continue
            completed += 1
            ratings[pmid].append({
                "reviewer": reviewer,
                "decision": decision,
                "notes": (row.get("human_notes") or "").strip(),
            })
        reviewer_counts[reviewer] = completed
        if args.expected_per_reviewer and completed != args.expected_per_reviewer:
            problems.append(
                f"{reviewer}: expected {args.expected_per_reviewer} completed decisions, found {completed}"
            )

    for pmid in master_by_pmid:
        count = len(ratings.get(pmid, []))
        if count != args.expected_ratings_per_paper:
            problems.append(
                f"PMID {pmid}: expected {args.expected_ratings_per_paper} ratings, found {count}"
            )

    if problems and not args.allow_incomplete:
        preview = "\n  ".join(problems[:20])
        more = f"\n  ...and {len(problems) - 20} more" if len(problems) > 20 else ""
        sys.exit(f"ERROR: reviewer files are not complete or correctly assigned:\n  {preview}{more}")

    merged = []
    pair_rows = defaultdict(list)
    for order, base in enumerate(master, 1):
        pmid = str(base.get("pmid", "")).strip()
        paper_ratings = sorted(ratings.get(pmid, []), key=lambda r: r["reviewer"])
        first = paper_ratings[0] if len(paper_ratings) >= 1 else {}
        second = paper_ratings[1] if len(paper_ratings) >= 2 else {}
        decision_a = first.get("decision", "")
        decision_b = second.get("decision", "")
        agreement = "yes" if decision_a and decision_a == decision_b else (
            "no" if decision_a and decision_b else "incomplete"
        )
        consensus = decision_a if agreement == "yes" else ""
        ai_combined = "include" if "include" in (
            (base.get("_ai_gpt") or "").strip().lower(),
            (base.get("_ai_claude") or "").strip().lower(),
        ) else "exclude"
        row = {
            "review_order": order,
            "pmid": pmid,
            "year": base.get("year", ""),
            "journal": base.get("journal", ""),
            "title": base.get("title", ""),
            "abstract": base.get("abstract", ""),
            "source_setting": base.get("source_setting", ""),
            "reviewer_a": first.get("reviewer", ""),
            "decision_a": decision_a,
            "notes_a": first.get("notes", ""),
            "reviewer_b": second.get("reviewer", ""),
            "decision_b": decision_b,
            "notes_b": second.get("notes", ""),
            "agreement": agreement,
            "consensus_decision": consensus,
            "adjudicated_decision": "",
            "adjudication_notes": "",
            "_ai_gpt": base.get("_ai_gpt", ""),
            "_ai_claude": base.get("_ai_claude", ""),
            "ai_combined_decision": ai_combined,
        }
        merged.append(row)
        if decision_a and decision_b:
            pair = f"{row['reviewer_a']} + {row['reviewer_b']}"
            pair_rows[pair].append(row)

    if args.adjudications:
        for adjudication in read_csv(need(args.adjudications)):
            pmid = str(adjudication.get("pmid", "")).strip()
            decision = clean_decision(adjudication.get("adjudicated_decision"))
            if pmid in master_by_pmid and decision:
                target = next(row for row in merged if row["pmid"] == pmid)
                target["adjudicated_decision"] = decision
                target["adjudication_notes"] = (adjudication.get("adjudication_notes") or "").strip()

    fields = [
        "review_order", "pmid", "year", "journal", "title", "abstract", "source_setting",
        "reviewer_a", "decision_a", "notes_a", "reviewer_b", "decision_b", "notes_b",
        "agreement", "consensus_decision", "adjudicated_decision", "adjudication_notes",
        "_ai_gpt", "_ai_claude", "ai_combined_decision",
    ]
    write_csv(args.output, merged, fields)
    disagreement_rows = [r for r in merged if r["agreement"] != "yes"]
    write_csv(args.disagreements, disagreement_rows, fields)

    summaries = []
    all_complete = []
    for pair, rows in sorted(pair_rows.items()):
        all_complete.extend(rows)
        agree = sum(r["agreement"] == "yes" for r in rows)
        summaries.append({
            "reviewer_pair": pair,
            "papers": len(rows),
            "agreements": agree,
            "disagreements": len(rows) - agree,
            "percent_agreement": f"{agree / len(rows):.3f}" if rows else "",
            "cohen_kappa": fmt_rate(kappa(rows)),
            "both_include": sum(r["decision_a"] == r["decision_b"] == "include" for r in rows),
            "both_exclude": sum(r["decision_a"] == r["decision_b"] == "exclude" for r in rows),
        })
    if all_complete:
        agree = sum(r["agreement"] == "yes" for r in all_complete)
        summaries.append({
            "reviewer_pair": "OVERALL",
            "papers": len(all_complete),
            "agreements": agree,
            "disagreements": len(all_complete) - agree,
            "percent_agreement": f"{agree / len(all_complete):.3f}",
            "cohen_kappa": fmt_rate(kappa(all_complete)),
            "both_include": sum(r["decision_a"] == r["decision_b"] == "include" for r in all_complete),
            "both_exclude": sum(r["decision_a"] == r["decision_b"] == "exclude" for r in all_complete),
        })
    write_csv(args.summary, summaries, [
        "reviewer_pair", "papers", "agreements", "disagreements", "percent_agreement",
        "cohen_kappa", "both_include", "both_exclude",
    ])

    print("\n  reviewer totals:")
    for reviewer in names:
        print(f"    {reviewer}: {reviewer_counts.get(reviewer, 0)}")
    print(f"  agreements: {sum(r['agreement'] == 'yes' for r in merged)}")
    unresolved = sum(not clean_decision(r.get("adjudicated_decision")) for r in disagreement_rows)
    print(f"  disagreements: {len(disagreement_rows)}; still requiring adjudication: {unresolved}")


if __name__ == "__main__":
    main()
