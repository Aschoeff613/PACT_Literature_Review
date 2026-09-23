"""
STEP 13 - Two summary checks, on the locked list.

Protocol v7, step 13.

Saturation: where new tasks stopped appearing. Papers carry a batch_100
number from step 2 (random order, 20 batches). A locked task is counted as
"found" at the earliest batch holding one of its supporting papers; the
cumulative count against batch number is the saturation curve. A curve that
flattens early says the sample was big enough; one still climbing at the last
batch says it was not.
    python3 scripts/17_summary_checks.py saturation
  -> data/13_saturation.csv, data/13_saturation.svg

Stability: group each half of the papers separately and see whether you get
roughly the same answer. Papers are split into two halves at random (fixed
seed); each half is grouped from scratch with the same two-round procedure
(08_cluster.py); then a model maps each half's tasks onto the locked list
(prompts/stability_map_prompt_v7.txt), saying "none" where nothing matches.
    python3 scripts/17_summary_checks.py stability
  -> data/13_halfA_*, data/13_halfB_*, data/13_stability.csv
Reported: how many locked tasks each half recovers, and how many half tasks
match nothing in the locked list. Nothing is changed.
"""
import importlib.util
import json
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, PROMPTS, check_budget, need, openrouter_chat,
                    parse_json_reply, provenance, read_csv, write_csv,
                    write_json)

SEED = 20260927
MAP_PROMPT = os.path.join(PROMPTS, "stability_map_prompt_v7.txt")


def locked():
    spec = importlib.util.spec_from_file_location(
        "gc", os.path.join(os.path.dirname(os.path.abspath(__file__)), "16_intrusion_check.py"))
    gc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gc)
    lock = gc.check_lock()
    return lock, read_csv(os.path.join(DATA, "11_locked_tasks.csv"))


def saturation():
    lock, tasks = locked()
    batch = {r["pmid"]: int(r["batch_100"]) for r in read_csv(need(os.path.join(DATA, "11_sample_500.csv")))}
    n_batches = max(batch.values())
    first = {}
    for t in tasks:
        b = [batch[p] for p in t["pmids"].split("; ") if p in batch]
        if b:
            first[t["locked_id"]] = min(b)
    grouped_papers = {p for t in tasks for p in t["pmids"].split("; ")}
    rows, cum = [], 0
    for b in range(1, n_batches + 1):
        new = sorted(k for k, v in first.items() if v == b)
        cum += len(new)
        rows.append({"batch_100": b, "new_tasks": len(new), "cumulative_tasks": cum,
                     "papers_in_batch_with_a_task": sum(1 for p in grouped_papers if batch.get(p) == b),
                     "new_task_ids": "; ".join(new)})
    write_csv(os.path.join(DATA, "13_saturation.csv"), rows,
              ["batch_100", "new_tasks", "cumulative_tasks", "papers_in_batch_with_a_task", "new_task_ids"])

    # Plain SVG, no plotting library (the scripts stay standard-library only).
    W, H, L, B, T, R = 640, 360, 56, 44, 20, 20
    ymax = max(cum, 1)
    x = lambda b: L + (W - L - R) * (b - 1) / max(n_batches - 1, 1)
    y = lambda v: H - B - (H - B - T) * v / ymax
    pts = " ".join(f"{x(r['batch_100']):.1f},{y(r['cumulative_tasks']):.1f}" for r in rows)
    ticks_y = sorted({0, ymax // 2, ymax})
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'font-family="Helvetica, Arial, sans-serif" font-size="12">',
           f'<rect width="{W}" height="{H}" fill="white"/>',
           f'<line x1="{L}" y1="{H - B}" x2="{W - R}" y2="{H - B}" stroke="#999"/>',
           f'<line x1="{L}" y1="{T}" x2="{L}" y2="{H - B}" stroke="#999"/>']
    for v in ticks_y:
        svg.append(f'<text x="{L - 8}" y="{y(v) + 4:.1f}" text-anchor="end" fill="#555">{v}</text>')
        svg.append(f'<line x1="{L}" y1="{y(v):.1f}" x2="{W - R}" y2="{y(v):.1f}" stroke="#eee"/>')
    for b in range(1, n_batches + 1, max(1, n_batches // 10)):
        svg.append(f'<text x="{x(b):.1f}" y="{H - B + 16}" text-anchor="middle" fill="#555">{b}</text>')
    svg += [f'<polyline points="{pts}" fill="none" stroke="#2b6cb0" stroke-width="2.5"/>',
            *[f'<circle cx="{x(r["batch_100"]):.1f}" cy="{y(r["cumulative_tasks"]):.1f}" r="3" fill="#2b6cb0"/>'
              for r in rows],
            f'<text x="{(W + L) / 2:.0f}" y="{H - 8}" text-anchor="middle" fill="#333">'
            f'Batch of 100 papers (random order, step 2)</text>',
            f'<text x="16" y="{(H) / 2:.0f}" text-anchor="middle" fill="#333" '
            f'transform="rotate(-90 16 {(H) / 2:.0f})">Locked tasks found so far</text>',
            '</svg>']
    with open(os.path.join(DATA, "13_saturation.svg"), "w", encoding="utf-8") as f:
        f.write("\n".join(svg))
    last_new = max((r["batch_100"] for r in rows if r["new_tasks"]), default=0)
    print(f"  {cum} locked tasks; the last new one first appears in batch {last_new} of {n_batches}")
    for r in rows:
        print(f"    batch {r['batch_100']:>2}: +{r['new_tasks']:<2} total {r['cumulative_tasks']}")
    prov = provenance(os.path.abspath(__file__))
    prov.update({"check": "saturation", "locked_tasks_sha256": lock["locked_tasks_sha256"],
                 "last_batch_with_new_task": last_new, "n_batches": n_batches})
    write_json(os.path.join(DATA, "13_saturation_manifest.json"), prov)


def stability():
    lock, tasks = locked()
    spec = importlib.util.spec_from_file_location(
        "cl", os.path.join(os.path.dirname(os.path.abspath(__file__)), "08_cluster.py"))
    cl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cl)
    rows = read_csv(need(os.path.join(DATA, "08_rows_for_grouping.csv")))
    pmids = sorted({r["pmid"] for r in rows})
    random.Random(SEED).shuffle(pmids)
    halves = {"halfA": set(pmids[:len(pmids) // 2]), "halfB": set(pmids[len(pmids) // 2:])}
    with open(need(MAP_PROMPT), encoding="utf-8") as f:
        map_prompt = f.read()
    ref = "\n".join(json.dumps({"reference_id": t["locked_id"], "name": t["name"],
                                "definition": t["definition"]}, ensure_ascii=False) for t in tasks)
    result, cost = [], 0.0
    for tag, keep in halves.items():
        sub = [r for r in rows if r["pmid"] in keep]
        print(f"  {tag}: grouping {len(sub)} rows from {len(keep)} papers")
        proposals, htasks, row_map, c = cl.group(sub, tag=f"{tag}-")
        cost += c
        d = lambda name: os.path.join(DATA, name)
        cl.write_outputs(proposals, htasks, row_map, d(f"13_{tag}_round1_proposals.csv"),
                         d(f"13_{tag}_candidate_tasks.csv"), d(f"13_{tag}_row_task_map.csv"))
        half = "\n".join(json.dumps({"half_id": t["task_id"], "name": t["name"],
                                     "definition": t["definition"]}, ensure_ascii=False) for t in htasks)
        check_budget(0.3, what=f"{tag} mapping call")
        reply, c = openrouter_chat(cl.MODEL, map_prompt, f"REFERENCE:\n{ref}\n\nHALF:\n{half}", max_tokens=8000)
        cost += c
        valid = {t["locked_id"] for t in tasks}
        m = {x.get("half_id"): (x.get("reference_id") if x.get("reference_id") in valid else "none",
                                x.get("reason", "")) for x in parse_json_reply(reply).get("matches") or []}
        for t in htasks:
            refid, why = m.get(t["task_id"], ("none", "not returned by the model"))
            result.append({"half": tag, "half_task_id": t["task_id"], "half_task_name": t["name"],
                           "n_papers": t["n_papers"], "matches_locked": refid, "reason": why})
    write_csv(os.path.join(DATA, "13_stability.csv"), result,
              ["half", "half_task_id", "half_task_name", "n_papers", "matches_locked", "reason"])
    summary = {}
    for tag in halves:
        mine = [r for r in result if r["half"] == tag]
        hit = {r["matches_locked"] for r in mine} - {"none"}
        summary[tag] = {"half_tasks": len(mine), "locked_recovered": len(hit),
                        "locked_total": len(tasks), "unmatched_half_tasks": sum(r["matches_locked"] == "none" for r in mine)}
        print(f"  {tag}: {len(mine)} tasks; recovers {len(hit)}/{len(tasks)} locked tasks; "
              f"{summary[tag]['unmatched_half_tasks']} match nothing locked")
    both = ({r["matches_locked"] for r in result if r["half"] == "halfA"} &
            {r["matches_locked"] for r in result if r["half"] == "halfB"}) - {"none"}
    print(f"  locked tasks found independently in BOTH halves: {len(both)}/{len(tasks)}")
    print(f"  stability spend recorded by OpenRouter: ${cost:.2f}")
    prov = provenance(os.path.abspath(__file__), extra_files=[MAP_PROMPT])
    prov.update({"check": "stability", "seed": SEED, "locked_tasks_sha256": lock["locked_tasks_sha256"],
                 "summary": summary, "locked_in_both_halves": len(both), "cost_usd": round(cost, 4)})
    write_json(os.path.join(DATA, "13_stability_manifest.json"), prov)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    if what == "saturation":
        saturation()
    elif what == "stability":
        stability()
    else:
        sys.exit(__doc__)
