# Human validation interface

`Lit_Review_Web_Interface.html` states the **current** v7 screening criterion,
matching `prompts/screen_prompt_v7.txt` — the wording was synced on 28 Aug 2026.

## Do not review in it yet

Its **embedded records are stale**. It carries 150 records from the
pre-amendment sample: only 1 of those 150 is in the current
`data/11_sample_500.csv`, 52 are not retrieved by the amended search at all,
and 12 are in the 5,972-PMID setting overlap that was deliberately dropped.

Regenerate it from the current sample before any reviewer uses it. The
generator is already in this repo:

```sh
python3 scripts/split_reviewer_html.py --help
```

It builds blinded reviewer pages from `templates/pact_reviewer_template.html`.
Point it at the current 500-paper sample, then re-cut the step 4 validation set.

Until that is done, step 4's AI-versus-human comparison would be measuring
papers that are not in the study.
