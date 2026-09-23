"""
STEP 6 - Decide whether the AI screen can be trusted.

Protocol v7, step 6. The number that matters: of the papers a human would
have kept, how many did the AI keep?

Two versions of that number are printed, and the difference matters:

  In the 300 checked. The 300 were deliberately balanced: half AI-kept, half
  AI-dropped. In the full sample the dropped pile is roughly eight times
  bigger. So a raw count on the 300 under-represents the dropped pile, which
  is exactly where missed papers hide, and flatters the AI.

  Estimated for the whole sample. Each checked paper is weighted by how many
  papers of its kind (setting x kept/dropped) it stands for in the full
  sample. This is the figure that answers the step 6 question. The protocol's
  warning still holds: neither figure is a rate for the literature.

Then the team chooses a tier, as the protocol sets out, and the script builds
the list of papers that goes to extraction (step 7):

    python3 scripts/07_metrics.py                          # report only
    python3 scripts/07_metrics.py --decision as_is         # AI kept almost all
    python3 scripts/07_metrics.py --decision missed_some   # AI missed some
    python3 scripts/07_metrics.py --decision missed_a_lot  # AI missed a lot

  as_is         extraction set = everything either model kept, with the 300
                human decisions overriding the AI for those papers.
  missed_some   same set, plus a worklist of every AI-dropped paper not yet
                checked, for a human to read. Their decisions are folded in
                with --extra-human FILE (columns pmid, human_decision).
  missed_a_lot  the AI drops nothing. Worklist of every unchecked paper,
                AI-kept first. Extraction set = human-kept only.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, need, provenance, read_csv, write_csv, write_json

SETTINGS = ("emergency_medicine", "primary_care")


def summarise(rows, weights, ai_col):
    """Human-kept papers, and how many of them the AI kept. Raw and weighted."""
    kept_by_human = [r for r in rows if r["human_final"] == "include"]
    raw_n = len(kept_by_human)
    raw_ai = sum(1 for r in kept_by_human if ai_col(r))
    w = lambda r: weights[(r["source_setting"], r["cell"])]
    w_n = sum(w(r) for r in kept_by_human)
    w_ai = sum(w(r) for r in kept_by_human if ai_col(r))
    dropped_by_human = [r for r in rows if r["human_final"] == "exclude"]
    fp = sum(1 for r in dropped_by_human if ai_col(r))
    return {"human_kept": raw_n, "ai_also_kept": raw_ai,
            "raw_pct": 100 * raw_ai / raw_n if raw_n else float("nan"),
            "weighted_pct": 100 * w_ai / w_n if w_n else float("nan"),
            "est_human_kept_in_sample": w_n, "est_missed_in_sample": w_n - w_ai,
            "ai_kept_human_dropped": fp}


def main():
    ap = argparse.ArgumentParser(description="Step 6: can the AI screen be trusted?")
    ap.add_argument("--input", default=os.path.join(DATA, "05_human_consensus.csv"))
    ap.add_argument("--screening", default=os.path.join(DATA, "03_screening.csv"))
    ap.add_argument("--decision", choices=["as_is", "missed_some", "missed_a_lot"])
    ap.add_argument("--extra-human", help="CSV of further human decisions (pmid, human_decision)")
    args = ap.parse_args()

    rows = read_csv(need(args.input))
    pending = [r for r in rows if r["human_final"] not in ("include", "exclude")]
    if pending:
        sys.exit(f"ERROR: {len(pending)} of {len(rows)} papers have no final human decision. "
                 "Finish step 5 first.")
    screen = read_csv(need(args.screening))

    # How many papers each checked paper stands for.
    pop = {}
    for s in screen:
        cell = (s["source_setting"], "kept" if s["either_include"] == "yes" else "dropped")
        pop[cell] = pop.get(cell, 0) + 1
    checked = {}
    for r in rows:
        checked[(r["source_setting"], r["cell"])] = checked.get((r["source_setting"], r["cell"]), 0) + 1
    weights = {c: pop[c] / checked[c] for c in checked}

    tests = {"either model kept it (the rule in use)": lambda r: r["either_include"] == "yes",
             "model A alone": lambda r: r["a_decision"] == "include",
             "model B alone": lambda r: r["b_decision"] == "include"}

    print(f"  papers with a final human decision: {len(rows)}\n")
    print("  OF THE PAPERS A HUMAN KEPT, HOW MANY DID THE AI KEEP?\n")
    report = {}
    for scope in ("all",) + SETTINGS:
        sub = rows if scope == "all" else [r for r in rows if r["source_setting"] == scope]
        print(f"  {scope.replace('_', ' ')}:")
        for label, fn in tests.items():
            s = summarise(sub, weights, fn)
            report[f"{scope}|{label}"] = s
            print(f"    {label:40s} in the 300: {s['ai_also_kept']:>3}/{s['human_kept']:<3} "
                  f"({s['raw_pct']:5.1f}%)   estimated for whole sample: {s['weighted_pct']:5.1f}%")
        s = report[f"{scope}|either model kept it (the rule in use)"]
        print(f"    -> estimated papers a human would keep that the AI dropped: "
              f"~{s['est_missed_in_sample']:.0f} of ~{s['est_human_kept_in_sample']:.0f}\n")

    both = report["all|either model kept it (the rule in use)"]
    print("  Of the AI-kept papers in the 300, humans dropped "
          f"{both['ai_kept_human_dropped']} (over-inclusion is by design).")
    print("\n  Choose the tier as a team (protocol v7, step 6), then re-run with")
    print("  --decision as_is | missed_some | missed_a_lot")
    print("  The 300 were balanced by design: report these as results of this check,")
    print("  not as rates for the literature.")

    extraction, worklist = None, None
    if args.decision:
        human = {r["pmid"]: r["human_final"] for r in rows}
        if args.extra_human:
            for r in read_csv(need(args.extra_human)):
                d = (r.get("human_decision") or "").strip().lower()
                if d in ("include", "exclude"):
                    human[r["pmid"]] = d
        extraction, worklist = [], []
        for s in screen:
            p, ai_kept = s["pmid"], s["either_include"] == "yes"
            if p in human:
                keep, basis = human[p] == "include", "human"
            elif args.decision == "missed_a_lot":
                keep, basis = False, "unchecked"
            else:
                keep, basis = ai_kept, "ai"
            if keep:
                extraction.append({"pmid": p, "source_setting": s["source_setting"],
                                   "batch_100": s["batch_100"], "basis": basis})
            unchecked = p not in human
            if args.decision == "missed_some" and unchecked and not ai_kept:
                worklist.append({"pmid": p, "title": s["title"], "source_setting": s["source_setting"],
                                 "human_decision": ""})
            if args.decision == "missed_a_lot" and unchecked:
                worklist.append({"pmid": p, "title": s["title"], "source_setting": s["source_setting"],
                                 "ai_kept": "yes" if ai_kept else "no", "human_decision": ""})
        if args.decision == "missed_a_lot":
            worklist.sort(key=lambda r: r["ai_kept"] != "yes")
        write_csv(os.path.join(DATA, "06_extraction_set.csv"), extraction,
                  ["pmid", "source_setting", "batch_100", "basis"])
        if worklist:
            write_csv(os.path.join(DATA, "06_human_check_worklist.csv"), worklist,
                      list(worklist[0].keys()))
            print(f"\n  {len(worklist)} papers need a human decision before extraction is final.")
            print("  Fill human_decision in data/06_human_check_worklist.csv, then re-run with")
            print(f"  --decision {args.decision} --extra-human data/06_human_check_worklist.csv")
        print(f"\n  extraction set: {len(extraction)} papers "
              f"(ED {sum(r['source_setting'] == SETTINGS[0] for r in extraction)}, "
              f"PC {sum(r['source_setting'] == SETTINGS[1] for r in extraction)})")

    prov = provenance(os.path.abspath(__file__))
    prov.update({"decision": args.decision, "weights": {f"{a}/{b}": w for (a, b), w in weights.items()},
                 "report": {k: {kk: (round(vv, 3) if isinstance(vv, float) else vv)
                                for kk, vv in v.items()} for k, v in report.items()},
                 "extraction_set": len(extraction) if extraction is not None else None,
                 "worklist": len(worklist) if worklist is not None else None})
    write_json(os.path.join(DATA, "06_metrics_manifest.json"), prov)


if __name__ == "__main__":
    main()
