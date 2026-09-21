# PACT targeted literature review

Code and prompts for the Task 1.1.1 literature stream: finding published cognitive
constructs in physician reasoning, to check and extend the candidate task list.

Written for someone who has not run a script before. If you can copy and paste into
a terminal, you can run all of this.

---

## What this actually does

Seven small programs, run in order. Each one reads a spreadsheet, does one job, and
writes a new spreadsheet you can open in Excel. Nothing is hidden and nothing happens
in one giant step, so if something looks wrong you can see exactly where.

| Step | What it does | You get |
|---|---|---|
| 1 | Searches PubMed, downloads every hit | ~11,000 records with titles and abstracts |
| 2 | Removes duplicates, sorts into batches of 100 | your screening list |
| 3 | Two AI models read each title and abstract, say include or exclude | a decision column per model |
| 4 | Picks 300 records for a human to check, and lists the papers to get in full | validation sheet + includes list |
| 5 | Downloads free full text automatically, lists what needs the library | text files + a short manual worklist |
| 6 | Two AI models pull the cognitive constructs out of each paper, with a quote | construct list, quotes auto-checked |
| 7 | Compares the human's 300 against the AI, prints sensitivity | the number that says whether to trust step 3 |

The human work is: screening 300 abstracts (step 4), fetching perhaps 40 PDFs (step 5),
and deciding which construct names mean the same thing (after step 6). That is the job.
Everything else is the computer's.

---

## Before you start: three one-time setup things

### 1. Check you have Python

Open Terminal (on a Mac, press Cmd+Space, type "terminal", hit enter) and paste:

```
python3 --version
```

If it prints a number 3.8 or higher, you are done. If it says "command not found",
install Python from python.org and try again.

**You do not need to install anything else.** These scripts use only what comes with Python.

### 2. Get two API keys

An API key is a password that lets a script talk to an AI model. You pay per use.
The whole project costs about **$12 to $17** if you follow the defaults, or up to
about $65 if you use the most expensive models for everything. Full breakdown in
"What this costs" near the end of this file.

- OpenAI: platform.openai.com -> API keys -> create new
- Anthropic: console.anthropic.com -> API keys -> create new

Both look like a long string starting `sk-`. **Never paste a key into a file you commit
to GitHub.** You will put them in the terminal instead, in the next step.

### 3. Open the project and set your keys

Every time you open a new terminal window, paste these three lines (with your real keys):

```
cd ~/Downloads/pact-lit-review
export PACT_EMAIL="aschoeff@stanford.edu"
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

The email is required: NCBI asks who is using their servers, and will slow you down
without it. Nothing is emailed to you.

---

## Running it, step by step

### Step 1 — search PubMed

```
python3 scripts/01_search.py
```

Takes about 15 minutes. It prints progress as it goes. When it finishes, open
`data/01_all_records.csv` and look at it. You should see titles and abstracts.

Last run (3 August 2026) this returned 885 + 2,549 + 2,885 + 4,892 = 11,206 records.
Your numbers will be slightly higher, because PubMed grows daily. That is expected.
The exact searches are saved to `data/01_search_log.csv` for the paper's appendix.

### Step 2 — remove duplicates

```
python3 scripts/02_dedupe.py
```

Takes seconds. Last run: 439 duplicates removed, leaving 10,767 unique papers, of
which 875 (8%) have no abstract. `data/02_unique_records.csv` is now your screening
list, already sorted so the highest-yield strand comes first.

### Step 3 — AI screening

**Test on 20 records first.** Always. This catches a wrong API key before you spend money:

```
python3 scripts/03_screen.py 20
```

Open `data/03_screening.csv` and read the reasons the models gave. If they look
sensible, run the whole thing:

```
python3 scripts/03_screen.py
```

This takes a few hours and costs money. Leave it running. **If it crashes or you
close the laptop, just run it again** — it remembers what it already did and picks up
where it stopped.

The prompt telling the models what to include is in `prompts/screen_prompt.txt`.
It is plain English. Read it, and change it if you disagree with it. Note it says
*when uncertain, include*: at this stage a false include costs a human ten seconds,
while a false exclude loses a paper permanently.

### Step 4 — build the human validation sample

```
python3 scripts/04_validate_sample.py
```

This is the step that makes the whole method defensible, so do not skip it.

Open `data/04_validation_sample.csv`. It has 300 papers and an empty `human_decision`
column. **Hide the two columns starting with `_ai_` first** so you are not influenced
by what the models said. Then read each abstract and type `include` or `exclude`.
Save the file as CSV when done.

This is about 4 to 6 hours of reading. No PDFs, no library access, just abstracts.
Two people doing the first 100 each and comparing is better than one person doing all
300, if you have two people.

### Step 5 — get the full text

```
python3 scripts/05_fulltext.py
```

Downloads everything that is free and legal, from PubMed Central and from Unpaywall.
On this corpus, 34% of records have PMC full text and another 38% of the rest are
open access elsewhere, so expect roughly 57% to arrive on its own.

What is left goes into `data/05_manual_worklist.csv`, with a free link where one
exists. For anything with no link, open it through the Stanford library, copy the text,
and save it as `data/fulltext/<pmid>.txt`. Expect 35 to 50 of these.

Two shortcuts worth taking before you start clicking:

- If a paper's abstract already names *and* defines a construct, you may not need the
  full text at all. Only chase the full text when the abstract names something without
  defining it.
- Ask a Stanford librarian whether the library has a text-and-data-mining agreement
  with Elsevier or Wiley. If it does, a chunk of the paywalled papers become
  downloadable by script and your manual pile shrinks again.

### Step 6 — extract the constructs

Test on three papers first:

```
python3 scripts/06_extract.py 3
```

Then all of them:

```
python3 scripts/06_extract.py
```

Every construct the models report must come with a quote copied word for word from
the paper. The script then checks that the quote really appears in the text and writes
`yes` or `NO - CHECK THIS` in the `quote_verified` column. **Sort by that column and
read every NO.** That is your fabrication check, and it takes minutes.

### Step 7 — find out whether the AI screen was any good

```
python3 scripts/07_metrics.py
```

Prints sensitivity, specificity and kappa for each model and for the two combined.

**Sensitivity is the number that matters.** It is the fraction of genuinely relevant
papers the AI would have kept. Published values for this exact task range from 0.55
to 0.85, which is why you cannot assume and have to measure. The script tells you
what to do with your result:

- 0.90 or above: use the AI screen, and report the number in the paper
- 0.75 to 0.90: treat "either model says include" as the screen, then have a human
  check the exclusions in one pass
- below 0.75: do not let the AI exclude anything. Use it only to sort records so
  humans read the likely-relevant ones first

That last option is still a large saving, and it is honest. A low number is not a
failed experiment; it is a finding, and reporting it is what makes the rest credible.

---

## After step 7: the part only a human can do

The models will report the same construct under different names across different
literatures. Deciding that "premature closure resistance" and "diagnostic
open-mindedness" are one construct, or two, is the taxonomy. Do it by hand, in
`data/07_canonical_constructs.csv`, keeping the original labels alongside the
canonical one so a reader can check your merges.

Then build the provenance table: for every canonical construct, was it produced by the
models in the earlier elicitation phase, found only in the literature, or both. The
"literature only" column is the interesting one, because it is the set of things three
frontier models did not know to mention.

---

## What goes in the repository

Commit these:

- `README.md`, `protocol.md`, `requirements.txt`
- everything in `scripts/` and `prompts/`
- `data/01_search_log.csv` (the exact searches and dates)
- `data/07_canonical_constructs.csv` (the final construct list)
- your metrics output from step 7, including the sensitivity figure even if it is low
- the synonym table and merge decisions

Do **not** commit: API keys, downloaded full text (copyright), or large intermediate CSVs.
`.gitignore` already handles this.

Publishing the prompts is the most valuable part. Almost nobody does it, and it is
what lets a reader judge the method rather than take it on trust.

---

## When something breaks

| It says | Do this |
|---|---|
| `command not found: python3` | Python is not installed. Install from python.org. |
| `no OPENAI_API_KEY set` | You opened a new terminal. Re-paste the three `export` lines. |
| `HTTP Error 502` from NCBI | NCBI is busy. The script retries by itself. If it stops, just run it again. |
| `HTTP Error 429` | You are going too fast, or out of API credit. Check your billing page. |
| `ERROR: expected file not found` | You skipped a numbered step. Run the earlier one. |
| Step 3 stopped halfway | Run it again. It resumes automatically. |
| A 404 fetching full text | Expected for some records. It goes to the manual worklist. Not a bug. |

One warning from experience: for PMC full text, use NCBI's `efetch`, which these
scripts do. The europePMC `fullTextXML` endpoint returns 404 for many records that
plainly do have full text, which is a confusing afternoon if you trust it.


---

## What this costs

Measured from the real corpus, not estimated. Screening 10,767 records comes to
9.09M input and 0.97M output tokens **per model**; the average record is 845 tokens
of title plus abstract. Extracting from 120 full texts comes to 1.19M input and
0.11M output tokens per model, based on measured full texts of 8,121 and 10,763 tokens.

Prices below are from the OpenAI and Anthropic pricing pages as of 3 August 2026.
They change, so check before you budget.

| What | Models | Standard | Via Batch API |
|---|---|---|---|
| Screening 10,767 records | cheap tier both sides | $16.92 | **$8.46** |
| Screening 10,767 records | mid tier both sides | $25.11 | $12.56 |
| Screening 10,767 records | flagship both sides | $57.68 | $28.84 |
| Extraction, 120 papers | strong tier both sides | $7.18 | **$3.59** |
| Extraction, 120 papers | cheap tier both sides | $3.13 | $1.56 |

**Recommended configuration: about $12 total.** Cheap models to screen, strong models
to extract, everything through the Batch API.

Three things worth knowing:

**Use the Batch API.** Both vendors take 50% off if you submit work as a batch instead
of one call at a time, with results back within hours. This job is not interactive, so
there is no reason not to. It is the single largest saving available and it costs you
nothing but patience. The scripts here call the normal endpoint for simplicity; moving
step 3 to batch is worth doing if the price matters to you.

**Screen cheap, extract well.** Screening is a yes/no judgement on an abstract, which
small models do about as well as large ones. Extraction means reading a paper and
pulling out constructs with exact quotes, where quality shows. Spending flagship money
on screening is where budgets get wasted: it is 80% of the tokens and the easiest task.

**Prompt caching probably will not help much here.** The shared instruction is only
~412 tokens against an average 845-token record, and minimum cacheable sizes may apply,
so most of what you send is the part that changes. Test it if you like, but Batch is the
reliable saving.

Your test run of 20 records costs a fraction of a cent. There is no reason to skip it.

---

## Honest limits of this method

Two models agreeing is weaker evidence than it feels like. They share training data
and failure modes, so their agreement partly measures shared bias rather than
correctness. Report their agreement as a description, not as validation. The
300-record human sample is the validation.

Screening is also not blind: whoever screens has already seen the candidate constructs
from the earlier phase. Say so in the write-up rather than leaving a reader to notice.
