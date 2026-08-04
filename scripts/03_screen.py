"""
STEP 3 - Have two AI models screen the titles and abstracts.

Each model sees one record at a time and answers include/exclude with a reason.
Both models' answers are saved. Where they disagree, a human decides.

BEFORE RUNNING, set your API keys in the terminal:
    export OPENAI_API_KEY=sk-...
    export ANTHROPIC_API_KEY=sk-ant-...

Run it with:   python3 scripts/03_screen.py
To test on 20 records first (do this):   python3 scripts/03_screen.py 20

COST: about $17 for all 10,767 records across both cheap models at standard rates,
or about $8.50 if you route it through each vendor's Batch API (50% off, and this
job has no reason to be interactive). See README for the full breakdown.
"""
import argparse, os, sys, json, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_csv, write_csv, need, DATA

PROMPT = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "prompts","screen_prompt.txt")).read()
# --- MODEL CHOICE -----------------------------------------------------------
# Model names change often. Copy the exact model ID from the vendor pages:
#   https://developers.openai.com/api/docs/pricing
#   https://platform.claude.com/docs/en/about-claude/pricing
# For SCREENING (a yes/no call on an abstract), use the cheap small models -
# small models handle this fine, which is exactly why step 7 measures
# sensitivity instead of assuming it.
# For EXTRACTION (steps 6, 8, 9), override to the stronger models below -
# extraction requires careful, specific demand/situation splitting with
# strict verbatim quotes, which is the harder task and where model quality
# actually shows. Putting a cheap model there to save money spends the
# saving on the step that costs you the most in quality.
OPENAI_MODEL    = "gpt-5.6-luna"        # cheap tier, $0.10 / $0.60 per Mtok
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"  # cheap tier, $1 / $5 per Mtok
# Recommended for steps 6/8/9 instead: "gpt-5.6-terra" and "claude-sonnet-5"

# Parameters a given model refuses. Once we learn one, stop sending it.
DROPPED = set()

def post(url, payload, headers, _depth=0):
    """Send a request. If the API rejects one parameter as unsupported, drop that
    parameter and retry. Newer models keep tightening what they accept (for example
    refusing temperature=0, or wanting max_completion_tokens instead of max_tokens),
    and hard-coding around each one means a failed overnight run every time."""
    import urllib.error, re
    payload = {k: v for k, v in payload.items() if k not in DROPPED}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
        headers={"Content-Type":"application/json", **headers})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=120).read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        if e.code == 400 and _depth < 4:
            # Special case, checked FIRST: response_format=json_object requires the
            # literal word "json" somewhere in the messages. When that check fails,
            # OpenAI reports it as `"param": "messages"` - if the generic handler
            # below saw that, it would try to drop the "messages" field itself and
            # break the request completely. The actual fix is to drop
            # response_format (our prompts already instruct JSON output in plain
            # English, so the model still returns parseable JSON most of the time;
            # parse_json() below is the safety net for when it wraps it in prose).
            if ("response_format" in body or "json_object" in body) and "json" in body.lower() \
               and "response_format" in payload:
                payload.pop("response_format")
                DROPPED.add("response_format")
                print("      note: this model needs the word 'json' in messages for "
                      "response_format=json_object; dropping response_format instead "
                      "of trying to drop 'messages'")
                return post(url, payload, headers, _depth + 1)
            # Find which parameter it objected to, e.g.
            # "Unsupported value: 'temperature' does not support 0 with this model"
            m = (re.search(r"Unsupported (?:value|parameter):?\s*'([\w_]+)'", body)
                 or re.search(r"'([\w_]+)' is not supported", body)
                 or re.search(r'"param"\s*:\s*"([\w_]+)"', body))
            bad = m.group(1) if m else None
            if bad and bad in payload and bad != "messages":
                DROPPED.add(bad)
                print(f"      note: this model rejects '{bad}' - dropping it and retrying")
                return post(url, payload, headers, _depth + 1)
            if "max_tokens" in body and "max_completion_tokens" in body and "max_tokens" in payload:
                payload["max_completion_tokens"] = payload.pop("max_tokens")
                print("      note: switching max_tokens -> max_completion_tokens")
                return post(url, payload, headers, _depth + 1)
        raise RuntimeError(f"HTTP {e.code}: {body[:400]}") from None

def parse_json(txt):
    """Pull JSON out of a reply. Needed because if the model refuses
    response_format=json_object, it may wrap the JSON in markdown fences or add a
    sentence around it."""
    txt = (txt or "").strip()
    if txt.startswith("```"):
        txt = txt.split("```")[1]
        if txt.lstrip().lower().startswith("json"):
            txt = txt.lstrip()[4:]
        txt = txt.strip()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        a, b = txt.find("{"), txt.rfind("}")
        if a != -1 and b > a:
            return json.loads(txt[a:b+1])
        raise

def ask_openai(record):
    key = os.environ.get("OPENAI_API_KEY")
    if not key: return {"decision":"","reason":"no OPENAI_API_KEY set"}
    r = post("https://api.openai.com/v1/chat/completions",
        # temperature 0 is requested for reproducibility. Some models refuse it;
        # post() detects that, drops it, and carries on. See the note in the README
        # about what losing temperature 0 means for reproducibility.
        {"model":OPENAI_MODEL,"temperature":0,
         "response_format":{"type":"json_object"},
         "messages":[{"role":"system","content":PROMPT},{"role":"user","content":record}]},
        {"Authorization":"Bearer "+key})
    return parse_json(r["choices"][0]["message"]["content"])

def ask_anthropic(record):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key: return {"decision":"","reason":"no ANTHROPIC_API_KEY set"}
    r = post("https://api.anthropic.com/v1/messages",
        {"model":ANTHROPIC_MODEL,"max_tokens":600,"temperature":0,
         "system":PROMPT,
         "messages":[{"role":"user","content":record+"\n\nReturn only the JSON."}]},
        {"x-api-key":key,"anthropic-version":"2023-06-01"})
    return parse_json(r["content"][0]["text"])

def as_text(r):
    return f"TITLE: {r['title']}\nJOURNAL: {r['journal']} ({r['year']})\nABSTRACT: {r['abstract'] or '[no abstract available]'}"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Screen literature-review records with two models.")
    parser.add_argument("limit", nargs="?", type=int, help="optional number of records to screen")
    parser.add_argument("--input", default=os.path.join(DATA, "02_unique_records.csv"),
                        help="input CSV (default: broad-search screening list)")
    parser.add_argument("--output", default=os.path.join(DATA, "03_screening.csv"),
                        help="output CSV (default: broad-search screening output)")
    parser.add_argument("--prompt", default=None, help="alternative screening prompt file")
    parser.add_argument("--start", type=int, default=1,
                        help="1-based first record to screen (default: 1)")
    args = parser.parse_args()
    limit = args.limit
    if args.prompt:
        PROMPT = open(args.prompt, encoding="utf-8").read()
    rows = read_csv(need(args.input))
    rows = rows[args.start - 1:]
    if limit: rows = rows[:limit]
    outpath = args.output
    done = {r["pmid"] for r in read_csv(outpath)} if os.path.exists(outpath) else set()
    results = read_csv(outpath) if os.path.exists(outpath) else []
    print(f"  {len(rows)} to screen, {len(done)} already done (safe to re-run after a crash)")
    for i, r in enumerate(rows, 1):
        if r["pmid"] in done: continue
        txt = as_text(r)
        row = {k:r[k] for k in ("screen_order","batch","pmid","year","journal","title","doi","pmc")}
        row["source_setting"] = r.get("source_setting", "")
        row["abstract"] = r.get("abstract","")   # keep it in the output, so the file stands alone
        for name, fn in (("gpt", ask_openai), ("claude", ask_anthropic)):
            try:
                a = fn(txt)
                row[name+"_decision"]   = a.get("decision","")
                row[name+"_confidence"] = a.get("confidence","")
                row[name+"_reason"]     = a.get("reason","")
                row[name+"_track"]      = a.get("track","")
                row[name+"_demands"]    = "; ".join(a.get("cognitive_demands") or [])
                row[name+"_situations"] = "; ".join(a.get("clinical_situations") or [])
                row[name+"_risk"]       = a.get("risk_evidence","")
            except Exception as e:
                row[name+"_decision"] = "ERROR"; row[name+"_reason"] = str(e)[:120]
            time.sleep(0.2)
        g, c = row.get("gpt_decision"), row.get("claude_decision")
        row["agree"] = "yes" if g == c else "no"
        row["needs_human"] = "yes" if (g != c or "low" in (row.get("gpt_confidence",""),
                                                           row.get("claude_confidence",""))) else "no"
        results.append(row)
        if i % 25 == 0 or i == len(rows):
            write_csv(outpath, results, ["screen_order","batch","source_setting","pmid","year","journal","title","abstract","doi","pmc",
                "gpt_decision","gpt_track","gpt_confidence","gpt_reason","gpt_demands","gpt_situations","gpt_risk",
                "claude_decision","claude_track","claude_confidence","claude_reason","claude_demands","claude_situations","claude_risk",
                "agree","needs_human"])
            print(f"    {i}/{len(rows)} screened")
    inc = sum(1 for r in results if "include" in (r.get("gpt_decision",""), r.get("claude_decision","")))
    dis = sum(1 for r in results if r.get("agree")=="no")
    print(f"\n  flagged include by at least one model: {inc}")
    print(f"  models disagreed: {dis} ({100*dis/max(len(results),1):.0f}%) - a human must resolve these")
    print("\nDone -> data/03_screening.csv")
