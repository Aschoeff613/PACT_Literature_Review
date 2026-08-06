"""
STEP 4 - Build (a) the human validation sample and (b) the includes list.

Two jobs:

  A. Pulls a random 300 records for a human to screen BY HAND from the abstract.
     No PDFs needed. This is how you measure whether the AI screen is trustworthy.
     Output: 04_validation_sample.csv  -- open in Excel, fill the 'human_decision'
     column with include or exclude, save it, then run step 7.

  B. Builds the list of papers to get full text for, from the AI screening.

Run it with:   python3 scripts/04_validate_sample.py
"""
import argparse, os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_csv, write_csv, need, DATA

SAMPLE_N = 300
SEED = 20260803   # fixed so the sample is reproducible. Do not change after starting.

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare a blinded validation sample and candidate includes list.")
    parser.add_argument("--records", default=os.path.join(DATA,"02_unique_records.csv"),
                        help="source records CSV")
    parser.add_argument("--screening", default=os.path.join(DATA,"03_screening.csv"),
                        help="completed screening CSV")
    parser.add_argument("--validation-output", default=os.path.join(DATA,"04_validation_sample.csv"),
                        help="validation sample CSV")
    parser.add_argument("--includes-output", default=os.path.join(DATA,"04_includes.csv"),
                        help="candidate includes CSV")
    parser.add_argument("--sample-size", type=int, default=SAMPLE_N,
                        help=f"number of abstracts for blinded human validation (default: {SAMPLE_N})")
    args = parser.parse_args()
    recs = {r["pmid"]: r for r in read_csv(need(args.records))}
    screen = read_csv(need(args.screening))

    # A. validation sample, stratified so it is not all from one strand
    random.seed(SEED)
    pool = [r for r in screen if r["pmid"] in recs]
    inc = [r for r in pool if "include" in (r.get("gpt_decision",""), r.get("claude_decision",""))]
    exc = [r for r in pool if r not in inc]
    take_i = min(len(inc), args.sample_size//2)
    take_e = min(len(exc), args.sample_size - take_i)

    def balanced_take(pool, n):
        """Take as evenly as possible from emergency medicine and primary care."""
        groups = {}
        for r in pool:
            groups.setdefault(recs[r["pmid"]].get("source_setting", "other"), []).append(r)
        chosen = []
        target = n // len(groups)
        for group in groups.values():
            chosen.extend(random.sample(group, min(len(group), target)))
        remaining = [r for r in pool if r not in chosen]
        chosen.extend(random.sample(remaining, min(n - len(chosen), len(remaining))))
        return chosen

    sample = balanced_take(inc, take_i) + balanced_take(exc, take_e)
    random.shuffle(sample)
    rows = []
    for r in sample:
        b = recs[r["pmid"]]
        rows.append({"pmid":r["pmid"],"year":b["year"],"journal":b["journal"],
            "title":b["title"],"abstract":b["abstract"],"source_setting":b.get("source_setting", ""),
            "human_decision":"", "human_notes":"",
            "_ai_gpt":r.get("gpt_decision",""), "_ai_claude":r.get("claude_decision","")})
    write_csv(args.validation_output, rows,
        ["pmid","year","journal","title","abstract","source_setting","human_decision","human_notes","_ai_gpt","_ai_claude"])
    print(f"  validation sample: {len(rows)} records ({take_i} AI-include, {take_e} AI-exclude)")
    print("  IMPORTANT: hide the two _ai_ columns while you screen, so you are not anchored.")

    # B. includes for full text
    includes = []
    for r in screen:
        human = (r.get("human_final") or "").strip().lower()
        ai_inc = "include" in (r.get("gpt_decision",""), r.get("claude_decision",""))
        if human == "include" or (human == "" and ai_inc):
            b = recs.get(r["pmid"], {})
            includes.append({"pmid":r["pmid"],"title":b.get("title",""),"year":b.get("year",""),
                "journal":b.get("journal",""),"doi":b.get("doi",""),"pmc":b.get("pmc",""),
                "source_setting":b.get("source_setting",""),
                "decided_by": "human" if human else "ai_pending_human"})
    write_csv(args.includes_output, includes,
        ["pmid","title","year","journal","doi","pmc","source_setting","decided_by"])
    npmc = sum(1 for r in includes if r["pmc"])
    print(f"\n  includes: {len(includes)}; {npmc} have free PMC full text ({100*npmc/max(len(includes),1):.0f}%)")
    print("  Next: step 5 downloads what it can and lists the rest for manual retrieval.")
