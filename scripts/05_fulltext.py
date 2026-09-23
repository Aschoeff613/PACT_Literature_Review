"""
STEP 7 (part) - Fetch full text for the papers extraction flagged.

Protocol v7 pulls the full paper only when the abstract is too thin, when the
paper looks like it holds something the abstract doesn't show, or when the
supporting sentence can't be confirmed. 06_extract.py records those flags;
this script fetches full text for exactly those papers, free and legally:

  1. PubMed Central open-access text, fetched automatically into
     data/fulltext/<pmid>.txt (body only; reference list dropped).
  2. Otherwise, a worklist line: a free copy's link from Unpaywall if one
     exists, else "library". A person saves the text as data/fulltext/<pmid>.txt.

Then: python3 scripts/06_extract.py --fulltext

The count of full texts pulled is reported, as v7's methods section requires.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, EMAIL, eutils, need, provenance, read_csv,
                    require_email, write_csv, write_json)

FTDIR = os.path.join(DATA, "fulltext")
PAPERS = os.path.join(DATA, "07_extraction_papers.csv")
SAMPLE = os.path.join(DATA, "11_sample_500.csv")
WORKLIST = os.path.join(DATA, "07_fulltext_worklist.csv")
MIN_CHARS = 3000


def pmc_text(pmcid):
    """Body text of a PMC article, without the reference list."""
    xml = eutils("efetch.fcgi", {"db": "pmc", "id": pmcid.replace("PMC", ""),
                                 "retmode": "xml"}).decode("utf-8", "ignore")
    body = re.search(r"<body>(.*?)</body>", xml, re.S)
    if not body:
        return ""
    raw = re.sub(r"<ref-list>.*?</ref-list>", " ", body.group(1), flags=re.S)
    raw = re.sub(r"</(p|title|sec)>", "\n", raw)
    import html
    txt = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", txt)).strip()


def unpaywall_link(doi):
    try:
        url = f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={EMAIL}"
        j = json.loads(urllib.request.urlopen(url, timeout=30).read())
        if j.get("is_oa"):
            loc = j.get("best_oa_location") or {}
            return loc.get("url_for_pdf") or loc.get("url") or ""
    except Exception:
        pass
    return ""


def main():
    require_email()
    sample = {r["pmid"]: r for r in read_csv(need(SAMPLE))}
    flagged = [r["pmid"] for r in read_csv(need(PAPERS))
               if r["source"] == "abstract" and r.get("full_text_warranted") == "yes"]
    os.makedirs(FTDIR, exist_ok=True)
    worklist, got, fetched_now = [], 0, 0
    for i, pmid in enumerate(flagged, 1):
        out = os.path.join(FTDIR, f"{pmid}.txt")
        if os.path.exists(out) and os.path.getsize(out) > MIN_CHARS:
            got += 1
            continue
        rec = sample[pmid]
        text = ""
        if rec.get("pmc"):
            try:
                text = pmc_text(rec["pmc"])
            except Exception as e:
                print(f"  {pmid}: PMC fetch failed ({type(e).__name__})")
        if len(text) > MIN_CHARS:
            with open(out, "w", encoding="utf-8") as f:
                f.write(text)
            got += 1
            fetched_now += 1
            print(f"  [{i}/{len(flagged)}] {pmid}: {len(text):,} chars from PMC")
        else:
            link = unpaywall_link(rec["doi"]) if rec.get("doi") else ""
            worklist.append({"pmid": pmid, "title": rec["title"], "year": rec["year"],
                             "journal": rec["journal"], "doi": rec.get("doi", ""),
                             "free_copy_link": link,
                             "action": "save the free copy as text" if link else "get via library",
                             "save_as": f"data/fulltext/{pmid}.txt"})
            print(f"  [{i}/{len(flagged)}] {pmid}: manual" + (" (free link found)" if link else ""))
        time.sleep(0.34)

    write_csv(WORKLIST, worklist,
              ["pmid", "title", "year", "journal", "doi", "free_copy_link", "action", "save_as"])
    print(f"\n  flagged: {len(flagged)}   full text on disk: {got} ({fetched_now} fetched now)"
          f"   manual worklist: {len(worklist)}")
    prov = provenance(os.path.abspath(__file__))
    prov.update({"flagged": len(flagged), "fulltext_on_disk": got, "manual": len(worklist)})
    write_json(os.path.join(DATA, "07_fulltext_manifest.json"), prov)
    print("\nNext: python3 scripts/06_extract.py --fulltext")


if __name__ == "__main__":
    main()
