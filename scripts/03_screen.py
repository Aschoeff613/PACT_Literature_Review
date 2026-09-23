"""
STEP 3 - AI screening.

Protocol v7, step 3: two models read all 500 titles and abstracts separately and
decide whether each paper is in scope. When a model is unsure, it includes.
Record which prompt file and which version of the code were used.

Routed through OpenRouter, so one API key covers both models.

Model choice
------------
The two models should come from different families. Two models from the same
family share training data and failure modes, so their agreement measures shared
bias rather than correctness. Their agreement is reported as a description, not
as validation. The 300-paper human check in step 4 is the validation.

Model IDs go stale fast. Set them from openrouter.ai/models before the first
run, or override without touching the file:

    export PACT_MODEL_A="vendor/model-name"
    export PACT_MODEL_B="othervendor/other-model"

Then always:

    python3 scripts/03_screen.py --check      # 1 record, both models, prints raw output
    python3 scripts/03_screen.py --limit 20   # 20 records, read the reasons
    python3 scripts/03_screen.py              # all 500

--check exists because a wrong model ID, a bad key, or a model that will not
emit clean JSON all fail on the first call, and finding that out on call 1 costs
nothing while finding out on call 400 costs an evening.

Cost note: 500 records is roughly 5% of the token volume the old README budgeted
for, because that version screened all 10,767. At v7's sample size, screening is
cents, not dollars. The README's cost table describes the superseded design.
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, PROMPTS, need, provenance, read_csv, write_csv,
                    write_json)

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# Verify both against openrouter.ai/models before running. --check will fail
# immediately if either is wrong.
MODEL_A = os.environ.get("PACT_MODEL_A", "openai/gpt-4o-mini")
MODEL_B = os.environ.get("PACT_MODEL_B", "anthropic/claude-3.5-haiku")

PROMPT_FILE = os.path.join(PROMPTS, "screen_prompt_v7.txt")
IN_FILE = os.path.join(DATA, "11_sample_500.csv")
OUT_FILE = os.path.join(DATA, "03_screening.csv")
DECISION_ID = "2026-09-22-search-tightening"

FIELDS = [
    "record_no", "batch_100", "block_50", "pmid", "source_setting", "year",
    "journal", "title",
    "a_model", "a_decision", "a_confidence", "a_reason", "a_setting_seen", "a_tasks",
    "b_model", "b_decision", "b_confidence", "b_reason", "b_setting_seen", "b_tasks",
    "agree", "either_include", "setting_mismatch", "run_utc",
]


def load_prompt():
    with open(need(PROMPT_FILE), encoding="utf-8") as f:
        return f.read()


def verify_sample_provenance():
    path = need(os.path.join(DATA, "11_sample_manifest.json"))
    with open(path, encoding="utf-8") as f:
        manifest = json.load(f)
    if (manifest.get("decision_id") != DECISION_ID
            or manifest.get("overlap_rule") != "drop"):
        sys.exit(
            "ERROR: the saved 500-paper sample predates the current method "
            "amendment (" + DECISION_ID + ").\n"
            "  Re-run steps 1 and 2 before screening. See data/README.md."
        )


def api_key():
    k = os.environ.get("OPENROUTER_API_KEY", "")
    if not k:
        sys.exit('ERROR: OPENROUTER_API_KEY is not set.\n'
                 '  export OPENROUTER_API_KEY="sk-or-..."')
    return k


def call_model(model, system_prompt, user_text, tries=4):
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 700,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
    }
    headers = {
        "Authorization": "Bearer " + api_key(),
        "Content-Type": "application/json",
        # OpenRouter uses these for attribution. Harmless, and it keeps the
        # request identifiable in Austin's usage dashboard.
        "HTTP-Referer": "https://github.com/Aschoeff613/PACT_Literature_Review",
        "X-Title": "PACT literature review screening",
    }
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                ENDPOINT, data=json.dumps(payload).encode(), headers=headers)
            body = json.loads(urllib.request.urlopen(req, timeout=180).read())
            return body["choices"][0]["message"]["content"]
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


def parse_json(text):
    """
    Models sometimes wrap JSON in fences or add a sentence despite instructions.
    Strip the wrapper rather than lose the record.
    """
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


def as_text(r):
    return (f"TITLE: {r['title']}\n"
            f"JOURNAL: {r['journal']} ({r['year']})\n"
            f"ABSTRACT: {r['abstract'] or '[no abstract available]'}")


def normalise(raw):
    d = (raw.get("decision") or "").strip().lower()
    if d not in ("include", "exclude"):
        d = "MALFORMED"
    tasks = raw.get("thinking_task_named") or []
    if isinstance(tasks, str):
        tasks = [tasks]
    return {
        "decision": d,
        "confidence": (raw.get("confidence") or "").strip().lower(),
        "reason": (raw.get("reason") or "").strip()[:200],
        "setting_seen": (raw.get("setting_seen") or "").strip().lower(),
        "tasks": "; ".join(str(t) for t in tasks)[:400],
    }


def check_mode(prompt):
    rows = read_csv(need(IN_FILE))
    r = rows[0]
    print(f"  test record: PMID {r['pmid']} — {r['title'][:70]}\n")
    for tag, model in (("A", MODEL_A), ("B", MODEL_B)):
        print(f"  --- {tag}: {model} ---")
        try:
            raw = call_model(model, prompt, as_text(r))
            print("  raw output:", raw.strip()[:400])
            print("  parsed:   ", normalise(parse_json(raw)))
        except Exception as e:
            print(f"  FAILED: {e}")
            print("  Fix the model ID or the key before going further.")
            return False
        print()
    print("  Both models responded and parsed. Now run --limit 20 and read the reasons.")
    return True


def main():
    verify_sample_provenance()
    prompt = load_prompt()
    prov = provenance(os.path.abspath(__file__), extra_files=[PROMPT_FILE])
    prov.update({"model_a": MODEL_A, "model_b": MODEL_B,
                 "decision_id": DECISION_ID,
                 "prompt_file": os.path.basename(PROMPT_FILE),
                 "endpoint": ENDPOINT})

    if "--check" in sys.argv:
        check_mode(prompt)
        return

    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    rows = read_csv(need(IN_FILE))
    if limit:
        rows = rows[:limit]

    # Resume. Safe to re-run after a crash or a closed laptop.
    results = read_csv(OUT_FILE) if os.path.exists(OUT_FILE) else []
    done = {r["pmid"] for r in results
            if r.get("a_decision") not in ("", "ERROR", "MALFORMED")
            and r.get("b_decision") not in ("", "ERROR", "MALFORMED")}
    # Keep only rows for papers in the CURRENT sample, and refresh their
    # position fields from it. When the sample is enlarged, a paper keeps its
    # PMID but gets a new record_no / batch_100 / block_50; stale values here
    # would corrupt step 4 blocks and the step 13 saturation plot.
    current = {r["pmid"]: r for r in rows}
    results = [r for r in results if r["pmid"] in done and r["pmid"] in current]
    for r in results:
        for k in ("record_no", "batch_100", "block_50", "source_setting"):
            r[k] = current[r["pmid"]].get(k, "")
    todo = [r for r in rows if r["pmid"] not in done]
    print(f"  {len(rows)} in sample, {len(done)} already screened, {len(todo)} to do")

    # Kept rows are not re-screened. If PACT_MODEL_A/B changed since they were
    # written, the CSV would silently mix two models under one column with no
    # record of which rows came from which -- warn loudly instead.
    stale = [(r["pmid"], tag, r.get(tag + "_model") or "(not recorded)", cur)
             for r in results
             for tag, cur in (("a", MODEL_A), ("b", MODEL_B))
             if r.get(tag + "_model") != cur]
    if stale:
        print(f"  WARNING: {len(stale)} already-screened decision(s) were made "
              f"by a different model than the current PACT_MODEL_A/B. They will "
              f"be kept as-is, not re-screened -- the run will mix models under "
              f"one column. Delete {os.path.relpath(OUT_FILE, DATA)} and re-run "
              f"from scratch for a single consistent model throughout. First few:")
        for pmid, tag, prior, cur in stale[:5]:
            print(f"    pmid {pmid} [{tag}]: recorded {prior!r}, current {cur!r}")

    workers = 1
    if "--workers" in sys.argv:
        workers = max(1, int(sys.argv[sys.argv.index("--workers") + 1]))

    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def screen_one(r):
        """Both models on one paper. Returns (row, number of errors)."""
        errs = 0
        out = {k: r.get(k, "") for k in
               ("record_no", "batch_100", "block_50", "pmid", "source_setting",
                "year", "journal", "title")}
        out["run_utc"] = stamp
        text = as_text(r)
        for tag, model in (("a", MODEL_A), ("b", MODEL_B)):
            out[tag + "_model"] = model
            try:
                d = normalise(parse_json(call_model(model, prompt, text)))
                out[tag + "_decision"] = d["decision"]
                out[tag + "_confidence"] = d["confidence"]
                out[tag + "_reason"] = d["reason"]
                out[tag + "_setting_seen"] = d["setting_seen"]
                out[tag + "_tasks"] = d["tasks"]
                if d["decision"] == "MALFORMED":
                    errs += 1
            except Exception as e:
                out[tag + "_decision"] = "ERROR"
                out[tag + "_reason"] = str(e)[:200]
                errs += 1
            time.sleep(0.2)

        da, db = out.get("a_decision"), out.get("b_decision")
        out["agree"] = "yes" if da == db else "no"
        out["either_include"] = "yes" if "include" in (da, db) else "no"
        # Both models, not "any non-blank model", have to say "neither" -- a
        # naive `all(... if s)` here is vacuously true when one model errored
        # and the other said "neither", which would overcount this.
        a_seen, b_seen = out.get("a_setting_seen", ""), out.get("b_setting_seen", "")
        out["setting_mismatch"] = "yes" if a_seen == "neither" and b_seen == "neither" else "no"
        return out, errs

    # --workers N screens N papers at once. Each paper is still read by both
    # models independently; only wall-clock time changes. Results are written
    # from this thread only, so the CSV is never written concurrently.
    def by_record_no(rs):
        return sorted(rs, key=lambda x: int(x.get("record_no") or 0))

    errors = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (out, errs) in enumerate(pool.map(screen_one, todo), 1):
            results.append(out)
            errors += errs
            if i % 20 == 0 or i == len(todo):
                write_csv(OUT_FILE, by_record_no(results), FIELDS)
                print(f"    {i}/{len(todo)} screened", flush=True)

    results = by_record_no(results)
    write_csv(OUT_FILE, results, FIELDS)

    scored = [r for r in results if r.get("a_decision") in ("include", "exclude")
              and r.get("b_decision") in ("include", "exclude")]
    n = max(len(scored), 1)
    inc_a = sum(1 for r in scored if r["a_decision"] == "include")
    inc_b = sum(1 for r in scored if r["b_decision"] == "include")
    either = sum(1 for r in scored if r["either_include"] == "yes")
    both = sum(1 for r in scored if r["a_decision"] == r["b_decision"] == "include")
    dis = sum(1 for r in scored if r["agree"] == "no")
    neither_setting = sum(1 for r in scored if r["setting_mismatch"] == "yes")

    print(f"\n  cleanly screened: {len(scored)} of {len(results)}  "
          f"(errors or malformed responses: {errors})")
    print(f"  model A include: {inc_a} ({100*inc_a/n:.0f}%)")
    print(f"  model B include: {inc_b} ({100*inc_b/n:.0f}%)")
    print(f"  either include:  {either} ({100*either/n:.0f}%)")
    print(f"  both include:    {both} ({100*both/n:.0f}%)")
    print(f"  disagreed:       {dis} ({100*dis/n:.0f}%)")
    print(f"  both models read the setting as neither EM nor primary care: "
          f"{neither_setting} ({100*neither_setting/n:.0f}%)")

    prov.update({"screened": len(results), "cleanly_screened": len(scored),
                 "errors": errors, "include_a": inc_a, "include_b": inc_b,
                 "either_include": either, "both_include": both,
                 "disagreed": dis, "setting_neither": neither_setting,
                 "limit": limit, "workers": workers})
    write_json(os.path.join(DATA, "03_screen_manifest.json"), prov)

    print("\n  Two things to read before step 4:")
    print("   - sort by a_reason / b_reason and skim 20. The reasons are the")
    print("     cheapest signal that the prompt is being read the way you meant.")
    print("   - the setting_mismatch count. If it is large, a chunk of the sample")
    print("     is out of scope on setting alone, and step 4's balanced 300 will")
    print("     partly be measuring setting detection rather than cognitive content.")
    print("\nDone -> data/03_screening.csv")


if __name__ == "__main__":
    main()
