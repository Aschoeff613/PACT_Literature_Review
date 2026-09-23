"""
STEP 12 - Human check: do the groups hold together?

Protocol v7, step 12, on the locked list only.

Pull 10 items from each task, the same number regardless of task size (fewer
if a task has fewer). Show each item next to three task names in random
order: its own and two others. The reviewer picks the best fit. Picking the
right one most of the time means the task is a real category; picking it
around a third of the time (chance) means the label isn't describing anything,
and the task is flagged as weak. Separately: does the task name describe what
is in it?

Agreed in advance: results are reported and nothing changes. The script
checks the lock fingerprint and refuses to run if the list has been edited.

    python3 scripts/16_intrusion_check.py build
  -> validation/step12/items.csv       reviewers pick A, B or C per item
  -> validation/step12/name_fit.csv    reviewers answer yes / partly / no per task
  -> data/12_answer_key.csv            NOT for reviewers
    python3 scripts/16_intrusion_check.py score validation/step12/items*.csv -- validation/step12/name_fit*.csv
  -> data/12_group_check_report.csv
"""
import hashlib
import json
import math
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, VALIDATION, need, provenance, read_csv, write_csv,
                    write_json)

SEED = 20260926
ITEMS_PER_TASK = 10
SHEET_DIR = os.path.join(VALIDATION, "step12")
KEY = os.path.join(DATA, "12_answer_key.csv")


def check_lock():
    lock = json.load(open(need(os.path.join(DATA, "11_lock.json")), encoding="utf-8"))
    with open(need(os.path.join(DATA, "11_locked_tasks.csv")), "rb") as f:
        if hashlib.sha256(f.read()).hexdigest() != lock["locked_tasks_sha256"]:
            sys.exit("ERROR: 11_locked_tasks.csv no longer matches its lock fingerprint. "
                     "The list must not change after step 11.")
    return lock


def binom_tail(k, n, p=1 / 3):
    """P(X >= k) for X ~ Binomial(n, p): how likely this many hits by chance."""
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def build():
    check_lock()
    tasks = read_csv(os.path.join(DATA, "11_locked_tasks.csv"))
    if len(tasks) < 3:
        sys.exit("ERROR: fewer than 3 locked tasks; a three-way choice is not possible.")
    rmap = read_csv(os.path.join(DATA, "11_locked_row_task_map.csv"))
    rows = {r["row_id"]: r for r in read_csv(need(os.path.join(DATA, "08_rows_for_grouping.csv")))}
    by_task = defaultdict(list)
    for m in rmap:
        by_task[m["locked_id"]].append(m["row_id"])
    name = {t["locked_id"]: t["name"] for t in tasks}
    rng = random.Random(SEED)
    items, key = [], []
    for t in tasks:
        ids = sorted(by_task[t["locked_id"]])
        rng.shuffle(ids)
        for rid in ids[:ITEMS_PER_TASK]:
            others = rng.sample([x["locked_id"] for x in tasks if x["locked_id"] != t["locked_id"]], 2)
            opts = [t["locked_id"]] + others
            rng.shuffle(opts)
            r = rows[rid]
            items.append({"item": f"{r['task_name']}: {r['definition']} | \"{r['quote'][:250]}\"",
                          "option_A": name[opts[0]], "option_B": name[opts[1]],
                          "option_C": name[opts[2]], "answer": "", "notes": ""})
            key.append({"row_id": rid, "true_task": t["locked_id"],
                        "correct_letter": "ABC"[opts.index(t["locked_id"])],
                        "A": opts[0], "B": opts[1], "C": opts[2]})
    order = list(range(len(items)))
    rng.shuffle(order)
    items = [dict(items[i], item_no=n) for n, i in enumerate(order, 1)]
    key = [dict(key[i], item_no=n) for n, i in enumerate(order, 1)]
    os.makedirs(SHEET_DIR, exist_ok=True)
    write_csv(os.path.join(SHEET_DIR, "items.csv"), items,
              ["item_no", "item", "option_A", "option_B", "option_C", "answer", "notes"])
    write_csv(KEY, key, ["item_no", "row_id", "true_task", "correct_letter", "A", "B", "C"])
    fit = []
    for t in tasks:
        ex = [rows[r]["task_name"] for r in sorted(by_task[t["locked_id"]])[:5]]
        fit.append({"locked_id": t["locked_id"], "task_name": t["name"],
                    "definition": t["definition"], "example_items": " || ".join(ex),
                    "name_fits": "", "notes": ""})
    write_csv(os.path.join(SHEET_DIR, "name_fit.csv"), fit,
              ["locked_id", "task_name", "definition", "example_items", "name_fits", "notes"])
    print(f"  {len(items)} items across {len(tasks)} locked tasks "
          f"(up to {ITEMS_PER_TASK} per task); name-fit sheet with {len(fit)} tasks")
    print("  Give reviewers validation/step12/. Keep data/12_answer_key.csv away from them.")


def score(item_paths, fit_paths):
    lock = check_lock()
    tasks = {t["locked_id"]: t for t in read_csv(os.path.join(DATA, "11_locked_tasks.csv"))}
    key = {k["item_no"]: k for k in read_csv(need(KEY))}
    hits, tries = defaultdict(int), defaultdict(int)
    for p in item_paths:
        for a in read_csv(need(p)):
            ans = (a.get("answer") or "").strip().upper()[:1]
            if ans not in ("A", "B", "C"):
                continue
            k = key[a["item_no"]]
            tries[k["true_task"]] += 1
            hits[k["true_task"]] += ans == k["correct_letter"]
    fits = defaultdict(list)
    for p in fit_paths:
        for a in read_csv(need(p)):
            v = (a.get("name_fits") or "").strip().lower()
            if v in ("yes", "partly", "no"):
                fits[a["locked_id"]].append(v)
    report = []
    for tid, t in sorted(tasks.items()):
        n, h = tries[tid], hits[tid]
        pval = binom_tail(h, n) if n else float("nan")
        report.append({"locked_id": tid, "name": t["name"], "items_answered": n, "correct": h,
                       "hit_rate": f"{h / n:.2f}" if n else "",
                       "p_if_chance": f"{pval:.3f}" if n else "",
                       "flag": ("too few items to judge" if n < 5 else
                                ("WEAK: not distinguishable from chance" if pval > 0.05 else "")),
                       "name_fits": "; ".join(f"{v} {fits[tid].count(v)}"
                                              for v in ("yes", "partly", "no") if fits[tid].count(v))})
    write_csv(os.path.join(DATA, "12_group_check_report.csv"), report,
              ["locked_id", "name", "items_answered", "correct", "hit_rate", "p_if_chance",
               "flag", "name_fits"])
    prov = provenance(os.path.abspath(__file__))
    prov.update({"locked_tasks_sha256": lock["locked_tasks_sha256"],
                 "weak": [r["locked_id"] for r in report if r["flag"].startswith("WEAK")]})
    write_json(os.path.join(DATA, "12_group_check_manifest.json"), prov)
    for r in report:
        print(f"  {r['locked_id']}  {r['correct']:>2}/{r['items_answered']:<2} {r['hit_rate']:>5}  "
              f"{r['flag'][:40]:40s} {r['name'][:50]}")
    print("\n  Reported only. The locked list is unchanged (fingerprint verified).")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "build":
        build()
    elif len(sys.argv) >= 3 and sys.argv[1] == "score":
        args = sys.argv[2:]
        if "--" not in args:
            sys.exit("usage: score ITEMS.csv [...] -- NAME_FIT.csv [...]")
        i = args.index("--")
        score(args[:i], args[i + 1:])
    else:
        sys.exit(__doc__)
