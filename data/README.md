# Generated-data status

**Current (22 September 2026, decision id `2026-09-22-search-tightening`).**
Regenerated after decisions 6–9 in `docs/DECISIONS_2026-09-22.md`.

- Search unions: 15,477 emergency-medicine hits and 45,418 primary-care hits
  (15,470 and 45,412 PMIDs downloaded).
- Setting overlap: 4,841 PMIDs, dropped from both sampling pools.
- Sample: 2,000 papers, 1,000 per setting, seed `20260828`, in
  `11_sample_500.csv` (name kept because later steps read it by that name).
  Contains the earlier 500 exactly. Missing/short abstracts skipped: 36 ED, 75 PC.
- Step 3 screening: 2,000/2,000 screened by Claude Sonnet 5 and GPT-5.4;
  229 kept by either model (ED 143, PC 86). Results in `03_screening.csv`
  (not committed; summary in `03_screen_manifest.json`).
- Step 4: 300-paper validation set built (`04_validation_manifest.json`).
  `04_validation_master.csv` and `04_warmup.csv` hold the AI decisions for
  those papers and are kept out of the public repo until reviews are done.
- `archive/`: the 20-paper screening trial on the superseded 28 August sample.

## Earlier status (superseded)

The `01_*` and `11_*` files were regenerated on 28 August 2026 after the
approved decisions in `docs/DECISIONS_2026-08-28.md` and the PubMed metadata
parser correction. They were the step 3 inputs until 22 September 2026.

- Search unions: 17,290 emergency-medicine hits and 54,558 primary-care hits
  (17,287 and 54,543 PMIDs downloaded, respectively).
- Setting overlap: 5,972 PMIDs, dropped from both sampling pools.
- Final sample: 500 unique papers, 250 per setting, seed `20260828`.
- Missing/short abstracts skipped during the draw: 12 emergency-medicine and
  20 primary-care records.

The step 2 and step 3 scripts enforce this: they refuse to consume upstream
manifests that do not carry `decision_id: 2026-08-28-method-amendment`.

To reproduce them from PubMed:

```sh
export PACT_EMAIL="<stanford address>"
python3 scripts/01_search.py --per-term
# Inspect the step 1 gate and commit the resulting search provenance.
python3 scripts/11_neutral_sample.py
```

Do not update the sample by deleting keyword matches from its CSV: records that
match a removed search term may also match a retained term, and deleting rows
would destroy the balanced random design. Rerun steps 1 and 2 instead.
