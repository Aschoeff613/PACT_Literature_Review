#!/usr/bin/env python3
"""Rapidly map included abstracts to the final 17-task PACT taxonomy.

This is the lightweight pathway. It uses adjudicated human decisions for the
300-record validation sample and the inclusive AI rule for the remaining records.
One model maps each retained abstract and flags only papers whose PDF is actually
needed.

Run after scripts/12_merge_human_reviews.py and adjudication:
  python3 scripts/13_rapid_abstract_map.py --dry-run
  python3 scripts/13_rapid_abstract_map.py
"""

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, need, read_csv, write_csv


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TAXONOMY = os.path.join(ROOT, "taxonomy", "pact_17_tasks.json")
DEFAULT_PROMPT = os.path.join(ROOT, "prompts", "rapid_abstract_map_prompt.txt")
VALID_DECISIONS = {"include", "exclude"}


def clean_decision(value):
    value = (value or "").strip().lower()
    return value if value in VALID_DECISIONS else ""


def as_bool(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def norm(text):
    return re.sub(r"\s+", " ", text or "").strip().lower()


def human_final(row):
    adjudicated = clean_decision(row.get("adjudicated_decision"))
    consensus = clean_decision(row.get("consensus_decision"))
    if adjudicated:
        return adjudicated, "human_adjudicated"
    if consensus:
        return consensus, "human_consensus"
    return "", "human_unresolved"


def select_included(records, screening_rows, consensus_rows, allow_unresolved=False):
    screening = {str(r.get("pmid", "")).strip(): r for r in screening_rows}
    human = {str(r.get("pmid", "")).strip(): r for r in consensus_rows}
    included = []
    unresolved = []
    for record in records:
        pmid = str(record.get("pmid", "")).strip()
        if pmid in human:
            decision, source = human_final(human[pmid])
            if not decision:
                unresolved.append(pmid)
                continue
            if decision == "include":
                included.append({**record, "include_source": source})
            continue
        ai = screening.get(pmid, {})
        ai_include = "include" in (
            clean_decision(ai.get("gpt_decision")),
            clean_decision(ai.get("claude_decision")),
        )
        if ai_include:
            included.append({**record, "include_source": "ai_either_model_remaining"})
    if unresolved and not allow_unresolved:
        preview = ", ".join(unresolved[:12])
        more = f" ...and {len(unresolved) - 12} more" if len(unresolved) > 12 else ""
        raise ValueError(
            f"{len(unresolved)} human-reviewed papers still need adjudication: {preview}{more}"
        )
    return included, unresolved


def taxonomy_blob(tasks):
    return "\n".join(
        f"[{t['id']}] {t['task']} — {t['definition']}" for t in tasks
    )


def normalize_mapping(result, record, tasks, provider, model):
    task_by_id = {int(t["id"]): t for t in tasks}
    ids = []
    for value in result.get("cognitive_task_ids") or []:
        try:
            task_id = int(value)
        except (TypeError, ValueError):
            continue
        if task_id in task_by_id and task_id not in ids:
            ids.append(task_id)
    ids = ids[:3]
    quote = (result.get("evidence_quote") or "").strip()
    quote_verified = "yes" if quote and norm(quote) in norm(record.get("abstract", "")) else "no"
    fit = (result.get("fit") or "none").strip().lower()
    if fit not in {"direct", "partial", "none"}:
        fit = "none"
    confidence = (result.get("confidence") or "low").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
    possible_new = as_bool(result.get("possible_new_task"))
    pdf_needed = as_bool(result.get("pdf_needed"))
    reasons = [(result.get("pdf_reason") or "").strip()]
    if not ids:
        pdf_needed = True
        reasons.append("No supported taxonomy task was identified from the abstract")
    if quote_verified == "no":
        pdf_needed = True
        reasons.append("No exact supporting abstract sentence was verified")
    if possible_new:
        pdf_needed = True
        reasons.append("Possible cognitive task outside the current taxonomy")
    pdf_reason = "; ".join(dict.fromkeys(r for r in reasons if r))
    return {
        "review_order": record.get("screen_order", ""),
        "pmid": record.get("pmid", ""),
        "year": record.get("year", ""),
        "journal": record.get("journal", ""),
        "title": record.get("title", ""),
        "abstract": record.get("abstract", ""),
        "source_setting": record.get("source_setting", ""),
        "include_source": record.get("include_source", ""),
        "clinical_task": (result.get("clinical_task") or "").strip(),
        "cognitive_task_ids": "; ".join(str(i) for i in ids),
        "cognitive_tasks": "; ".join(f"{i}. {task_by_id[i]['task']}" for i in ids),
        "fit": fit,
        "evidence_quote": quote,
        "quote_verified": quote_verified,
        "confidence": confidence,
        "possible_new_task": "yes" if possible_new else "no",
        "new_task_note": (result.get("new_task_note") or "").strip(),
        "pdf_needed": "yes" if pdf_needed else "no",
        "pdf_reason": pdf_reason,
        "human_check": "",
        "human_notes": "",
        "mapping_provider": provider,
        "mapping_model": model,
        "mapping_status": "complete",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Map retained abstracts to the final 17-task taxonomy and create a PDF shortlist."
    )
    parser.add_argument("--records", default=os.path.join(DATA, "11_neutral_sample.csv"))
    parser.add_argument("--screening", default=os.path.join(DATA, "11_neutral_screening.csv"))
    parser.add_argument("--consensus", default=os.path.join(DATA, "12_human_consensus.csv"))
    parser.add_argument("--taxonomy", default=DEFAULT_TAXONOMY)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--output", default=os.path.join(DATA, "13_rapid_abstract_map.csv"))
    parser.add_argument("--pdf-output", default=os.path.join(DATA, "13_pdf_shortlist.csv"))
    parser.add_argument("--provider", choices=("openai", "anthropic"), default="openai")
    parser.add_argument("--model", default=None, help="optional provider model override")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--allow-unresolved", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="show selection counts without calling a model")
    args = parser.parse_args()

    records = read_csv(need(args.records))
    screening = read_csv(need(args.screening))
    consensus = read_csv(need(args.consensus))
    with open(need(args.taxonomy), encoding="utf-8") as handle:
        tasks = json.load(handle)
    if len(tasks) != 17 or {int(t["id"]) for t in tasks} != set(range(1, 18)):
        sys.exit("ERROR: taxonomy must contain exactly task IDs 1 through 17.")

    try:
        included, unresolved = select_included(
            records, screening, consensus, allow_unresolved=args.allow_unresolved
        )
    except ValueError as exc:
        sys.exit(f"ERROR: {exc}")
    print(f"  source records: {len(records)}")
    print(f"  human-reviewed records: {len(consensus)}")
    print(f"  retained abstracts to map: {len(included)}")
    if unresolved:
        print(f"  unresolved human disagreements skipped: {len(unresolved)}")
    if args.dry_run:
        print("  dry run only: no API calls made")
        return

    if args.limit:
        included = included[:args.limit]
    required_key = "OPENAI_API_KEY" if args.provider == "openai" else "ANTHROPIC_API_KEY"
    if not os.environ.get(required_key):
        sys.exit(f"ERROR: {required_key} is not set. Use --dry-run to inspect counts without an API call.")
    api = import_module("03_screen")
    api.PROMPT = open(need(args.prompt), encoding="utf-8").read()
    if args.provider == "openai":
        api.OPENAI_MODEL = args.model or "gpt-5.6-terra"
        ask = api.ask_openai
        model = api.OPENAI_MODEL
    else:
        api.ANTHROPIC_MODEL = args.model or "claude-sonnet-5"
        ask = api.ask_anthropic
        model = api.ANTHROPIC_MODEL

    fields = [
        "review_order", "pmid", "year", "journal", "title", "abstract", "source_setting",
        "include_source", "clinical_task", "cognitive_task_ids", "cognitive_tasks", "fit",
        "evidence_quote", "quote_verified", "confidence", "possible_new_task", "new_task_note",
        "pdf_needed", "pdf_reason", "human_check", "human_notes", "mapping_provider",
        "mapping_model", "mapping_status",
    ]
    prior = read_csv(args.output) if os.path.exists(args.output) else []
    mapped = {
        str(r.get("pmid", "")).strip(): r for r in prior
        if (r.get("mapping_status") or "").strip().lower() == "complete"
    }
    pending = [r for r in included if str(r.get("pmid", "")).strip() not in mapped]
    print(f"  already mapped: {len(mapped)}; pending: {len(pending)}")
    tax_text = taxonomy_blob(tasks)

    def map_one(record):
        request = (
            f"TITLE: {record.get('title', '')}\n"
            f"JOURNAL: {record.get('journal', '')} ({record.get('year', '')})\n"
            f"SETTING: {record.get('source_setting', '')}\n"
            f"ABSTRACT: {record.get('abstract', '') or '[no abstract available]'}\n\n"
            f"FINAL PACT TAXONOMY:\n{tax_text}"
        )
        result = ask(request)
        return normalize_mapping(result, record, tasks, args.provider, model)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(map_one, record): record for record in pending}
        for index, future in enumerate(as_completed(futures), 1):
            record = futures[future]
            pmid = str(record.get("pmid", "")).strip()
            try:
                mapped[pmid] = future.result()
            except Exception as exc:
                mapped[pmid] = {
                    **{field: "" for field in fields},
                    "review_order": record.get("screen_order", ""),
                    "pmid": pmid,
                    "year": record.get("year", ""),
                    "journal": record.get("journal", ""),
                    "title": record.get("title", ""),
                    "abstract": record.get("abstract", ""),
                    "source_setting": record.get("source_setting", ""),
                    "include_source": record.get("include_source", ""),
                    "pdf_needed": "yes",
                    "pdf_reason": f"Mapping error: {str(exc)[:160]}",
                    "mapping_provider": args.provider,
                    "mapping_model": model,
                    "mapping_status": "error",
                }
            if index % 10 == 0 or index == len(pending):
                ordered = [mapped[str(r.get("pmid", "")).strip()] for r in included
                           if str(r.get("pmid", "")).strip() in mapped]
                write_csv(args.output, ordered, fields)
                print(f"    {index}/{len(pending)} newly mapped")

    ordered = [mapped[str(r.get("pmid", "")).strip()] for r in included
               if str(r.get("pmid", "")).strip() in mapped]
    write_csv(args.output, ordered, fields)
    pdf_rows = [r for r in ordered if (r.get("pdf_needed") or "").strip().lower() == "yes"]
    write_csv(args.pdf_output, pdf_rows, fields)
    print(f"\n  mapped abstracts: {len(ordered)}")
    print(f"  PDFs flagged for targeted retrieval: {len(pdf_rows)}")
    print("  Next: scan human_check, correct obvious mappings, and retrieve only the flagged PDFs.")


if __name__ == "__main__":
    main()
