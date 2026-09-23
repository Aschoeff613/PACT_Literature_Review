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
# PACT_DATA_DIR lets a test run read and write a scratch copy instead of the
# real data/ folder. Unset for every real run.
DATA = os.environ.get("PACT_DATA_DIR") or os.path.join(ROOT, "data")
# Reviewer pages and sheets. Test runs write them beside the scratch data
# so test material never lands in the repo.
VALIDATION = (os.path.join(DATA, "_validation") if os.environ.get("PACT_DATA_DIR")
              else os.path.join(ROOT, "validation"))
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


# --------------------------------------------------------------------------
# OpenRouter: one helper for every model call from step 7 onward.
# (03_screen.py keeps its own call_model so its recorded SHA stays meaningful.)
# --------------------------------------------------------------------------

OPENROUTER = "https://openrouter.ai/api/v1/"

# Hard ceiling on total spend on this OpenRouter key, across the whole
# pipeline. Checked before each batch of calls; the script stops, rather than
# overspends, when the next batch could cross it. The key's own "usage" figure
# is lifetime spend on the key, which is the right measure as long as the key
# is used for this project only.
BUDGET_USD = float(os.environ.get("PACT_BUDGET_USD", "50"))


class TruncatedResponse(RuntimeError):
    """The model stopped at max_tokens; retrying will not help. Still billed."""

    def __init__(self, msg, cost=0.0, partial=""):
        super().__init__(msg)
        self.cost = cost
        self.partial = partial


def openrouter_key():
    k = os.environ.get("OPENROUTER_API_KEY", "")
    if not k:
        sys.exit('ERROR: OPENROUTER_API_KEY is not set.\n'
                 '  Run:  set -a; . ./.env; set +a')
    return k


def openrouter_chat(model, system_prompt, user_text, max_tokens=3000,
                    tries=4, timeout=300):
    """
    One chat completion, temperature 0, JSON mode. Returns (text, cost_usd).
    Cost comes from OpenRouter's own accounting for the call.

    Hidden reasoning is switched off. Left on, current models can spend the
    whole max_tokens allowance reasoning about a long input and return an
    empty answer while billing every token. Seen live on a 43k-character
    paper: 8,000 reasoning tokens and no content; a 2,000-token reasoning cap
    was ignored. With reasoning off the same paper returned 10 complete rows
    for about a third of the cost.
    """
    payload = {
        "model": model, "temperature": 0, "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "reasoning": {"enabled": False},
        "usage": {"include": True},
        "messages": [{"role": "system", "content": system_prompt},
                     {"role": "user", "content": user_text}],
    }
    headers = {"Authorization": "Bearer " + openrouter_key(),
               "Content-Type": "application/json",
               "HTTP-Referer": "https://github.com/Aschoeff613/PACT_Literature_Review",
               "X-Title": "PACT literature review"}
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(OPENROUTER + "chat/completions",
                                         data=json.dumps(payload).encode(),
                                         headers=headers)
            body = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
            choice = body["choices"][0]
            cost = float((body.get("usage") or {}).get("cost") or 0)
            if choice.get("finish_reason") == "length":
                raise TruncatedResponse(
                    f"reply hit max_tokens={max_tokens} (cost ${cost:.4f})", cost,
                    choice["message"].get("content") or "")
            return choice["message"]["content"], cost
        except TruncatedResponse:
            raise
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:300]
            last = RuntimeError(f"HTTP {e.code}: {detail}")
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(3.0 * (attempt + 1))
                continue
            raise last
        except Exception as e:
            last = e
            time.sleep(3.0 * (attempt + 1))
    raise last


def parse_json_reply(text):
    """Strip code fences or stray prose around a JSON object."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("```")[1]
        if t.lower().startswith("json"):
            t = t[4:]
        t = t.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        i, j = t.find("{"), t.rfind("}")
        if i >= 0 and j > i:
            return json.loads(t[i:j + 1])
        raise


def key_spend():
    """Lifetime spend on the OpenRouter key, in USD."""
    req = urllib.request.Request(OPENROUTER + "key",
                                 headers={"Authorization": "Bearer " + openrouter_key()})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())["data"]
    return float(d["usage"])


def check_budget(next_batch_estimate_usd, what="next batch"):
    """Stop the script if the next batch could push spend past BUDGET_USD."""
    spent = key_spend()
    if spent + next_batch_estimate_usd > BUDGET_USD:
        sys.exit(
            f"\nSTOPPED by budget guard before the {what}.\n"
            f"  Spent so far on this key: ${spent:.2f}. Next batch estimated at "
            f"${next_batch_estimate_usd:.2f}. Ceiling PACT_BUDGET_USD=${BUDGET_USD:.2f}.\n"
            "  Everything done so far is saved; re-running resumes. Raise the\n"
            "  ceiling deliberately (export PACT_BUDGET_USD=...) only if agreed."
        )
    return spent


# --------------------------------------------------------------------------
# Quote verification (protocol v7 step 8, automatic part)
# --------------------------------------------------------------------------

def _norm_for_match(s):
    import html
    import re
    s = html.unescape(s or "").lower()
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'),
                 ("–", "-"), ("—", "-"), (" ", " ")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9%]+", " ", s)      # punctuation and spacing differences
    return re.sub(r"\s+", " ", s).strip()   # don't count as a mismatch


def quote_in_text(quote, text, min_words=6):
    """
    True when the quote appears word for word in the source text, ignoring
    case, punctuation and whitespace. Very short quotes fail: a four-word
    fragment proves almost nothing about what a paper says.
    """
    q = _norm_for_match(quote)
    return len(q.split()) >= min_words and q in _norm_for_match(text)


def salvage_json_list(partial, key):
    """
    Recover the complete objects from a JSON reply cut off mid-list, e.g.
    {"tasks": [{...}, {...}, {"task_na   ->  [{...}, {...}]
    """
    i = partial.find(f'"{key}"')
    if i < 0:
        return []
    i = partial.find("[", i)
    if i < 0:
        return []
    dec, out, pos = json.JSONDecoder(), [], i + 1
    while True:
        while pos < len(partial) and partial[pos] in " \t\r\n,":
            pos += 1
        if pos >= len(partial) or partial[pos] != "{":
            break
        try:
            obj, pos = dec.raw_decode(partial, pos)
        except json.JSONDecodeError:
            break
        out.append(obj)
    return out


def quote_check(quote, text, min_words=6):
    """
    'verbatim'  found word for word (case, punctuation, spacing ignored)
    'too_short' found, but under min_words: too short to prove anything
    'not_found' not in the text: paraphrased, stitched, or invented
    """
    q = _norm_for_match(quote)
    if not q or q not in _norm_for_match(text):
        return "not_found"
    return "verbatim" if len(q.split()) >= min_words else "too_short"
