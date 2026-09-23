"""
STEP 11 - Human check: was the combining right?

Protocol v7, step 11. Round two decides the list, and its mistakes leave no
trace: combining two different things deletes one; failing to combine two of
the same thing inflates the count. About 60 pairs, checked both ways:

  combined     two proposals round two put in the SAME task. Same task, or
               different?                        decision: same / different
  kept_apart   two proposals round two put in DIFFERENT tasks. State the
               boundary between them. If you can't, they should have been
               combined.                         decision: boundary / combine

The kept-apart pairs are the most similar pairs across tasks (by shared words
in name and definition), because a check on obviously different tasks tests
nothing.

Two reviewers read every pair; a tiebreaker named in advance settles
disagreements. Unlike the other checks, this one changes the list: a combined
pair judged "different" splits the second proposal out as its own task; a
kept-apart pair judged "combine" merges the two tasks. Then the list is
locked, and later steps refuse to run on anything else.

    python3 scripts/15_grouping_check.py build
  -> validation/step11/pairs_A.csv, pairs_B.csv
    python3 scripts/15_grouping_check.py apply validation/step11/pairs_A.csv validation/step11/pairs_B.csv
  -> if they disagree anywhere: data/11_tiebreak.csv for the tiebreaker, then re-run
  -> data/11_locked_tasks.csv, data/11_locked_row_task_map.csv, data/11_lock.json
"""
import hashlib
import itertools
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, VALIDATION, need, provenance, read_csv, write_csv,
                    write_json)

SEED = 20260925
N_COMBINED, N_APART = 30, 30
SHEET_DIR = os.path.join(VALIDATION, "step11")
MASTER = os.path.join(DATA, "11_pairs_master.csv")
TIEBREAK = os.path.join(DATA, "11_tiebreak.csv")
LOCK = os.path.join(DATA, "11_lock.json")
STOP = set("a an and the of to in or for with on by as is are be that this their "
           "its from at into when whether which what how clinician clinicians "
           "patient patients task".split())


def words(s):
    return {w for w in re.findall(r"[a-z]+", (s or "").lower()) if w not in STOP and len(w) > 2}


def load():
    props = {p["proposal_id"]: p for p in read_csv(need(os.path.join(DATA, "09_round1_proposals.csv")))}
    tasks = read_csv(need(os.path.join(DATA, "10_candidate_tasks.csv")))
    rows = {r["row_id"]: r for r in read_csv(need(os.path.join(DATA, "08_rows_for_grouping.csv")))}
    return props, tasks, rows


def quotes(p, rows, k=2):
    ids = [x.strip() for x in p["row_ids"].split(";") if x.strip()]
    return " || ".join(rows[i]["quote"][:220] for i in ids[:k] if i in rows)


def build():
    if os.path.exists(LOCK):
        sys.exit("ERROR: the list is already locked (data/11_lock.json). Not rebuilding.")
    props, tasks, rows = load()
    rng = random.Random(SEED)
    task_of = {}
    for t in tasks:
        for pid in t["proposal_ids"].split("; "):
            task_of[pid] = t["task_id"]

    combined = []
    for t in tasks:
        members = t["proposal_ids"].split("; ")
        combined += [(a, b) for a, b in itertools.combinations(members, 2)]
    # Prefer pairs from different round-one batches: those are the real merges.
    rng.shuffle(combined)
    combined.sort(key=lambda ab: props[ab[0]]["batch"] == props[ab[1]]["batch"])
    combined = combined[:N_COMBINED]

    apart, seen = [], set()
    cands = []
    for a, b in itertools.combinations(props, 2):
        if task_of.get(a) == task_of.get(b):
            continue
        wa = words(props[a]["name"] + " " + props[a]["definition"])
        wb = words(props[b]["name"] + " " + props[b]["definition"])
        sim = len(wa & wb) / max(len(wa | wb), 1)
        cands.append((sim, a, b))
    cands.sort(key=lambda x: -x[0])
    for sim, a, b in cands:
        key = tuple(sorted((task_of[a], task_of[b])))
        if key in seen:
            continue
        seen.add(key)
        apart.append((a, b))
        if len(apart) >= N_APART:
            break

    pairs = [("combined", a, b) for a, b in combined] + [("kept_apart", a, b) for a, b in apart]
    rng.shuffle(pairs)
    master, sheet = [], []
    for i, (kind, a, b) in enumerate(pairs, 1):
        pa, pb = props[a], props[b]
        master.append({"pair_no": i, "type": kind, "proposal_a": a, "proposal_b": b,
                       "task_a": task_of[a], "task_b": task_of[b]})
        sheet.append({"pair_no": i, "type": kind,
                      "question": ("Same task or different? (same / different)" if kind == "combined"
                                   else "State the boundary. Can't? Then combine. (boundary / combine)"),
                      "a_name": pa["name"], "a_definition": pa["definition"], "a_quotes": quotes(pa, rows),
                      "b_name": pb["name"], "b_definition": pb["definition"], "b_quotes": quotes(pb, rows),
                      "decision": "", "boundary": "", "notes": ""})
    os.makedirs(SHEET_DIR, exist_ok=True)
    for rv in ("A", "B"):
        write_csv(os.path.join(SHEET_DIR, f"pairs_{rv}.csv"),
                  [{**s, "reviewer": rv} for s in sheet],
                  ["pair_no", "reviewer", "type", "question", "a_name", "a_definition",
                   "a_quotes", "b_name", "b_definition", "b_quotes", "decision",
                   "boundary", "notes"])
    write_csv(MASTER, master, ["pair_no", "type", "proposal_a", "proposal_b", "task_a", "task_b"])
    prov = provenance(os.path.abspath(__file__))
    prov.update({"seed": SEED, "combined_pairs": len(combined), "kept_apart_pairs": len(apart),
                 "tasks": len(tasks), "proposals": len(props)})
    write_json(os.path.join(DATA, "11_build_manifest.json"), prov)
    print(f"  {len(combined)} combined pairs, {len(apart)} kept-apart pairs "
          f"(from {len(tasks)} tasks, {len(props)} proposals)")
    print("  Both reviewers read every pair. Name the tiebreaker before they start.")


def norm(d):
    d = (d or "").strip().lower()
    return {"same": "same", "different": "different", "boundary": "boundary",
            "combine": "combine"}.get(d, "")


def apply(paths, force=False):
    if os.path.exists(LOCK) and not force:
        sys.exit("ERROR: already locked. The list does not change after step 11.")
    props, tasks, rows = load()
    master = read_csv(need(MASTER))
    ans = {}
    for p in paths:
        for a in read_csv(need(p)):
            ans[(a["reviewer"], a["pair_no"])] = a
    missing = [m["pair_no"] for m in master for rv in ("A", "B") if not norm(ans.get((rv, m["pair_no"]), {}).get("decision"))]
    if missing:
        sys.exit(f"ERROR: {len(missing)} decisions missing or unreadable, e.g. pairs {missing[:5]}.")
    prior = {r["pair_no"]: r for r in read_csv(TIEBREAK)} if os.path.exists(TIEBREAK) else {}
    final, disagreements = {}, []
    for m in master:
        a, b = norm(ans[("A", m["pair_no"])]["decision"]), norm(ans[("B", m["pair_no"])]["decision"])
        if a == b:
            final[m["pair_no"]] = a
            continue
        tb = norm(prior.get(m["pair_no"], {}).get("tiebreak_decision"))
        disagreements.append({"pair_no": m["pair_no"], "type": m["type"],
                              "a_name": props[m["proposal_a"]]["name"],
                              "b_name": props[m["proposal_b"]]["name"],
                              "reviewer_A": a, "reviewer_B": b,
                              "tiebreak_decision": tb,
                              "tiebreaker": prior.get(m["pair_no"], {}).get("tiebreaker", "")})
        if tb:
            final[m["pair_no"]] = tb
    write_csv(TIEBREAK, disagreements, ["pair_no", "type", "a_name", "b_name", "reviewer_A",
                                        "reviewer_B", "tiebreak_decision", "tiebreaker"])
    pending = [d for d in disagreements if not d["tiebreak_decision"]]
    agree_pct = 100 * (len(master) - len(disagreements)) / len(master) if master else 0
    print(f"  reviewer agreement: {agree_pct:.0f}% of {len(master)} pairs")
    if pending:
        sys.exit(f"  {len(pending)} disagreements await the tiebreaker in data/11_tiebreak.csv "
                 "(tiebreak_decision). Then re-run.")

    member = {t["task_id"]: t["proposal_ids"].split("; ") for t in tasks}
    info = {t["task_id"]: {"name": t["name"], "definition": t["definition"],
                           "origin": t["origin"]} for t in tasks}
    changes = []
    # Splits first: a proposal judged different leaves its task.
    for m in master:
        if m["type"] == "combined" and final[m["pair_no"]] == "different":
            pid = m["proposal_b"]
            src = next(t for t, ms in member.items() if pid in ms)
            if len(member[src]) > 1:
                member[src].remove(pid)
                new = f"S{len(changes) + 1:02d}"
                member[new] = [pid]
                info[new] = {"name": props[pid]["name"], "definition": props[pid]["definition"],
                             "origin": f"split from {src} at step 11 (pair {m['pair_no']})"}
                changes.append(f"split {pid} out of {src} -> {new}")
    # Then merges: kept-apart pairs judged combinable.
    for m in master:
        if m["type"] == "kept_apart" and final[m["pair_no"]] == "combine":
            ta = next(t for t, ms in member.items() if m["proposal_a"] in ms)
            tb = next(t for t, ms in member.items() if m["proposal_b"] in ms)
            if ta != tb:
                member[ta] += member.pop(tb)
                info[ta]["origin"] += f"; {tb} merged in at step 11 (pair {m['pair_no']})"
                changes.append(f"merged {tb} into {ta}")

    locked, row_map = [], []
    for i, (tid, ms) in enumerate(sorted(member.items(), key=lambda x: x[0]), 1):
        lid = f"L{i:02d}"
        rws = [r.strip() for pid in ms for r in props[pid]["row_ids"].split(";") if r.strip()]
        pm = sorted({rows[r]["pmid"] for r in rws if r in rows})
        locked.append({"locked_id": lid, "name": info[tid]["name"],
                       "definition": info[tid]["definition"], "n_papers": len(pm),
                       "n_rows": len(rws), "proposal_ids": "; ".join(ms),
                       "pmids": "; ".join(pm), "from_candidate": tid, "origin": info[tid]["origin"]})
        row_map += [{"row_id": r, "pmid": rows[r]["pmid"], "locked_id": lid} for r in rws if r in rows]
    tpath = os.path.join(DATA, "11_locked_tasks.csv")
    write_csv(tpath, locked, ["locked_id", "name", "definition", "n_papers", "n_rows",
                              "proposal_ids", "pmids", "from_candidate", "origin"])
    write_csv(os.path.join(DATA, "11_locked_row_task_map.csv"), row_map,
              ["row_id", "pmid", "locked_id"])
    with open(tpath, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    prov = provenance(os.path.abspath(__file__))
    prov.update({"locked_tasks": len(locked), "changes": changes, "agreement_pct": round(agree_pct, 1),
                 "tiebreaks": len(disagreements), "locked_tasks_sha256": digest})
    write_json(LOCK, prov)
    print(f"  changes applied: {len(changes)}")
    for c in changes:
        print(f"    {c}")
    print(f"  LOCKED: {len(locked)} tasks. sha256 {digest[:16]}... recorded in data/11_lock.json")
    print("\nNext: python3 scripts/16_intrusion_check.py build")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "build":
        build()
    elif len(sys.argv) >= 3 and sys.argv[1] == "apply":
        apply([a for a in sys.argv[2:] if a != "--force"], force="--force" in sys.argv)
    else:
        sys.exit(__doc__)
