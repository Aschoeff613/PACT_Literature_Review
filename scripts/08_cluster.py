"""
STEPS 9 and 10 - Grouping, rounds one and two.

Protocol v7, step 9: the checked thinking-process rows from step 8 go to the
model in batches of 50. For each batch it proposes whatever tasks that batch
supports, citing the rows. Batches can't see each other, so the same task
comes back under different names; that is expected. No target number.

Step 10: all round-one proposals go to the model together. It combines the
duplicates, keeps the genuinely different ones, and logs which proposals went
into each surviving task. That is the candidate list.

Every assignment is kept, so each row traces to a proposal and each proposal
to a task. Rows are shuffled with a fixed seed before batching, so batch
boundaries carry no meaning.

    python3 scripts/08_cluster.py
Outputs
    data/09_round1_proposals.csv   every proposal, its batch and its rows
    data/10_candidate_tasks.csv    the candidate list
    data/10_row_task_map.csv       row -> proposal -> task
    data/10_grouping_manifest.json

Step 13's stability check reuses this with a subset of papers:
    python3 scripts/08_cluster.py --pmids FILE --tag halfA
which writes data/13_halfA_* instead and leaves the main outputs alone.

Model: PACT_GROUP_MODEL (default anthropic/claude-opus-5). Grouping decides
the list, so it gets the strongest model; it is also the cheapest step,
because it reads short rows rather than papers.
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, PROMPTS, check_budget, need, openrouter_chat,
                    parse_json_reply, provenance, read_csv, write_csv,
                    write_json)

MODEL = os.environ.get("PACT_GROUP_MODEL", "anthropic/claude-opus-5")
SEED = 20260924
BATCH_SIZE = 50
P1 = os.path.join(PROMPTS, "group_round1_prompt_v7.txt")
P2 = os.path.join(PROMPTS, "group_round2_prompt_v7.txt")
ROWS = os.path.join(DATA, "08_rows_for_grouping.csv")
EST = {"round1": 0.15, "round2": 0.60}      # USD per call, for the budget guard


def row_line(r):
    return json.dumps({"row_id": r["row_id"], "task_name": r["task_name"],
                       "definition": r["definition"][:300], "quote": r["quote"][:300],
                       "clinical_situation": r["clinical_situation"][:120]},
                      ensure_ascii=False)


def ask(prompt, text, max_tokens, what):
    check_budget(EST[what], what=f"grouping {what} call")
    reply, cost = openrouter_chat(MODEL, prompt, text, max_tokens=max_tokens)
    return parse_json_reply(reply), cost


def group(rows, tag=""):
    """Run both rounds on these rows. Returns (proposals, tasks, row_map, cost)."""
    with open(need(P1), encoding="utf-8") as f:
        p1 = f.read()
    with open(need(P2), encoding="utf-8") as f:
        p2 = f.read()
    rows = sorted(rows, key=lambda r: r["row_id"])
    random.Random(SEED).shuffle(rows)
    by_id = {r["row_id"]: r for r in rows}
    cost = 0.0

    proposals = []
    n_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE
    for b in range(n_batches):
        batch = rows[b * BATCH_SIZE:(b + 1) * BATCH_SIZE]
        ids = {r["row_id"] for r in batch}
        text = f"BATCH {b + 1} of {n_batches}, {len(batch)} rows:\n" + "\n".join(row_line(r) for r in batch)
        d, c = ask(p1, text, 8000, "round1")
        cost += c
        used = set()
        for i, pr in enumerate(d.get("proposals") or [], 1):
            cited = [x for x in pr.get("row_ids") or [] if x in ids and x not in used]
            dropped = [x for x in pr.get("row_ids") or [] if x not in ids or x in used]
            if not cited:
                continue
            used.update(cited)
            proposals.append({"proposal_id": f"{tag}b{b + 1}p{i}", "batch": b + 1,
                              "name": (pr.get("name") or "").strip(),
                              "definition": (pr.get("definition") or "").strip(),
                              "row_ids": cited,
                              "invalid_citations_dropped": len(dropped)})
        print(f"    round 1, batch {b + 1}/{n_batches}: {len(batch)} rows -> "
              f"{sum(p['batch'] == b + 1 for p in proposals)} proposals, "
              f"{len(ids - used)} rows unassigned", flush=True)

    lines = []
    for p in proposals:
        ex = [by_id[r]["quote"][:160] for r in p["row_ids"][:2]]
        lines.append(json.dumps({"proposal_id": p["proposal_id"], "name": p["name"],
                                 "definition": p["definition"], "n_rows": len(p["row_ids"]),
                                 "example_quotes": ex}, ensure_ascii=False))
    d, c = ask(p2, f"{len(proposals)} provisional tasks:\n" + "\n".join(lines), 16000, "round2")
    cost += c
    pids = {p["proposal_id"] for p in proposals}
    assigned, tasks = set(), []
    for i, t in enumerate(d.get("tasks") or [], 1):
        members = [x for x in t.get("proposal_ids") or [] if x in pids and x not in assigned]
        if not members:
            continue
        assigned.update(members)
        tasks.append({"task_id": f"{tag}T{i:02d}", "name": (t.get("name") or "").strip(),
                      "definition": (t.get("definition") or "").strip(),
                      "proposal_ids": members, "origin": "round2"})
    # Protocol: no proposal may be dropped. Any the model left out stand alone.
    for p in proposals:
        if p["proposal_id"] not in assigned:
            tasks.append({"task_id": f"{tag}T{len(tasks) + 1:02d}", "name": p["name"],
                          "definition": p["definition"], "proposal_ids": [p["proposal_id"]],
                          "origin": "unassigned in round 2; kept as its own task"})

    prop_by_id = {p["proposal_id"]: p for p in proposals}
    row_map = []
    for t in tasks:
        rws = [r for pid in t["proposal_ids"] for r in prop_by_id[pid]["row_ids"]]
        t["n_proposals"] = len(t["proposal_ids"])
        t["n_rows"] = len(rws)
        t["pmids"] = sorted({by_id[r]["pmid"] for r in rws})
        t["n_papers"] = len(t["pmids"])
        for pid in t["proposal_ids"]:
            for r in prop_by_id[pid]["row_ids"]:
                row_map.append({"row_id": r, "pmid": by_id[r]["pmid"],
                                "proposal_id": pid, "task_id": t["task_id"]})
    return proposals, tasks, row_map, cost


def write_outputs(proposals, tasks, row_map, proposals_path, tasks_path, map_path):
    write_csv(proposals_path,
              [{**p, "row_ids": "; ".join(p["row_ids"])} for p in proposals],
              ["proposal_id", "batch", "name", "definition", "row_ids",
               "invalid_citations_dropped"])
    write_csv(tasks_path,
              [{**t, "proposal_ids": "; ".join(t["proposal_ids"]), "pmids": "; ".join(t["pmids"])}
               for t in sorted(tasks, key=lambda t: -t["n_papers"])],
              ["task_id", "name", "definition", "n_papers", "n_rows", "n_proposals",
               "proposal_ids", "pmids", "origin"])
    write_csv(map_path, row_map, ["row_id", "pmid", "proposal_id", "task_id"])


def main():
    tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else ""
    rows = read_csv(need(ROWS))
    if "--pmids" in sys.argv:
        keep = {r["pmid"] for r in read_csv(need(sys.argv[sys.argv.index("--pmids") + 1]))}
        rows = [r for r in rows if r["pmid"] in keep]
    if not rows:
        sys.exit("ERROR: no rows to group.")
    print(f"  grouping {len(rows)} rows from {len({r['pmid'] for r in rows})} papers "
          f"in batches of {BATCH_SIZE}; model {MODEL}")
    proposals, tasks, row_map, cost = group(rows, tag=f"{tag}-" if tag else "")
    d = lambda name: os.path.join(DATA, name)
    if tag:
        write_outputs(proposals, tasks, row_map, d(f"13_{tag}_round1_proposals.csv"),
                      d(f"13_{tag}_candidate_tasks.csv"), d(f"13_{tag}_row_task_map.csv"))
    else:
        write_outputs(proposals, tasks, row_map, d("09_round1_proposals.csv"),
                      d("10_candidate_tasks.csv"), d("10_row_task_map.csv"))

    prov = provenance(os.path.abspath(__file__), extra_files=[P1, P2])
    prov.update({"model": MODEL, "seed": SEED, "batch_size": BATCH_SIZE, "tag": tag,
                 "rows": len(rows), "proposals": len(proposals), "tasks": len(tasks),
                 "unassigned_in_round2": sum(t["origin"] != "round2" for t in tasks),
                 "cost_usd": round(cost, 4)})
    write_json(os.path.join(DATA, f"13_{tag}_grouping_manifest.json" if tag
                            else "10_grouping_manifest.json"), prov)
    print(f"\n  round 1: {len(proposals)} proposals; round 2: {len(tasks)} candidate tasks "
          f"({prov['unassigned_in_round2']} left unassigned by the model, kept as their own)")
    print(f"  grouping spend recorded by OpenRouter: ${cost:.2f}")
    for t in sorted(tasks, key=lambda t: -t["n_papers"])[:40]:
        print(f"    {t['task_id']:>8}  {t['n_papers']:>3} papers  {t['name']}")
    if not tag:
        print("\nNext: python3 scripts/15_grouping_check.py build")


if __name__ == "__main__":
    main()
