# Generated-data status

The `01_*` and `11_*` files were regenerated on 28 August 2026 after the
approved decisions in `docs/DECISIONS_2026-08-28.md` and the PubMed metadata
parser correction. They are the current inputs for step 3.

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
