"""Build a bounded, category-neutral corpus for inductive task discovery.

This is a targeted evidence scan, not a systematic review. It draws a reproducible,
equal-sized random sample from the broad high-risk cognition literature in emergency
medicine and primary care. The search names no task families and never uses the
expert-generated task list.

Run: python3 scripts/11_neutral_sample.py
"""
import os, random, sys
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
base = import_module("01_search")
from common import DATA, write_csv

SAMPLE_PER_SETTING = 250
SEED = 20260803

ED = '''("Emergency Service, Hospital"[majr] OR "Emergency Medicine"[majr]
OR "emergency department"[ti] OR "emergency physician"[ti]
OR "emergency physicians"[ti] OR "emergency medicine"[ti])'''

PRIMARY_CARE = '''("Primary Health Care"[majr] OR "General Practice"[majr]
OR "General Practitioners"[majr] OR "Physicians, Primary Care"[majr]
OR "Family Practice"[majr] OR "primary care"[ti] OR "general practice"[ti]
OR "general practitioner"[ti] OR "general practitioners"[ti]
OR "family physician"[ti] OR "family physicians"[ti])'''

# These are source signals, not candidate task categories. A record qualifies if it
# concerns clinician cognition OR a diagnostic/workflow safety signal in one setting.
SIGNAL = f"({base.COGNITION} OR {base.HARM})"

OUT = os.path.join(DATA, "11_neutral_sample.csv")
LOG = os.path.join(DATA, "11_neutral_sample_log.csv")
FIELDS = ["screen_order", "batch", "source_setting", "pmid", "year", "journal",
          "title", "abstract", "doi", "pmc", "authors"]

def sample_ids(ids, setting, seen, rng):
    shuffled = list(ids)
    rng.shuffle(shuffled)
    chosen = []
    for pmid in shuffled:
        if pmid not in seen:
            chosen.append((pmid, setting))
            seen.add(pmid)
        if len(chosen) == SAMPLE_PER_SETTING:
            break
    return chosen

if __name__ == "__main__":
    rng = random.Random(SEED)
    ed_ids, ed_hits = base.search(f"{ED} AND {SIGNAL} {base.EXCLUDE} {base.DATES}")
    pc_ids, pc_hits = base.search(f"{PRIMARY_CARE} AND {SIGNAL} {base.EXCLUDE} {base.DATES}")

    seen = set()
    ed_sample = sample_ids(ed_ids, "emergency medicine", seen, rng)
    pc_sample = sample_ids(pc_ids, "primary care", seen, rng)

    # Interleave settings so every early pilot has equal ED and primary-care coverage.
    selected = []
    for ed, pc in zip(ed_sample, pc_sample):
        selected.extend((ed, pc))
    selected.extend(ed_sample[len(pc_sample):])
    selected.extend(pc_sample[len(ed_sample):])

    details = {r["pmid"]: r for r in base.details([pmid for pmid, _ in selected])}
    rows = []
    for i, (pmid, setting) in enumerate(selected, 1):
        row = details.get(pmid)
        if not row:
            continue
        row["screen_order"] = i
        row["batch"] = (i - 1) // 100 + 1
        row["source_setting"] = setting
        rows.append(row)

    write_csv(OUT, rows, FIELDS)
    write_csv(LOG, [
        {"setting": "emergency medicine", "query": f"{ED} AND {SIGNAL} {base.EXCLUDE} {base.DATES}",
         "hits": ed_hits, "sampled": len(ed_sample)},
        {"setting": "primary care", "query": f"{PRIMARY_CARE} AND {SIGNAL} {base.EXCLUDE} {base.DATES}",
         "hits": pc_hits, "sampled": len(pc_sample)},
    ], ["setting", "query", "hits", "sampled"])
    print(f"  ED: {ed_hits} eligible records; sampled {len(ed_sample)}")
    print(f"  Primary care: {pc_hits} eligible records; sampled {len(pc_sample)}")
    print(f"  wrote {len(rows)} balanced, category-neutral records -> {OUT}")
