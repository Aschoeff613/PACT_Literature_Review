"""
STEP 2 - Remove duplicates and set the screening order.

No family logic here any more (see step 1 for why). Records keep the order
PubMed's relevance ranking returned them in, which is what determines batch
number for the saturation stopping rule in the protocol: screen in batches of
100 and stop after two consecutive batches produce no new candidate task.

Run it with:   python3 scripts/02_dedupe.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_csv, write_csv, need, DATA

if __name__ == "__main__":
    rows = read_csv(need(os.path.join(DATA,"01_all_records.csv")))
    print(f"  read {len(rows)} rows")
    seen = {}
    order = []
    for r in rows:
        key = r["pmid"]
        if key not in seen:
            seen[key] = r
            order.append(key)
    uniq = [seen[k] for k in order]
    for i, r in enumerate(uniq, 1):
        r["screen_order"] = i
        r["batch"] = (i - 1)//100 + 1
        r["has_abstract"] = "yes" if len(r.get("abstract","")) > 100 else "no"
    print(f"  {len(rows) - len(uniq)} duplicates removed -> {len(uniq)} unique papers")
    noabs = sum(1 for r in uniq if r["has_abstract"]=="no")
    print(f"  {noabs} have no usable abstract ({100*noabs/max(len(uniq),1):.0f}%) - these need title-only or full-text screening")
    write_csv(os.path.join(DATA,"02_unique_records.csv"), uniq,
        ["screen_order","batch","pmid","year","journal","title","abstract","doi","pmc","authors","has_abstract"])
    print("\nDone. data/02_unique_records.csv is your screening list, relevance order, batches of 100.")
    print("Screen batch 1 with two reviewers, compute kappa, then one-reviewer the rest with")
    print("second-reviewer check on all inclusions - see protocol.md section 7.")
