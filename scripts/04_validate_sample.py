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
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_csv, write_csv, need, DATA

SAMPLE_N = 300
SEED = 20260803   # fixed so the sample is reproducible. Do not change after starting.

if __name__ == "__main__":
    recs = {r["pmid"]: r for r in read_csv(need(os.path.join(DATA,"02_unique_records.csv")))}
    screen = read_csv(need(os.path.join(DATA,"03_screening.csv")))

    # A. validation sample, stratified so it is not all from one strand
    random.seed(SEED)
    pool = [r for r in screen if r["pmid"] in recs]
    inc = [r for r in pool if "include" in (r.get("gpt_decision",""), r.get("claude_decision",""))]
    exc = [r for r in pool if r not in inc]
    take_i = min(len(inc), SAMPLE_N//2)
    take_e = min(len(exc), SAMPLE_N - take_i)
    sample = random.sample(inc, take_i) + random.sample(exc, take_e)
    random.shuffle(sample)
    rows = []
    for r in sample:
        b = recs[r["pmid"]]
        rows.append({"pmid":r["pmid"],"year":b["year"],"journal":b["journal"],
            "title":b["title"],"abstract":b["abstract"],
            "human_decision":"", "human_notes":"",
            "_ai_gpt":r.get("gpt_decision",""), "_ai_claude":r.get("claude_decision","")})
    write_csv(os.path.join(DATA,"04_validation_sample.csv"), rows,
        ["pmid","year","journal","title","abstract","human_decision","human_notes","_ai_gpt","_ai_claude"])
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
                "decided_by": "human" if human else "ai_pending_human"})
    write_csv(os.path.join(DATA,"04_includes.csv"), includes,
        ["pmid","title","year","journal","doi","pmc","decided_by"])
    npmc = sum(1 for r in includes if r["pmc"])
    print(f"\n  includes: {len(includes)}; {npmc} have free PMC full text ({100*npmc/max(len(includes),1):.0f}%)")
    print("  Next: step 5 downloads what it can and lists the rest for manual retrieval.")
