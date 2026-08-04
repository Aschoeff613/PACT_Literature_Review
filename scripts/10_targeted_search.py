"""Targeted evidence scan for high-risk cognitive tasks in ED and primary care.

This is deliberately a high-precision, non-systematic search. It retrieves papers
about explicit diagnostic, handoff, follow-up, medication, or disposition decision
points that also document a safety risk. It is intended to inform a practical
framework, not to estimate the full literature.

Run: python3 scripts/10_targeted_search.py
"""
import os, sys
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
base = import_module("01_search")
from common import DATA, write_csv

SETTING = '''("Emergency Service, Hospital"[majr] OR "Emergency Medicine"[majr]
OR "Primary Health Care"[majr] OR "General Practice"[majr] OR "Family Practice"[majr]
OR "emergency department"[tiab] OR "emergency medicine"[tiab] OR "primary care"[tiab]
OR "general practice"[tiab] OR "family physician"[tiab])'''

DECISION_POINT = '''("disposition decision"[tiab] OR undertriage[tiab]
OR "clinical handoff"[tiab] OR "clinical handover"[tiab]
OR "handoff failure"[tiab] OR "handover failure"[tiab]
OR "failure to follow up"[tiab] OR "failure to follow-up"[tiab]
OR "test result follow-up"[tiab] OR "medication reconciliation"[tiab]
OR "medication review"[tiab] OR "diagnostic reconsideration"[tiab]
OR "diagnostic re-evaluation"[tiab] OR "diagnostic reevaluation"[tiab]
OR "re-evaluate diagnosis"[tiab] OR "reassess diagnosis"[tiab])'''

HARM = '''("diagnostic error"[tiab] OR "diagnostic errors"[tiab]
OR "missed diagnosis"[tiab] OR "missed diagnoses"[tiab]
OR "delayed diagnosis"[tiab] OR "diagnostic delay"[tiab]
OR "medication error"[tiab] OR "medication errors"[tiab]
OR "adverse drug event"[tiab] OR "adverse drug events"[tiab]
OR "loss to follow-up"[tiab] OR "lost to follow-up"[tiab]
OR "unplanned return"[tiab])'''

TERM = f"{SETTING} AND {DECISION_POINT} AND {HARM} {base.EXCLUDE} {base.DATES}"
OUT = os.path.join(DATA, "10_targeted_records.csv")
LOG = os.path.join(DATA, "10_targeted_search_log.csv")
FIELDS = ["screen_order", "batch", "pmid", "year", "journal", "title", "abstract", "doi", "pmc", "authors"]

if __name__ == "__main__":
    ids, count = base.search(TERM)
    print(f"  {count} high-precision targeted-search hits")
    rows = base.details(ids)
    for i, row in enumerate(rows, 1):
        row["screen_order"] = i
        row["batch"] = (i - 1) // 100 + 1
    write_csv(OUT, rows, FIELDS)
    write_csv(LOG, [{"query": TERM, "hits": count, "downloaded": len(rows)}],
              ["query", "hits", "downloaded"])
    print(f"\n  {len(rows)} records ready for targeted screening -> {OUT}")
