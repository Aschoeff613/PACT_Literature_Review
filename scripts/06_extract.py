"""
STEP 7 - Pull the tasks out of the papers.

Protocol v7, step 7, run on every paper in the extraction set from step 6.
For each paper the model records: the paper's own name for a thinking task
(kept only if the paper also defines it), the paper's definition, an exact
supporting sentence, thinking process vs clinical activity, named biases as
failure modes, the clinical situation, and any error or frequency figure.
The prompt is prompts/extract_prompt_v7.txt. No task list is given to the
model at any point.

Abstract first, full text only when needed (v7): the model flags papers whose
abstract is too thin or names a task without defining it; papers whose quotes
cannot be confirmed are flagged too. Those go to full-text retrieval
(05_fulltext.py) and are extracted again from the full text, which then
replaces their abstract rows.

Every quote is checked word for word against the text it came from
(quote_verified). Unverified rows are kept in the file for the record and
excluded from grouping in step 8.

Run order:
    python3 scripts/06_extract.py                 # abstracts, whole set
    python3 scripts/05_fulltext.py                # fetch flagged full texts
    python3 scripts/06_extract.py --fulltext      # re-extract those papers
Options:
    --limit N      first N papers only (for a trial)
    --workers N    papers in parallel (default 1)
    --redo-partial re-extract papers whose reply was cut off and salvaged

Model: PACT_EXTRACT_MODEL (default anthropic/claude-sonnet-5). One model: v7
does not ask for two here, and step 8's human check is the safeguard.
Resumable. Spend is checked against PACT_BUDGET_USD before every batch.
"""
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, PROMPTS, TruncatedResponse, check_budget, need,
                    openrouter_chat, parse_json_reply, provenance,
                    quote_check, read_csv, salvage_json_list, write_csv,
                    write_json)

MODEL = os.environ.get("PACT_EXTRACT_MODEL", "anthropic/claude-sonnet-5")
PROMPT_FILE = os.path.join(PROMPTS, "extract_prompt_v7.txt")
SET_FILE = os.path.join(DATA, "06_extraction_set.csv")
SAMPLE = os.path.join(DATA, "11_sample_500.csv")
FTDIR = os.path.join(DATA, "fulltext")
ROWS_OUT = os.path.join(DATA, "07_extraction_rows.csv")
PAPERS_OUT = os.path.join(DATA, "07_extraction_papers.csv")

FULLTEXT_MAX_CHARS = 60000        # ~15k tokens; long papers are cut, and flagged
EST_COST = {"abstract": 0.02, "fulltext": 0.08}   # USD per paper, for the guard
BATCH = 10                        # papers between budget checks

VAGUE = {"clinical reasoning", "decision making", "decision-making",
         "clinical decision making", "clinical decision-making",
         "clinical judgment", "clinical judgement", "judgment", "judgement",
         "diagnosis", "communication", "cognition", "reasoning", "thinking"}

ROW_FIELDS = ["row_id", "pmid", "source", "task_name", "definition", "quote",
              "quote_verified", "quote_check", "kind", "failure_modes", "clinical_situation",
              "error_or_frequency", "rejected_vague", "model", "run_utc"]
PAPER_FIELDS = ["pmid", "source", "status", "n_rows", "n_verified",
                "full_text_warranted", "full_text_reason", "text_chars",
                "text_truncated", "cost_usd", "model", "run_utc", "error"]


def strip_references(text):
    """Cut a trailing reference list, if the text has one."""
    m = None
    for m in re.finditer(r"\n\s*(references|bibliography|literature cited)\s*\n", text, re.I):
        pass
    return text[:m.start()] if m and m.start() > len(text) * 0.5 else text


def source_text(pmid, rec, source):
    if source == "abstract":
        return (f"TITLE: {rec['title']}\nJOURNAL: {rec['journal']} ({rec['year']})\n"
                f"ABSTRACT: {rec['abstract']}"), False
    path = os.path.join(FTDIR, f"{pmid}.txt")
    with open(path, encoding="utf-8", errors="ignore") as f:
        body = strip_references(f.read())
    truncated = len(body) > FULLTEXT_MAX_CHARS
    return (f"TITLE: {rec['title']}\nJOURNAL: {rec['journal']} ({rec['year']})\n"
            f"FULL TEXT:\n{body[:FULLTEXT_MAX_CHARS]}"), truncated


def extract_one(pmid, rec, source, prompt, stamp):
    text, truncated = source_text(pmid, rec, source)
    paper = {"pmid": pmid, "source": source, "model": MODEL, "run_utc": stamp,
             "text_chars": len(text), "text_truncated": "yes" if truncated else "no",
             "cost_usd": 0.0, "error": ""}
    rows = []
    partial_note = ""
    try:
        try:
            reply, cost = openrouter_chat(MODEL, prompt, text,
                                          max_tokens=5000 if source == "abstract" else 10000)
            paper["cost_usd"] = cost
            d = parse_json_reply(reply)
        except TruncatedResponse as e:
            # Keep every complete row from the cut-off reply rather than paying
            # again. Save the raw reply so a person can see what happened.
            paper["cost_usd"] = e.cost
            os.makedirs(os.path.join(DATA, "07_truncated"), exist_ok=True)
            with open(os.path.join(DATA, "07_truncated", f"{pmid}-{source}.txt"), "w",
                      encoding="utf-8") as f:
                f.write(e.partial)
            tasks, seen = [], set()
            for t in salvage_json_list(e.partial, "tasks"):
                k = ((t.get("task_name") or "").lower(), (t.get("quote") or "").lower())
                if k not in seen:
                    seen.add(k)
                    tasks.append(t)
            if not tasks:
                raise
            d = {"tasks": tasks, "full_text_warranted": source == "abstract",
                 "full_text_reason": "reply cut off; partial rows kept"}
            partial_note = (f"PARTIAL: reply hit the length limit; {len(tasks)} complete "
                            f"distinct rows kept, raw reply in data/07_truncated/")
        for i, t in enumerate(d.get("tasks") or [], 1):
            name = (t.get("task_name") or "").strip()
            quote = (t.get("quote") or "").strip()
            fm = t.get("failure_modes") or []
            rows.append({
                "row_id": f"{pmid}-{source[0]}{i}", "pmid": pmid, "source": source,
                "task_name": name, "definition": (t.get("definition") or "").strip(),
                "quote": quote,
                "quote_check": quote_check(quote, text),
                "kind": (t.get("kind") or "").strip(),
                "failure_modes": "; ".join(fm) if isinstance(fm, list) else str(fm),
                "clinical_situation": (t.get("clinical_situation") or "").strip(),
                "error_or_frequency": (t.get("error_or_frequency") or "").strip(),
                "rejected_vague": "yes" if name.lower().strip(" .") in VAGUE else "no",
                "model": MODEL, "run_utc": stamp})
            rows[-1]["quote_verified"] = "yes" if rows[-1]["quote_check"] == "verbatim" else "no"
        flagged = bool(d.get("full_text_warranted")) and source == "abstract"
        unverified = any(r["quote_verified"] == "no" for r in rows)
        reason = (d.get("full_text_reason") or "").strip()
        if source == "abstract" and unverified and not flagged:
            flagged, reason = True, "a supporting quote could not be confirmed in the abstract"
        paper["error"] = partial_note
        paper.update({"status": "done", "n_rows": len(rows),
                      "n_verified": sum(r["quote_verified"] == "yes" for r in rows),
                      "full_text_warranted": "yes" if flagged else "no",
                      "full_text_reason": reason})
    except (TruncatedResponse, Exception) as e:
        paper["cost_usd"] = getattr(e, "cost", 0.0)   # truncated replies are still billed
        paper.update({"status": "ERROR", "n_rows": 0, "n_verified": 0,
                      "full_text_warranted": "", "full_text_reason": "",
                      "error": f"{type(e).__name__}: {str(e)[:180]}"})
        rows = []
    return paper, rows


def main():
    fulltext_mode = "--fulltext" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 1
    source = "fulltext" if fulltext_mode else "abstract"

    with open(need(PROMPT_FILE), encoding="utf-8") as f:
        prompt = f.read()
    sample = {r["pmid"]: r for r in read_csv(need(SAMPLE))}
    ext_set = [r["pmid"] for r in read_csv(need(SET_FILE))]
    papers = {(r["pmid"], r["source"]): r for r in read_csv(PAPERS_OUT)} if os.path.exists(PAPERS_OUT) else {}
    rows = read_csv(ROWS_OUT) if os.path.exists(ROWS_OUT) else []

    if fulltext_mode:
        flagged = [p for p in ext_set
                   if papers.get((p, "abstract"), {}).get("full_text_warranted") == "yes"]
        have = [p for p in flagged if os.path.exists(os.path.join(FTDIR, f"{p}.txt"))
                and os.path.getsize(os.path.join(FTDIR, f"{p}.txt")) > 3000]
        print(f"  flagged for full text: {len(flagged)}   full text available: {len(have)}")
        targets = have
    else:
        targets = ext_set
    if limit:
        targets = targets[:limit]
    redo_partial = "--redo-partial" in sys.argv
    todo = [p for p in targets
            if papers.get((p, source), {}).get("status") != "done"
            or (redo_partial and papers[(p, source)].get("error", "").startswith("PARTIAL"))]
    print(f"  {source}: {len(targets)} papers, {len(targets) - len(todo)} already done, {len(todo)} to do")
    print(f"  model: {MODEL}")

    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for start in range(0, len(todo), BATCH):
        chunk = todo[start:start + BATCH]
        check_budget(EST_COST[source] * len(chunk), what=f"{source} extraction batch")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(lambda p: extract_one(p, sample[p], source, prompt, stamp), chunk))
        for paper, new_rows in results:
            papers[(paper["pmid"], source)] = paper
            rows = [r for r in rows if not (r["pmid"] == paper["pmid"] and r["source"] == source)]
            rows.extend(new_rows)
        write_csv(PAPERS_OUT, sorted(papers.values(), key=lambda r: (r["pmid"], r["source"])), PAPER_FIELDS)
        write_csv(ROWS_OUT, sorted(rows, key=lambda r: r["row_id"]), ROW_FIELDS)
        print(f"    {min(start + BATCH, len(todo))}/{len(todo)} papers", flush=True)

    # Report on the whole set as it stands.
    done = [p for p in papers.values() if p["status"] == "done"]
    errs = [p for p in papers.values() if p["status"] == "ERROR"]
    abs_done = [p for p in done if p["source"] == "abstract"]
    ft_done = [p for p in done if p["source"] == "fulltext"]
    ft_pmids = {p["pmid"] for p in ft_done}
    # Rows in force: full-text rows replace a paper's abstract rows.
    in_force = [r for r in rows if r["source"] == "fulltext" or r["pmid"] not in ft_pmids]
    cost = sum(float(p.get("cost_usd") or 0) for p in papers.values())
    print(f"\n  papers extracted: abstract {len(abs_done)}, full text {len(ft_done)}; errors {len(errs)}")
    print(f"  flagged for full text: {sum(p.get('full_text_warranted') == 'yes' for p in abs_done)}")
    print(f"  rows in force: {len(in_force)}  "
          f"(thinking processes {sum(r['kind'] == 'thinking_process' for r in in_force)}, "
          f"clinical activities {sum(r['kind'] == 'clinical_activity' for r in in_force)})")
    qc = {k: sum(r.get("quote_check") == k for r in in_force) for k in ("verbatim", "too_short", "not_found")}
    print(f"  quotes: verbatim {qc['verbatim']}, found but too short {qc['too_short']}, "
          f"NOT in the paper {qc['not_found']}   (of {len(in_force)})")
    print(f"  rejected as too vague: {sum(r['rejected_vague'] == 'yes' for r in in_force)}")
    print(f"  extraction spend recorded by OpenRouter: ${cost:.2f}")
    if errs:
        print("  Re-run the same command to retry errored papers.")

    prov = provenance(os.path.abspath(__file__), extra_files=[PROMPT_FILE])
    prov.update({"model": MODEL, "prompt_file": os.path.basename(PROMPT_FILE),
                 "abstract_papers": len(abs_done), "fulltext_papers": len(ft_done),
                 "errors": len(errs), "rows_in_force": len(in_force),
                 "quotes_verified": sum(r["quote_verified"] == "yes" for r in in_force),
                 "quote_check": {k: sum(r.get("quote_check") == k for r in in_force)
                                 for k in ("verbatim", "too_short", "not_found")},
                 "fulltext_max_chars": FULLTEXT_MAX_CHARS, "cost_usd": round(cost, 4),
                 "limit": limit})
    write_json(os.path.join(DATA, "07_extraction_manifest.json"), prov)


if __name__ == "__main__":
    main()
