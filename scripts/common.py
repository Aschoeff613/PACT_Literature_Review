"""
Shared helpers for steps 1-3 of the PACT targeted literature review.
You do not run this file directly.

Environment variables it reads:
  PACT_EMAIL        required by NCBI. They throttle anonymous callers.
  NCBI_API_KEY      optional. Raises the rate limit from 3/sec to 10/sec.
  OPENROUTER_API_KEY  used by 03_screen.py only.
"""
import csv
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

EMAIL = os.environ.get("PACT_EMAIL", "")
NCBI_KEY = os.environ.get("NCBI_API_KEY", "")
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
PROMPTS = os.path.join(ROOT, "prompts")

# NCBI allows 3 requests/sec without a key, 10/sec with one.
_MIN_INTERVAL = 0.11 if NCBI_KEY else 0.34
_last_call = [0.0]


def _throttle():
    gap = time.time() - _last_call[0]
    if gap < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - gap)
    _last_call[0] = time.time()


def require_email():
    if not EMAIL:
        sys.exit(
            "ERROR: PACT_EMAIL is not set.\n"
            "  NCBI requires a contact address and will throttle or block you without one.\n"
            '  Run:  export PACT_EMAIL="you@stanford.edu"'
        )


def eutils(endpoint, params, tries=5, timeout=120):
    """
    Call an E-utilities endpoint. Rate limited and retried.

    POST, not GET. The union queries in 01_search.py OR together ~90 MeSH/tiab
    terms and run to 4,000+ characters before URL-encoding, well past the
    ~2,000-char length NCBI recommends for GET. POST puts the same params in
    the request body instead, which NCBI accepts identically on every eutils
    endpoint.
    """
    p = dict(params)
    p["email"] = EMAIL
    p["tool"] = "PACT-lit-review"
    if NCBI_KEY:
        p["api_key"] = NCBI_KEY
    url = EUTILS + endpoint
    data = urllib.parse.urlencode(p).encode("utf-8")
    last = None
    for attempt in range(tries):
        _throttle()
        try:
            req = urllib.request.Request(
                url, data=data, headers={"User-Agent": f"PACT-lit-review/2.0 ({EMAIL})"}
            )
            return urllib.request.urlopen(req, timeout=timeout).read()
        except urllib.error.HTTPError as e:
            last = e
            # 429 = too fast, 5xx = NCBI having a moment. Both are worth retrying.
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2.0 * (attempt + 1))
                continue
            raise
        except Exception as e:
            last = e
            time.sleep(2.0 * (attempt + 1))
    raise last


def esearch_count(term):
    """How many PubMed records match this query. One cheap call."""
    r = json.loads(eutils("esearch.fcgi", {"db": "pubmed", "term": term,
                                           "retmax": 0, "retmode": "json"}))
    return int(r["esearchresult"]["count"])


_ESEARCH_RETSTART_CAP = 9998  # NCBI hard limit, confirmed live: "ESearch can only
# retrieve the first 9,999 records matching the query." usehistory=y + WebEnv/
# query_key does NOT lift it for ESearch or ESummary paging -- confirmed by
# calling both directly. NCBI's own error message points at their EDirect CLI
# as the workaround; this project stays stdlib-only, so instead we partition
# the query by publication date until every partition is under the cap, page
# each with plain retstart, and merge. A PMID has exactly one pub date, so
# date partitions can't produce duplicates across partitions.


def _esearch_page_all(term, page):
    """Page a query that is already known to return <= _ESEARCH_RETSTART_CAP."""
    total = esearch_count(term)
    out, start = [], 0
    while start < total:
        r = json.loads(eutils("esearch.fcgi", {
            "db": "pubmed", "term": term, "retstart": start,
            "retmax": page, "retmode": "json"}))
        ids = r["esearchresult"].get("idlist", [])
        if not ids:
            break
        out.extend(ids)
        start += len(ids)
    return out


def _esearch_by_date_range(term, lo, hi, page):
    """Recurse on the [lo, hi] date.date window until each leaf query fits
    under the retstart cap, then page it directly."""
    q = f'{term} AND ("{lo:%Y/%m/%d}"[dp] : "{hi:%Y/%m/%d}"[dp])'
    n = esearch_count(q)
    if n > _ESEARCH_RETSTART_CAP and hi > lo:
        mid = lo + (hi - lo) // 2
        return (_esearch_by_date_range(term, lo, mid, page)
                + _esearch_by_date_range(term, mid + datetime.timedelta(days=1), hi, page))
    if n > _ESEARCH_RETSTART_CAP:
        # lo == hi: a single day over the cap. Not seen in practice for a
        # boolean literature query; surfacing loudly rather than silently
        # truncating the pull.
        raise RuntimeError(
            f"{lo:%Y-%m-%d} alone returns {n:,} records, over the "
            f"{_ESEARCH_RETSTART_CAP:,} per-query cap. Query too broad to "
            "page even at single-day granularity."
        )
    return _esearch_page_all(q, page)


def esearch_all_pmids(term, page=9000, cap=200000):
    """
    Every PMID matching a query, paged.

    PMID lists are tiny, so pulling a 40,000-record list costs seconds. This
    is why step 1 does not download abstracts: it only needs the identifiers,
    and step 2 fetches metadata for the 500 papers actually drawn.
    """
    total = esearch_count(term)
    if total > cap:
        raise RuntimeError(
            f"query returns {total:,} records, above the {cap:,} safety cap.\n"
            "  Tighten the query or raise cap= deliberately."
        )
    if total <= _ESEARCH_RETSTART_CAP:
        out = _esearch_page_all(term, page)
    else:
        out = _esearch_by_date_range(
            term, datetime.date(1990, 1, 1), datetime.date.today(), page)
        seen = set()
        out = [p for p in out if not (p in seen or seen.add(p))]
    print(f"      {len(out):,}/{total:,} ids")
    # PubMed occasionally reports a count that differs from what it will serve.
    return out, total


def efetch_records(pmids, chunk=200):
    """
    Title, abstract, journal, year, DOI, PMC id, authors, publication types.

    Uses efetch XML, not esummary, because esummary has no abstract field.
    Parsed with the regex approach from the original repo rather than an XML
    library, so this still runs with no third-party packages installed.
    """
    import html
    import re

    out = []
    for i in range(0, len(pmids), chunk):
        block = pmids[i:i + chunk]
        xml = eutils("efetch.fcgi", {"db": "pubmed", "id": ",".join(block),
                                     "retmode": "xml"}).decode("utf-8", "ignore")
        for art in re.findall(r"<PubmedArticle>.*?</PubmedArticle>", xml, re.S):
            def one(pat):
                m = re.search(pat, art, re.S)
                return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""

            # Structured abstracts arrive as several AbstractText elements with
            # Label attributes. Keep the labels: they help a screener a lot.
            #
            # Do not filter by NlmCategory="UNASSIGNED". That attribute does not
            # mean "not real abstract content" -- NLM applies it to a labeled
            # section whenever the label text doesn't match one of its fixed
            # category names, which happens for ordinary sections too (seen
            # live: a paper's BACKGROUND/METHODS/RESULTS/CONCLUSION were all
            # marked UNASSIGNED while an unrelated plain-language-summary blurb
            # with no label was not). Excluding on it silently dropped the real
            # abstract for ~1% of a real 500-paper sample.
            parts = []
            for label, body in re.findall(
                    r'<AbstractText([^>]*)>(.*?)</AbstractText>', art, re.S):
                lm = re.search(r'Label="([^"]+)"', label)
                txt = html.unescape(re.sub(r"<[^>]+>", "", body)).strip()
                if not txt:
                    continue
                parts.append(f"{lm.group(1)}: {txt}" if lm else txt)
            # ArticleId lookup: use only the article's own <ArticleIdList>, not
            # the whole record. <PubmedData><ReferenceList> holds one ArticleId
            # block per cited reference, each of which can carry its own doi/
            # pmc/pubmed ids; a dict() over the whole record keeps whichever
            # one appears last, i.e. some cited reference's identifiers, not
            # the article's. The article's own ArticleIdList always precedes
            # ReferenceList in the PubMed XML schema, so cut there first.
            # Verified live: this was wrong for 32% of dois and 45% of pmcs in
            # a real 500-paper sample.
            own_ids_xml = art.split("<ReferenceList>", 1)[0]
            ids = dict(re.findall(r'<ArticleId IdType="(\w+)">(.*?)</ArticleId>', own_ids_xml))
            names = re.findall(r"<LastName>(.*?)</LastName>", art)
            ptypes = [html.unescape(t).strip() for t in
                      re.findall(r"<PublicationType[^>]*>(.*?)</PublicationType>", art, re.S)]
            out.append({
                "pmid": one(r"<PMID[^>]*>(.*?)</PMID>"),
                "year": one(r"<PubDate>.*?<Year>(\d{4})</Year>") or one(r"<Year>(\d{4})</Year>"),
                "journal": one(r"<ISOAbbreviation>(.*?)</ISOAbbreviation>"),
                "title": one(r"<ArticleTitle[^>]*>(.*?)</ArticleTitle>"),
                "abstract": " ".join(parts),
                "doi": ids.get("doi", ""),
                "pmc": ids.get("pmc", ""),
                "authors": "; ".join(names[:3]) + (" et al." if len(names) > 3 else ""),
                "pub_types": "; ".join(ptypes),
            })
        print(f"    fetched {min(i + chunk, len(pmids))}/{len(pmids)}", end="\r", flush=True)
    print(f"    fetched {len(out)}/{len(pmids)}      ")
    return out


# --------------------------------------------------------------------------
# CSV / JSON
# --------------------------------------------------------------------------

def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"  wrote {len(rows)} rows -> {os.path.relpath(path, ROOT)}")


def read_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    print(f"  wrote {os.path.relpath(path, ROOT)}")


def need(path):
    if not os.path.exists(path):
        sys.exit(f"ERROR: expected file not found:\n  {path}\nRun the earlier numbered script first.")
    return path


# --------------------------------------------------------------------------
# Provenance. The protocol says: record which prompt file and which version of
# the code were used, before running each step. This makes that automatic
# instead of a thing someone remembers to write down.
# --------------------------------------------------------------------------

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()[:16]


def git_version():
    try:
        rev = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                      cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"],
                                        cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
        return rev + ("-dirty" if dirty else "")
    except Exception:
        return "not-a-git-repo"


def provenance(script_path, extra_files=()):
    """Everything needed to say exactly what produced an output file."""
    p = {
        "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_version": git_version(),
        "script": os.path.basename(script_path),
        "script_sha256_16": sha256_file(script_path),
        "common_sha256_16": sha256_file(os.path.abspath(__file__)),
        "python": sys.version.split()[0],
    }
    for f in extra_files:
        p[os.path.basename(f) + "_sha256_16"] = sha256_file(f)
    if p["git_version"].endswith("-dirty"):
        print("  NOTE: uncommitted changes present. Commit before a real run so the "
              "version stamp is meaningful.")
    return p
