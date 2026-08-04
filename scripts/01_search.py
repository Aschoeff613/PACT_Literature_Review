"""
STEP 1 - Search PubMed with ONE broad, unconditioned query.

Earlier versions of this script required every record to match one of 12
pre-specified "decision families" (disposition, triage, handoff, etc.). That was
a mistake: it meant the search could only ever return evidence for categories we
had already picked, so "the literature supports these 12 tasks" was true by
construction, not by discovery. A reviewer would be right to ask how that is
different from searching for what you already believe.

This version drops the family filter entirely. A record is in scope if it is
about adult ED or primary care AND it discusses EITHER a cognitive process in
clinician reasoning OR a signal of diagnostic/workflow harm (error, delay, near
miss, malpractice claim, etc). That is the full inductive net: nothing about
which specific tasks matter is baked into the search. The task list is supposed
to emerge later, from clustering what these records actually say (step 8).

Tested on the dates below:
  SETTING AND COGNITION only:                 2,331
  SETTING AND HARM only:                      4,161
  SETTING AND (COGNITION OR HARM), this query: 5,730

Run it with:   python3 scripts/01_search.py
"""
import json, urllib.parse, os, sys, re, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import fetch, write_csv, EUTILS, EMAIL, DATA

DATES = "AND 2005:2026[dp] AND English[lang]"

SETTING = """("Emergency Service, Hospital"[majr] OR "Emergency Medicine"[majr] OR "Primary Health Care"[majr] OR "General Practice"[majr] OR "General Practitioners"[majr] OR "Physicians, Primary Care"[majr] OR "Family Practice"[majr] OR "emergency department"[ti] OR "emergency physician"[ti] OR "emergency physicians"[ti] OR "emergency medicine"[ti] OR "primary care"[ti] OR "general practice"[ti] OR "general practitioner"[ti] OR "general practitioners"[ti] OR "family physician"[ti] OR "family physicians"[ti])"""

# Cognitive-PROCESS signal: the paper names how clinicians reason, without
# reference to any specific clinical situation. This is the "demand" half.
COGNITION = """("Clinical Reasoning"[MeSH] OR "Diagnostic Errors"[majr] OR "clinical reasoning"[tiab] OR "diagnostic reasoning"[tiab] OR "clinical judgment"[tiab] OR "clinical judgement"[tiab] OR "clinical gestalt"[tiab] OR "physician judgment"[tiab] OR "physician gestalt"[tiab] OR "cognitive bias"[tiab] OR "cognitive biases"[tiab] OR "diagnostic error"[tiab] OR "diagnostic errors"[tiab] OR "diagnostic uncertainty"[tiab] OR "decision-making under uncertainty"[tiab] OR "premature closure"[tiab] OR "anchoring bias"[tiab] OR "cognitive load"[tiab] OR "situation awareness"[tiab] OR "overconfidence"[tiab] OR "missed diagnosis"[tiab] OR "missed diagnoses"[tiab] OR "delayed diagnosis"[tiab] OR "diagnostic delay"[tiab] OR "missed opportunity"[tiab] OR "missed opportunities"[tiab] OR "clinician decision"[tiab] OR "physician decision"[tiab] OR "decision fatigue"[tiab] OR "clinical intuition"[tiab])"""

# HARM signal: the paper documents error, delay, or failure with some evidence
# attached, regardless of whether it names a cognitive process. This is the
# "situation" half - it is what strands 5-7 were reaching for, generalised so it
# is not limited to a pre-chosen list of failure types.
HARM = """("diagnostic error"[tiab] OR "diagnostic errors"[tiab] OR "missed diagnosis"[tiab] OR "missed diagnoses"[tiab] OR "delayed diagnosis"[tiab] OR "diagnostic delay"[tiab] OR "adverse event"[tiab] OR "adverse events"[tiab] OR "medical error"[tiab] OR "medical errors"[tiab] OR "never event"[tiab] OR "sentinel event"[tiab] OR malpractice[tiab] OR "malpractice claim"[tiab] OR "malpractice claims"[tiab] OR "patient safety incident"[tiab] OR "near miss"[tiab] OR "near-miss"[tiab] OR "root cause analysis"[tiab] OR undertriage[tiab] OR "under-triage"[tiab] OR "failure to rescue"[tiab])"""

# Excluded: other specialties, paediatrics, ICU, non-physicians, med-ed-only,
# case reports and editorials, and patient-cognition topics that hijack the word
# "cognitive" (dementia, cognitive impairment, CBT). None of this touches WHICH
# tasks are in scope - only who/where/what kind of source.
EXCLUDE = """NOT ("Pediatrics"[majr] OR "Infant"[majr] OR "Child"[majr] OR child[ti] OR children[ti] OR pediatric[ti] OR paediatric[ti] OR infant[ti] OR infants[ti] OR neonatal[ti] OR "Intensive Care Units"[majr] OR "Radiology"[majr] OR "Pathology"[majr] OR "Psychiatry"[majr] OR "Dentistry"[majr] OR "Students, Medical"[majr] OR "Education, Medical"[majr] OR "Internship and Residency"[majr] OR veterinary[ti] OR nurses[ti] OR nursing[ti] OR pharmacist[ti] OR pharmacists[ti] OR dental[ti])
NOT ("Case Reports"[pt] OR Editorial[pt] OR Comment[pt] OR Letter[pt] OR "Historical Article"[pt])
NOT ("Cognitive Dysfunction"[majr] OR "Cognitive Behavioral Therapy"[majr] OR "Dementia"[majr] OR "Cognition Disorders"[majr] OR "Neuropsychological Tests"[majr] OR "cognitive impairment"[ti] OR "cognitive decline"[ti] OR "cognitive behavioral"[ti] OR "cognitive screening"[ti] OR "cognitive function"[ti])"""

TERM = f"{SETTING} AND ({COGNITION} OR {HARM}) {EXCLUDE} {DATES}"

FIELDS = ["pmid","source_signal","year","journal","title","abstract","doi","pmc","authors"]

def search(term):
    q = urllib.parse.urlencode({"db":"pubmed","term":term,"retmax":10000,
                                "retmode":"json","email":EMAIL})
    r = json.loads(fetch(EUTILS+"esearch.fcgi?"+q))["esearchresult"]
    return r["idlist"], int(r["count"])

def details(pmids):
    out=[]
    for i in range(0,len(pmids),150):
        chunk=pmids[i:i+150]
        q=urllib.parse.urlencode({"db":"pubmed","id":",".join(chunk),"retmode":"xml","email":EMAIL})
        xml=fetch(EUTILS+"efetch.fcgi?"+q).decode("utf-8","ignore")
        for art in re.findall(r"<PubmedArticle>.*?</PubmedArticle>", xml, re.S):
            def one(pat):
                m=re.search(pat,art,re.S)
                return html.unescape(re.sub(r"<[^>]+>","",m.group(1))).strip() if m else ""
            abstract=" ".join(html.unescape(re.sub(r"<[^>]+>","",t)).strip()
                for t in re.findall(r"<AbstractText[^>]*>(.*?)</AbstractText>",art,re.S))
            ids=dict(re.findall(r'<ArticleId IdType="(\w+)">(.*?)</ArticleId>',art))
            names=re.findall(r"<LastName>(.*?)</LastName>",art)
            out.append({"pmid":one(r"<PMID[^>]*>(.*?)</PMID>"),
                "year":one(r"<PubDate>.*?<Year>(\d{4})</Year>") or one(r"<Year>(\d{4})</Year>"),
                "journal":one(r"<ISOAbbreviation>(.*?)</ISOAbbreviation>"),
                "title":one(r"<ArticleTitle[^>]*>(.*?)</ArticleTitle>"),
                "abstract":abstract,"doi":ids.get("doi",""),"pmc":ids.get("pmc",""),
                "authors":"; ".join(names[:3])+(" et al." if len(names)>3 else "")})
    return out

if __name__ == "__main__":
    ids, count = search(TERM)
    print(f"  {count} hits (broad, unconditioned net - no task categories assumed)")
    rows = details(ids)
    # source_signal is informational only (which half of the net caught it) -
    # it is NOT used anywhere downstream to sort records into pre-set buckets.
    for r in rows:
        r["source_signal"] = "unlabelled"
    write_csv(os.path.join(DATA,"01_all_records.csv"), rows, FIELDS)
    write_csv(os.path.join(DATA,"01_search_log.csv"),
        [{"query":TERM,"hits":count,"downloaded":len(rows)}], ["query","hits","downloaded"])
    print(f"\n  {len(rows)} rows downloaded (duplicates removed in step 2)")
    print("  Nothing here is pre-sorted into a task or family. That happens inductively")
    print("  in step 8, from what the extracted papers actually say.")
