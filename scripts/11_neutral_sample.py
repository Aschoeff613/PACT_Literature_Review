"""
STEP 2 - Draw the sample.

Protocol v7, step 2:
  - 250 papers from emergency medicine, 250 from primary care
    (raised to 1,000 + 1,000 by decision 9, docs/DECISIONS_2026-09-22.md)
  - random draw, seed recorded so it can be reproduced
  - numbered in batches of 100

Three things the protocol does not specify, decided here and logged so they are
reportable rather than accidental.

1. Papers matching both settings.
   A paper can match the emergency medicine terms and the primary care terms.
   If both draws could take it, the two samples are not independent and the
   paper could be counted twice. The approved rule is to drop every overlapping
   PMID from both pools before either draw. The overlap size is reported in the
   sample manifest.

2. Records with no abstract.
   About 8% of this corpus has no usable abstract, and step 3 screens on title
   and abstract. Rather than screen blind or silently shrink the sample, the
   draw takes an oversample in seeded order, fetches metadata, drops records
   with no abstract, and keeps the first 250 that survive. Deterministic given
   the seed, and the number dropped is reported. It is not a post-hoc
   exclusion: the rule is fixed before the draw.

3. Ordering of the 500.
   The two settings are interleaved by the seeded shuffle rather than stacked,
   so batches of 100 and blocks of 50 each contain both settings. If they were
   stacked, reviewer blocks in step 4 would each be single-setting and any
   reviewer effect would be indistinguishable from a setting effect.

Usage
    python3 scripts/11_neutral_sample.py
    python3 scripts/11_neutral_sample.py --dry-run    # draw PMIDs, skip metadata
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, efetch_records, need, provenance, read_csv,
                    require_email, write_csv, write_json)

# --- fixed before drawing. Do not change once step 3 has started. ----------
SEED = 20260828
N_PER_SETTING = 1000      # 250 in v7; raised 2026-09-22 (decision 9) so step 4 can
                          # fill 75 AI-kept papers per setting at a ~10% include rate
OVERSAMPLE = 1.30          # 1,300 drawn per setting to survive the abstract filter
OVERLAP_RULE = "drop"      # approved 2026-08-28; do not change without amendment
MIN_ABSTRACT_CHARS = 100
DECISION_ID = "2026-09-22-search-tightening"
# ---------------------------------------------------------------------------

SETTING_FILES = {
    "emergency_medicine": "01_pmids_emergency_medicine.csv",
    "primary_care": "01_pmids_primary_care.csv",
}


def main():
    require_email()
    dry = "--dry-run" in sys.argv
    prov = provenance(os.path.abspath(__file__))
    rng = random.Random(SEED)

    search_manifest_path = need(os.path.join(DATA, "01_run_manifest.json"))
    with open(search_manifest_path, encoding="utf-8") as f:
        search_manifest = json.load(f)
    if (search_manifest.get("decision_id") != DECISION_ID
            or search_manifest.get("counts_only")):
        sys.exit(
            "ERROR: the saved PubMed pools predate the current method "
            "amendment (" + DECISION_ID + ") (or came from a counts-only run).\n"
            "  Re-run: python3 scripts/01_search.py --per-term"
        )

    pools = {}
    for setting, fname in SETTING_FILES.items():
        rows = read_csv(need(os.path.join(DATA, fname)))
        pools[setting] = {r["pmid"] for r in rows}
        print(f"  {setting:20s} pool {len(pools[setting]):,}")

    settings = list(pools)
    a, b = settings
    overlap = sorted(pools[a] & pools[b])
    print(f"\n  papers matching both settings: {len(overlap):,} "
          f"({100 * len(overlap) / max(len(pools[a] | pools[b]), 1):.1f}% of the union)")

    if OVERLAP_RULE == "drop":
        for s in settings:
            pools[s] -= set(overlap)
        assigned = {}
        print("  rule: dropped from both pools")
    else:
        assigned = {p: (a if rng.random() < 0.5 else b) for p in overlap}
        for p, keep in assigned.items():
            other = b if keep == a else a
            pools[other].discard(p)
        n_a = sum(1 for v in assigned.values() if v == a)
        print(f"  rule: assigned by seeded coin flip ({n_a} to {a}, "
              f"{len(overlap) - n_a} to {b})")

    for s in settings:
        if len(pools[s]) < N_PER_SETTING:
            sys.exit(f"ERROR: {s} pool has only {len(pools[s])} papers, "
                     f"need {N_PER_SETTING}. Widen the search first.")

    # Seeded draw. Shuffle the whole sorted pool, then take from the front.
    # Taking from the front of a shuffled list means the oversample is a strict
    # prefix of the draw, so dropping no-abstract records does not disturb the
    # randomness of what remains.
    draws, order = {}, {}
    take = int(N_PER_SETTING * OVERSAMPLE)
    for s in settings:
        ordered = sorted(pools[s])
        rng.shuffle(ordered)
        order[s] = ordered
        draws[s] = ordered[:take]
        print(f"  {s:20s} drew {len(draws[s])} (oversample of {N_PER_SETTING})")

    if dry:
        write_csv(os.path.join(DATA, "11_draw_pmids.csv"),
                  [{"pmid": p, "setting": s, "rank": i + 1}
                   for s in settings for i, p in enumerate(draws[s])],
                  ["pmid", "setting", "rank"])
        print("\n  dry run: PMIDs drawn, no metadata fetched.")
        return

    print("\n  fetching metadata for the drawn papers")
    kept, dropped = {}, {}
    for s in settings:
        recs = {r["pmid"]: r for r in efetch_records(draws[s])}
        keep, drop = [], []
        for p in draws[s]:                      # seeded order preserved
            r = recs.get(p)
            if r is None:
                drop.append({"pmid": p, "setting": s, "reason": "efetch returned nothing"})
                continue
            if len(r.get("abstract", "")) < MIN_ABSTRACT_CHARS:
                drop.append({"pmid": p, "setting": s, "reason": "no usable abstract"})
                continue
            r["source_setting"] = s
            keep.append(r)
            if len(keep) == N_PER_SETTING:
                break
        kept[s] = keep
        dropped[s] = drop
        print(f"  {s:20s} kept {len(keep)}, skipped {len(drop)}")
        if len(keep) < N_PER_SETTING:
            print(f"    WARNING: only {len(keep)} of {N_PER_SETTING}. "
                  f"Raise OVERSAMPLE and re-run.")

    combined = [r for s in settings for r in kept[s]]
    rng.shuffle(combined)                        # interleave the two settings

    for i, r in enumerate(combined, 1):
        r["record_no"] = i
        r["batch_100"] = (i - 1) // 100 + 1      # protocol step 2
        r["block_50"] = (i - 1) // 50 + 1        # step 4 reviewer blocks, step 9 batches

    write_csv(os.path.join(DATA, "11_sample_500.csv"), combined,
              ["record_no", "batch_100", "block_50", "pmid", "source_setting",
               "year", "journal", "title", "abstract", "doi", "pmc", "authors",
               "pub_types"])
    write_csv(os.path.join(DATA, "11_sample_skipped.csv"),
              [d for s in settings for d in dropped[s]],
              ["pmid", "setting", "reason"])

    prov.update({
        "decision_id": DECISION_ID,
        "seed": SEED,
        "n_per_setting": N_PER_SETTING,
        "oversample": OVERSAMPLE,
        "overlap_rule": OVERLAP_RULE,
        "min_abstract_chars": MIN_ABSTRACT_CHARS,
        "pool_sizes": {s: len(pools[s]) for s in settings},
        "overlap_n": len(overlap),
        "overlap_assignment": assigned if OVERLAP_RULE == "assign" else None,
        "kept": {s: len(kept[s]) for s in settings},
        "skipped": {s: len(dropped[s]) for s in settings},
        "total": len(combined),
    })
    write_json(os.path.join(DATA, "11_sample_manifest.json"), prov)

    print(f"\n  sample: {len(combined)} papers, "
          f"{max(r['batch_100'] for r in combined)} batches of 100")
    print("  11_sample_manifest.json holds the seed and every draw decision. "
          "Commit it.")
    print("\nDone. Next: python3 scripts/03_screen.py --check")


if __name__ == "__main__":
    main()
