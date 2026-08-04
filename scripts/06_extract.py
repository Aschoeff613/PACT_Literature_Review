"""
STEP 6 - Pull cognitive demands and high-risk situations out of each full text.

Reads every .txt file in data/fulltext/ and asks each model to extract the two
halves of a taxonomy entry separately (see prompts/extract_prompt.txt): the
cognitive demand, and the high-risk clinical situation. Every item carries a
verbatim quote, checked automatically against the actual text. An item whose
quote is not really in the paper is flagged, which is how you catch a model
making something up.

Run it with:   python3 scripts/06_extract.py
Test on 3 papers first:   python3 scripts/06_extract.py 3
"""
import os, sys, json, time, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_csv, write_csv, need, DATA
from importlib import import_module
screen = import_module("03_screen")   # reuse the API call functions

# Extraction is the step where model quality matters, so override the cheap
# screening models with the stronger ones. Copy exact IDs from the vendor
# pricing pages if these have been renamed.
screen.OPENAI_MODEL    = "gpt-5.6-terra"
screen.ANTHROPIC_MODEL = "claude-sonnet-5"

PROMPT = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "prompts","extract_prompt.txt")).read()
FTDIR = os.path.join(DATA,"fulltext")
MAXCHARS = 120000    # trim very long papers; references add nothing here

def norm(s):
    return re.sub(r"\s+"," ", (s or "")).strip().lower()

def verified(quote, hay):
    q = norm(quote)
    return "yes" if q and q[:80] in hay else "NO - CHECK THIS"

def call(fn, text):
    orig = screen.PROMPT
    screen.PROMPT = PROMPT
    try:
        return fn(text)
    finally:
        screen.PROMPT = orig

if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    files = sorted(f for f in os.listdir(need(FTDIR)) if f.endswith(".txt"))
    if limit: files = files[:limit]
    print(f"  {len(files)} full texts to process")
    out = []
    for i, fn_ in enumerate(files, 1):
        pmid = fn_[:-4]
        body = open(os.path.join(FTDIR,fn_), encoding="utf-8").read()[:MAXCHARS]
        hay = norm(body)
        for model, fn in (("gpt", screen.ask_openai), ("claude", screen.ask_anthropic)):
            try:
                res = call(fn, "PAPER TEXT:\n\n"+body)
                for d in res.get("cognitive_demands", []):
                    out.append({"pmid":pmid,"model":model,"kind":"demand",
                        "label":d.get("label",""),"situation":"",
                        "definition":d.get("definition",""),
                        "altitude":d.get("altitude",""),"setting":"",
                        "failure_modes":"; ".join(d.get("failure_modes") or []),
                        "risk_evidence":"","has_number":"",
                        "why_cognitively_hard":"",
                        "undefined":d.get("undefined",False),
                        "verbatim_quote":d.get("verbatim_quote",""),
                        "quote_verified":verified(d.get("verbatim_quote",""), hay)})
                for s in res.get("high_risk_situations", []):
                    out.append({"pmid":pmid,"model":model,"kind":"situation",
                        "label":"","situation":s.get("situation",""),
                        "definition":"","altitude":"","setting":s.get("setting",""),
                        "failure_modes":"",
                        "risk_evidence":s.get("risk_evidence",""),
                        "has_number":s.get("has_number",""),
                        "why_cognitively_hard":s.get("why_cognitively_hard",""),
                        "undefined":"",
                        "verbatim_quote":s.get("verbatim_quote",""),
                        "quote_verified":verified(s.get("verbatim_quote",""), hay)})
            except Exception as e:
                out.append({"pmid":pmid,"model":model,"kind":"ERROR","label":str(e)[:150],
                            "situation":"","definition":"","altitude":"","setting":"",
                            "failure_modes":"","risk_evidence":"","has_number":"",
                            "why_cognitively_hard":"","undefined":"","verbatim_quote":"",
                            "quote_verified":""})
            time.sleep(0.3)
        print(f"    [{i}/{len(files)}] {pmid}: {sum(1 for r in out if r['pmid']==pmid)} extracted rows")
    write_csv(os.path.join(DATA,"06_constructs_raw.csv"), out,
        ["pmid","model","kind","label","situation","altitude","definition",
         "setting","failure_modes","risk_evidence","has_number","why_cognitively_hard",
         "undefined","verbatim_quote","quote_verified"])
    bad = sum(1 for r in out if r.get("quote_verified","").startswith("NO"))
    demands = sum(1 for r in out if r.get("kind")=="demand")
    situations = sum(1 for r in out if r.get("kind")=="situation")
    print(f"\n  {len(out)} extracted rows ({demands} demands, {situations} situations);")
    print(f"  {bad} with a quote NOT found in the paper - review those first")
    print("  Next: step 8 clusters the verified situations (and their paired demands)")
    print("  into an emergent candidate task list. Nothing is pre-sorted by category.")
