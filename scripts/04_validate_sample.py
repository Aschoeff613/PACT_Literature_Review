"""
STEP 4 - Build the human check of the AI screen.

Protocol v7, step 4: 300 papers, split evenly four ways,

                               ED     Primary care
    At least one model kept     75     75
    Both models dropped         75     75

read by six reviewers in six blocks of 50, two reviewers per block, pairs
rotating so no two reviewers are paired twice. Each reviewer reads 100. All six
first read the same 10 warm-up abstracts, which do not count.

Outputs
    data/04_validation_master.csv     the 300, with block, reviewers and the AI
                                      decisions. NOT for reviewers.
    data/04_warmup.csv                the 10 warm-up papers
    validation/step4/review_R1.html   one page per reviewer, 100 papers each
      ... review_R6.html
    validation/step4/review_warmup.html
    data/04_validation_manifest.json  seed, counts, provenance

Blinding. The reviewer pages carry no AI decision, no cell label and no task
list; the AI decisions live only in the master file and are joined back by
PMID in step 5. (The earlier interface embedded both models' decisions in the
page data, where anyone viewing the page source could read them.)

Balance. Each cell's 75 papers are dealt round-robin across the six blocks, so
every block holds 12 or 13 papers from each cell and exactly 50 in total. A
reviewer pair whose block happened to be mostly obvious rejects would
otherwise look more reliable than it is.

Run:
    python3 scripts/04_validate_sample.py
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, ROOT, need, provenance, read_csv, write_csv,
                    write_json)

# --- fixed before drawing. Do not change once reviewers have started. -------
SEED = 20260922
PER_CELL = 75
WARMUP_PER_CELL = {("emergency_medicine", "kept"): 3,
                   ("emergency_medicine", "dropped"): 2,
                   ("primary_care", "kept"): 3,
                   ("primary_care", "dropped"): 2}
BLOCKS = [(1, "R1", "R2"), (2, "R2", "R3"), (3, "R3", "R4"),
          (4, "R4", "R5"), (5, "R5", "R6"), (6, "R6", "R1")]
BLOCK_SIZE = 50
DECISION_ID = "2026-09-22-search-tightening"
# ---------------------------------------------------------------------------

SAMPLE = os.path.join(DATA, "11_sample_500.csv")
SCREEN = os.path.join(DATA, "03_screening.csv")
SCREEN_MANIFEST = os.path.join(DATA, "03_screen_manifest.json")
TEMPLATE = os.path.join(ROOT, "validation", "Lit_Review_Web_Interface.html")
PAGE_DIR = os.path.join(ROOT, "validation", "step4")
CELLS = [("emergency_medicine", "kept"), ("emergency_medicine", "dropped"),
         ("primary_care", "kept"), ("primary_care", "dropped")]


def build_page(template, records, reviewer, heading, intro, filename):
    """Fill Andrew's reviewer interface with one reviewer's papers."""
    n = len(records)
    page_records = [{"reviewer": reviewer, "val_no": r.get("val_no", ""),
                     "pmid": r["pmid"], "year": r["year"], "journal": r["journal"],
                     "title": r["title"], "abstract": r["abstract"],
                     "source_setting": r["source_setting"],
                     "human_decision": "", "human_notes": ""} for r in records]
    seed_json = json.dumps(page_records, ensure_ascii=False).replace("</", "<\\/")

    swaps = [
        ('<title>PACT validation review — records 1–150</title>',
         f'<title>PACT step 4 review — {heading}</title>'),
        ('Your assigned records: 1&ndash;150. Read the title',
         f'{intro} Read the title'),
        ('Records 1&ndash;150 of the 300-record human validation sample &middot; step 4',
         f'{heading} &middot; step 4'),
        ('<input type="number" id="jumpInput" min="1" max="150">',
         f'<input type="number" id="jumpInput" min="1" max="{n}">'),
        ('<span>/ 300</span>', f'<span>/ {n}</span>'),
        ('All 150 assigned records (1–150) have a decision.',
         f'All {n} papers on this page have a decision.'),
        ('0 / 150 reviewed', f'0 / {n} reviewed'),
        ('Remaining: <b id="statRemaining">150</b>',
         f'Remaining: <b id="statRemaining">{n}</b>'),
        ('''  const COLUMNS = ["pmid","year","journal","title","abstract","source_setting",
                   "human_decision","human_notes","_ai_gpt","_ai_claude"];''',
         '''  const COLUMNS = ["reviewer","val_no","pmid","year","journal","title",
                   "source_setting","human_decision","human_notes"];'''),
        ('''    human_notes: r.human_notes||"",
    _ai_gpt: r._ai_gpt||"", _ai_claude: r._ai_claude||""
  }));''',
         '''    human_notes: r.human_notes||"",
    reviewer: r.reviewer||"", val_no: r.val_no||""
  }));'''),
        ('const ORIGINAL_TOTAL = 300;', f'const ORIGINAL_TOTAL = {n};'),
        ("download('11_validation_sample_reviewed_001-150.csv', toCSV(records));",
         f"download('{filename}', toCSV(records));"),
    ]
    page = template
    for old, new in swaps:
        if page.count(old) != 1:
            sys.exit(f"ERROR: reviewer template changed; cannot find:\n  {old[:80]}")
        page = page.replace(old, new)

    start = page.index('<script id="seed-data" type="application/json">')
    start += len('<script id="seed-data" type="application/json">')
    end = page.index("</script>", start)
    page = page[:start] + seed_json + page[end:]
    if "_ai_" in seed_json:
        sys.exit("ERROR: AI decisions leaked into a reviewer page.")
    return page


def main():
    with open(need(SCREEN_MANIFEST), encoding="utf-8") as f:
        sm = json.load(f)
    if sm.get("decision_id") != DECISION_ID:
        sys.exit(f"ERROR: screening manifest is not from decision {DECISION_ID}.")

    sample = {r["pmid"]: r for r in read_csv(need(SAMPLE))}
    screen = read_csv(need(SCREEN))
    bad = [r["pmid"] for r in screen
           if r["a_decision"] not in ("include", "exclude")
           or r["b_decision"] not in ("include", "exclude")]
    missing = set(sample) - {r["pmid"] for r in screen}
    if bad or missing:
        sys.exit(f"ERROR: screening incomplete ({len(bad)} errored, "
                 f"{len(missing)} unscreened). Finish step 3 first.")

    rng = random.Random(SEED)
    cell_rows = {c: [] for c in CELLS}
    for s in sorted(screen, key=lambda r: r["pmid"]):
        cell = (s["source_setting"], "kept" if s["either_include"] == "yes" else "dropped")
        row = dict(sample[s["pmid"]])
        row.update({"cell": cell[1], "a_decision": s["a_decision"],
                    "b_decision": s["b_decision"], "either_include": s["either_include"]})
        cell_rows[cell].append(row)

    main_by_cell, warmup = {}, []
    for c in CELLS:
        pool = cell_rows[c]
        need_n = PER_CELL + WARMUP_PER_CELL[c]
        if len(pool) < need_n:
            sys.exit(f"ERROR: {c} has {len(pool)} papers, need {need_n}.")
        rng.shuffle(pool)
        main_by_cell[c] = pool[:PER_CELL]
        warmup.extend(pool[PER_CELL:need_n])

    # Deal each cell round-robin over the six blocks. 75 = 6*12 + 3, so three
    # blocks take a 13th paper from each cell; alternating the starting block
    # by cell gives every block exactly 50.
    blocks = {b: [] for b, _, _ in BLOCKS}
    for i, c in enumerate(CELLS):
        offset = (i % 2) * 3
        for k, row in enumerate(main_by_cell[c]):
            blocks[(offset + k) % 6 + 1].append(row)
    master = []
    for b, r1, r2 in BLOCKS:
        rows = blocks[b]
        assert len(rows) == BLOCK_SIZE, (b, len(rows))
        rng.shuffle(rows)
        for row in rows:
            row.update({"block": b, "reviewer_1": r1, "reviewer_2": r2})
            master.append(row)
    for i, row in enumerate(master, 1):
        row["val_no"] = i
    rng.shuffle(warmup)
    for i, row in enumerate(warmup, 1):
        row["val_no"] = f"W{i}"

    write_csv(os.path.join(DATA, "04_validation_master.csv"), master,
              ["val_no", "block", "reviewer_1", "reviewer_2", "pmid",
               "source_setting", "cell", "a_decision", "b_decision",
               "either_include", "record_no", "batch_100", "year", "journal",
               "title"])
    write_csv(os.path.join(DATA, "04_warmup.csv"), warmup,
              ["val_no", "pmid", "source_setting", "cell", "a_decision",
               "b_decision", "year", "journal", "title"])

    with open(need(TEMPLATE), encoding="utf-8") as f:
        template = f.read()
    os.makedirs(PAGE_DIR, exist_ok=True)
    reviewers = sorted({r for _, a, b in BLOCKS for r in (a, b)})
    for rv in reviewers:
        mine = [r for r in master if rv in (r["reviewer_1"], r["reviewer_2"])]
        bl = sorted({r["block"] for r in mine})
        page = build_page(
            template, mine, rv,
            heading=f"Reviewer {rv} &middot; {len(mine)} papers (blocks {bl[0]} and {bl[1]})",
            intro=f"You are reviewer {rv}. This page holds your {len(mine)} papers.",
            filename=f"step4_review_{rv}.csv")
        with open(os.path.join(PAGE_DIR, f"review_{rv}.html"), "w", encoding="utf-8") as f:
            f.write(page)
    page = build_page(
        template, warmup, "WARMUP",
        heading="Warm-up &middot; 10 papers, read by all six reviewers, not counted",
        intro="Warm-up: everyone reads these same 10 papers, then discusses them. They do not count.",
        filename="step4_warmup.csv")
    with open(os.path.join(PAGE_DIR, "review_warmup.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print(f"  wrote {len(reviewers)} reviewer pages + warm-up -> "
          f"{os.path.relpath(PAGE_DIR, ROOT)}/")

    prov = provenance(os.path.abspath(__file__), extra_files=[TEMPLATE])
    prov.update({
        "decision_id": DECISION_ID, "seed": SEED, "per_cell": PER_CELL,
        "warmup_per_cell": {f"{a}/{b}": n for (a, b), n in WARMUP_PER_CELL.items()},
        "blocks": [{"block": b, "reviewers": [r1, r2]} for b, r1, r2 in BLOCKS],
        "cell_pool_sizes": {f"{a}/{b}": len(cell_rows[(a, b)]) for a, b in CELLS},
        "screening_manifest_git": sm.get("git_version"),
        "total": len(master), "warmup": len(warmup),
    })
    write_json(os.path.join(DATA, "04_validation_manifest.json"), prov)

    print("\n  per block (kept/dropped by setting):")
    for b, r1, r2 in BLOCKS:
        rows = [r for r in master if r["block"] == b]
        cnt = {c: sum(1 for r in rows if (r["source_setting"], r["cell"]) == c) for c in CELLS}
        print(f"    block {b} ({r1},{r2}): ED kept {cnt[CELLS[0]]}, ED dropped {cnt[CELLS[1]]}, "
              f"PC kept {cnt[CELLS[2]]}, PC dropped {cnt[CELLS[3]]}")
    print("\nDone. Send each reviewer their page. They export a CSV when finished.")
    print("Then: python3 scripts/12_merge_human_reviews.py <the six CSVs>")


if __name__ == "__main__":
    main()
