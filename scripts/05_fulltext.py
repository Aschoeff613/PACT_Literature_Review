"""
STEP 5 - Find and download full text, free and legally, wherever possible.

Checks two places for every paper you decided to include:
  1. PubMed Central  (free full text hosted by NIH)
  2. Unpaywall       (tells you if a legal free copy exists anywhere else)

Downloads what it can as plain text into data/fulltext/ and then gives you a
short worklist of the ones a human has to fetch through the library.

Run it with:   python3 scripts/05_fulltext.py
"""
import argparse, os, re, sys, json, time, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import fetch, read_csv, write_csv, need, DATA, EMAIL, EUTILS

INPUT = os.path.join(DATA, "04_includes.csv")     # made in step 4
FTDIR = os.path.join(DATA, "fulltext")

def pmc_text(pmcid):
    """PMC full text. NOTE: use NCBI efetch. The europePMC fullTextXML endpoint
    404s on many records, which will waste your afternoon if you trust it."""
    num = pmcid.replace("PMC","")
    q = urllib.parse.urlencode({"db":"pmc","id":num,"rettype":"xml","email":EMAIL})
    xml = fetch(EUTILS+"efetch.fcgi?"+q).decode("utf-8","ignore")
    body = re.search(r"<body>(.*?)</body>", xml, re.S)
    raw = body.group(1) if body else xml
    txt = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", txt).strip()

def unpaywall(doi):
    try:
        j = json.loads(fetch(f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={EMAIL}", tries=2))
        if j.get("is_oa"):
            loc = j.get("best_oa_location") or {}
            return loc.get("url_for_pdf") or loc.get("url") or ""
    except Exception:
        pass
    return ""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retrieve legally available full text and create a manual worklist.")
    parser.add_argument("--input", default=INPUT, help="candidate includes CSV")
    parser.add_argument("--fulltext-dir", default=FTDIR, help="directory for retrieved PMC text")
    parser.add_argument("--worklist-output", default=os.path.join(DATA,"05_manual_worklist.csv"),
                        help="manual retrieval worklist CSV")
    parser.add_argument("--start", type=int, default=1, help="1-based first input row")
    parser.add_argument("--limit", type=int, default=None, help="optional number of input rows to process")
    args = parser.parse_args()
    rows = read_csv(need(args.input))
    rows = rows[args.start - 1:]
    if args.limit:
        rows = rows[:args.limit]
    os.makedirs(args.fulltext_dir, exist_ok=True)
    prior = read_csv(args.worklist_output) if os.path.exists(args.worklist_output) else []
    worklist = {r["pmid"]: r for r in prior}
    got = 0
    for i, r in enumerate(rows, 1):
        pmid, pmc, doi = r["pmid"], r.get("pmc",""), r.get("doi","")
        out = os.path.join(args.fulltext_dir, f"{pmid}.txt")
        if os.path.exists(out) and os.path.getsize(out) > 3000:
            got += 1; continue
        text = ""
        if pmc:
            try:
                t = pmc_text(pmc)
                if len(t) > 3000: text = t
            except Exception: pass
        if text:
            open(out,"w",encoding="utf-8").write(text)
            got += 1
            print(f"  [{i}/{len(rows)}] {pmid}: {len(text):,} chars from PMC")
        else:
            link = unpaywall(doi) if doi else ""
            worklist[pmid] = {"pmid":pmid,"title":r["title"],"year":r.get("year",""),
                "journal":r.get("journal",""),"doi":doi,
                "free_pdf_link": link,
                "action": "download this free PDF" if link else "get via library proxy",
                "save_as": os.path.join(args.fulltext_dir, f"{pmid}.txt")}
            print(f"  [{i}/{len(rows)}] {pmid}: needs manual retrieval" + (" (free link found)" if link else ""))
        time.sleep(0.34)
    write_csv(args.worklist_output, list(worklist.values()),
        ["pmid","title","year","journal","doi","free_pdf_link","action","save_as"])
    print(f"\n  automatic: {got}    manual: {len(worklist)}")
    print("  Open data/05_manual_worklist.csv. Work down it, save each as plain text")
    print("  in data/fulltext/<pmid>.txt, then run step 6.")
