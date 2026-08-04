"""
STEP 8 - Inductively cluster the extracted situations into a candidate task list.

The whole corpus is clustered at once, with no categories assumed in advance.
It works the way open coding / thematic analysis works:

  PASS 1 (open coding). All verified high-risk situations are split into
  arbitrary batches (just to keep each prompt a manageable size - the batch
  boundary carries no meaning). For each batch, the model proposes whatever
  candidate tasks the batch's material actually supports, citing PMIDs. This
  produces many overlapping, redundant provisional tasks - that is expected
  and is not a problem, because:

  PASS 2 (merge). Every provisional task from every batch is handed to the
  model in one shot, which merges near-duplicates and keeps genuinely distinct
  ones, still citing PMIDs back to the batch-level provisional tasks (and
  through them to source papers). The output is an emergent candidate list,
  typically 30-50 before human curation down to the 30-40 target.

Run it with:   python3 scripts/08_cluster.py
"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_csv, write_csv, need, DATA
from importlib import import_module
api = import_module("03_screen")
api.OPENAI_MODEL    = "gpt-5.6-terra"      # clustering is judgement; use the stronger tier
api.ANTHROPIC_MODEL = "claude-sonnet-5"

BATCH_SIZE = 50

OPEN_CODING_PROMPT = """You are open-coding a batch of extracted material for an INDUCTIVE
review, building a taxonomy of high-risk cognitive tasks in adult emergency medicine and
primary care from the literature alone. You have NOT been given, and must not assume, any
pre-existing list of task categories. Propose whatever candidate tasks THIS BATCH of material
actually supports - could be 0, could be 6. Do not aim for a target count.

Each candidate task must:
  - be phrased as a cognitive demand applied to a specific clinical situation
  - be specific enough that you could write a scoreable test case for it
  - cite the PMIDs from THIS BATCH that support it
  - carry the strongest risk evidence available in the batch, quoted

Do NOT propose a task that is only a theory label ("diagnostic reasoning", "clinical
judgment"). Do NOT invent a task the batch does not support. Do NOT try to make this batch's
proposals resemble any external framework - describe only what is in front of you.

Good: "Recognising sepsis when the presentation lacks fever or hypotension"
Good: "Deciding admission versus discharge for an older adult after a fall, with
       incomplete information about home support"
Bad:  "Diagnostic reasoning in the emergency department"
Bad:  "Sepsis"

Return ONLY valid JSON:
{"tasks": [
  {"task": "<demand applied to situation>",
   "cognitive_demand": "<the demand alone>",
   "clinical_situation": "<the situation alone>",
   "setting": "emergency" | "primary care" | "both",
   "why_high_risk": "<the evidence, in one sentence>",
   "risk_evidence_quote": "<figure or finding quoted from the supplied material>",
   "supporting_pmids": ["<pmid>", "..."]}]}
"""

MERGE_PROMPT = """You are merging provisional candidate tasks produced independently from
different batches of literature during an inductive review. Many describe the same
underlying cognitive work in different words; some are genuinely distinct. You are looking
for the true underlying set - do not force a target count, and do not discard a task just
because it only appeared once, if the risk evidence for it is real.

For each surviving task:
  - state it once, in the clearest phrasing available across the provisional versions
  - union the supporting PMIDs of everything you merged into it
  - keep the strongest risk evidence quote among the merged versions
  - note briefly which provisional task-texts you merged (so a human can audit the merge)

Two provisional tasks are the SAME if a clinician would call them the same cognitive work,
even in different words. They are DIFFERENT if one is broader/narrower in a way that would
matter for writing a separate benchmark case for each.

Return ONLY valid JSON:
{"tasks": [
  {"task": "<demand applied to situation>",
   "cognitive_demand": "<the demand alone>",
   "clinical_situation": "<the situation alone>",
   "setting": "emergency" | "primary care" | "both",
   "why_high_risk": "<the evidence, in one sentence>",
   "risk_evidence_quote": "<strongest quote among merged versions>",
   "supporting_pmids": ["<pmid>", "..."],
   "merged_from": ["<provisional task text merged in>", "..."],
   "benchmarkable_as": "<how you would test it: vignette, multi-turn, agentic, multimodal>"}]}
"""

def batches(items, n):
    for i in range(0, len(items), n):
        yield items[i:i+n]

if __name__ == "__main__":
    items = read_csv(need(os.path.join(DATA, "06_constructs_raw.csv")))
    situations = [r for r in items if r.get("kind") == "situation"
                  and r.get("quote_verified") == "yes"]
    demands_by_pmid = {}
    for r in items:
        if r.get("kind") == "demand" and r.get("quote_verified") == "yes":
            demands_by_pmid.setdefault(r["pmid"], []).append(r)
    if not situations:
        sys.exit("No verified high-risk situations in data/06_constructs_raw.csv. Run step 6 first.")
    print(f"  {len(situations)} verified situations across {len(set(r['pmid'] for r in situations))} papers")

    # ---- PASS 1: open coding, arbitrary batches, no categories assumed ----
    provisional, pmids_seen = [], set()
    for bi, batch in enumerate(batches(situations, BATCH_SIZE), 1):
        pmids_in_batch = {r["pmid"] for r in batch}
        pmids_seen |= pmids_in_batch
        blob = "\n".join(
            f"[pmid {r['pmid']}] situation: {r.get('situation','')} :: "
            f"why hard: {(r.get('why_cognitively_hard') or '')[:250]} :: "
            f"risk: {(r.get('risk_evidence') or '')[:200]} :: "
            f"paired demands on this paper: "
            + "; ".join(d.get("label","") for d in demands_by_pmid.get(r["pmid"], [])[:3])
            for r in batch)
        print(f"  batch {bi}: {len(batch)} situations from {len(pmids_in_batch)} papers")
        for model, fn in (("gpt", api.ask_openai), ("claude", api.ask_anthropic)):
            saved = api.PROMPT; api.PROMPT = OPEN_CODING_PROMPT
            try:
                res = fn(f"BATCH {bi}\n\n{blob}")
                for t in res.get("tasks", []):
                    cited = [p for p in (t.get("supporting_pmids") or [])]
                    bad = [p for p in cited if p not in pmids_in_batch]
                    provisional.append({"batch":bi,"model":model,
                        "task":t.get("task",""),
                        "cognitive_demand":t.get("cognitive_demand",""),
                        "clinical_situation":t.get("clinical_situation",""),
                        "setting":t.get("setting",""),
                        "why_high_risk":t.get("why_high_risk",""),
                        "risk_evidence_quote":t.get("risk_evidence_quote",""),
                        "supporting_pmids":"; ".join(cited),
                        "citations_check":"ok" if not bad else f"NOT IN BATCH: {bad}"})
            except Exception as e:
                print(f"    {model} failed on batch {bi}: {e}")
            finally:
                api.PROMPT = saved
            time.sleep(0.4)

    write_csv(os.path.join(DATA,"08a_open_coding.csv"), provisional,
        ["batch","model","task","cognitive_demand","clinical_situation","setting",
         "why_high_risk","risk_evidence_quote","supporting_pmids","citations_check"])
    print(f"\n  {len(provisional)} provisional tasks from open coding across "
          f"{len(set(p['batch'] for p in provisional))} batches")

    # ---- PASS 2: merge across the whole corpus at once ----
    all_pmids = pmids_seen
    blob = "\n".join(
        f"- \"{p['task']}\" (demand: {p['cognitive_demand']} | situation: "
        f"{p['clinical_situation']} | risk: {p['risk_evidence_quote'][:150]} | "
        f"pmids: {p['supporting_pmids']})"
        for p in provisional if p["citations_check"] == "ok")
    out = []
    for model, fn in (("gpt", api.ask_openai), ("claude", api.ask_anthropic)):
        saved = api.PROMPT; api.PROMPT = MERGE_PROMPT
        try:
            res = fn(f"PROVISIONAL TASKS FROM ALL BATCHES:\n\n{blob}")
            for t in res.get("tasks", []):
                cited = [p for p in (t.get("supporting_pmids") or [])]
                bad = [p for p in cited if p not in all_pmids]
                out.append({"model":model,
                    "task":t.get("task",""),
                    "cognitive_demand":t.get("cognitive_demand",""),
                    "clinical_situation":t.get("clinical_situation",""),
                    "setting":t.get("setting",""),
                    "why_high_risk":t.get("why_high_risk",""),
                    "risk_evidence_quote":t.get("risk_evidence_quote",""),
                    "supporting_pmids":"; ".join(cited),
                    "merged_from":" | ".join(t.get("merged_from") or []),
                    "benchmarkable_as":t.get("benchmarkable_as",""),
                    "citations_check":"ok" if not bad else f"NOT IN CORPUS: {bad}",
                    "human_keep":"", "human_merge_with":"", "human_notes":""})
        except Exception as e:
            print(f"    {model} merge failed: {e}")
        finally:
            api.PROMPT = saved

    write_csv(os.path.join(DATA,"08_candidate_tasks.csv"), out,
        ["model","task","cognitive_demand","clinical_situation","setting",
         "why_high_risk","risk_evidence_quote","supporting_pmids","merged_from",
         "benchmarkable_as","citations_check","human_keep","human_merge_with","human_notes"])
    nofig = sum(1 for r in out if not r["risk_evidence_quote"].strip())
    print(f"\n  {len(out)} merged candidate tasks (both models combined)")
    print(f"  {nofig} have no risk evidence quote - those cannot be called high-risk yet")
    print("\n  Now the human step: open data/08_candidate_tasks.csv. GPT and Claude each")
    print("  produced their own merge, so expect overlap between the two. Mark human_keep")
    print("  = yes on the wording you want, use human_merge_with to collapse the two models'")
    print("  versions of the same task, and see how close the result lands to 30-40 before")
    print("  forcing it there.")
