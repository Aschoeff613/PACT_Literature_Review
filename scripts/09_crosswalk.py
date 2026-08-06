"""
STEP 9 - Cross-match the literature task list against your expert task list.

Inputs:
  data/08_candidate_tasks.csv   the kept rows from step 8 (human_keep = yes)
  data/09_expert_tasks.csv      your expert list. Two columns: expert_id, expert_task
                                (this is where the Stanford 37 and the Erasmus
                                processes go; make the file yourself in Excel)

Output:
  data/09_crosswalk.csv         one row per literature task, with the expert task it
                                matches and a convergence code
  data/09_gaps.csv              expert tasks with no literature support, and
                                literature tasks with no expert counterpart

The convergence codes are the same ones the Stanford-Erasmus crosswalk used, so this
plugs straight into the methods memo:
  DIRECT   the same task, different wording
  PARTIAL  overlapping, but one is broader
  NOVEL    no counterpart on the expert list

Run it with:   python3 scripts/09_crosswalk.py
"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_csv, write_csv, need, DATA
from importlib import import_module
api = import_module("03_screen")
api.OPENAI_MODEL    = "gpt-5.6-terra"
api.ANTHROPIC_MODEL = "claude-sonnet-5"

PROMPT = """You are matching one task from a literature review against a list of tasks
produced independently by clinical experts, for a taxonomy of high-risk cognitive tasks
in adult emergency medicine and primary care.

Judge on whether a clinician would say the two describe the same cognitive work, not on
whether the wording is similar. Two tasks can use different words for the same work, and
the same words can hide different work.

Codes:
  DIRECT   the same cognitive work, however differently worded
  PARTIAL  real overlap, but one is broader or covers a component the other does not
  NOVEL    no expert task describes this cognitive work

Return ONLY valid JSON:
{"code": "DIRECT" | "PARTIAL" | "NOVEL",
 "matched_expert_ids": ["<expert_id>", "..."],
 "rationale": "<25 words or fewer>",
 "what_is_uncovered": "<if PARTIAL, the part the expert list misses; else empty>"}
"""

if __name__ == "__main__":
    lit = [r for r in read_csv(need(os.path.join(DATA,"08_candidate_tasks.csv")))
           if (r.get("human_keep") or "").strip().lower() in ("y","yes","1")]
    exp = read_csv(need(os.path.join(DATA,"09_expert_tasks.csv")))
    if not lit:
        sys.exit("No rows marked human_keep=yes in 08_candidate_tasks.csv. Do that first.")
    print(f"  {len(lit)} literature tasks vs {len(exp)} expert tasks")
    exp_blob = "\n".join(f"[{e['expert_id']}] {e['expert_task']}" for e in exp)

    rows, matched = [], set()
    for i, t in enumerate(lit, 1):
        row = {"family":t["family"],"literature_task":t["task"],
               "cognitive_demand":t["cognitive_demand"],
               "clinical_situation":t["clinical_situation"],
               "risk_evidence_quote":t["risk_evidence_quote"],
               "supporting_pmids":t["supporting_pmids"]}
        for model, fn in (("gpt", api.ask_openai), ("claude", api.ask_anthropic)):
            saved = api.PROMPT; api.PROMPT = PROMPT
            try:
                r = fn(f"LITERATURE TASK:\n{t['task']}\n\nsituation: {t['clinical_situation']}\n"
                       f"demand: {t['cognitive_demand']}\n\nEXPERT TASK LIST:\n{exp_blob}")
                row[model+"_code"] = r.get("code","")
                row[model+"_match"] = "; ".join(r.get("matched_expert_ids") or [])
                row[model+"_rationale"] = r.get("rationale","")
                row[model+"_uncovered"] = r.get("what_is_uncovered","")
                if r.get("code") in ("DIRECT","PARTIAL"):
                    matched.update(r.get("matched_expert_ids") or [])
            except Exception as e:
                row[model+"_code"] = "ERROR"; row[model+"_rationale"] = str(e)[:120]
            finally:
                api.PROMPT = saved
            time.sleep(0.3)
        row["agree"] = "yes" if row.get("gpt_code") == row.get("claude_code") else "no"
        row["human_final_code"] = ""
        rows.append(row)
        print(f"    [{i}/{len(lit)}] {row.get('gpt_code','?')} / {row.get('claude_code','?')}")

    write_csv(os.path.join(DATA,"09_crosswalk.csv"), rows,
        ["family","literature_task","cognitive_demand","clinical_situation",
         "risk_evidence_quote","supporting_pmids",
         "gpt_code","gpt_match","gpt_rationale","gpt_uncovered",
         "claude_code","claude_match","claude_rationale","claude_uncovered",
         "agree","human_final_code"])

    gaps = []
    for e in exp:
        if e["expert_id"] not in matched:
            gaps.append({"type":"expert task with no literature support",
                         "id":e["expert_id"],"task":e["expert_task"],
                         "note":"expert opinion only; no citation or risk evidence found"})
    for r in rows:
        if "NOVEL" in (r.get("gpt_code",""), r.get("claude_code","")):
            gaps.append({"type":"literature task absent from expert list",
                         "id":r["family"],"task":r["literature_task"],
                         "note":r["risk_evidence_quote"][:200]})
    write_csv(os.path.join(DATA,"09_gaps.csv"), gaps, ["type","id","task","note"])

    nov = sum(1 for r in rows if "NOVEL" in (r.get("gpt_code",""), r.get("claude_code","")))
    unsupported = sum(1 for g in gaps if g["type"].startswith("expert"))
    recovered = len(matched)
    print(f"\n  RECOVERY RATE: {recovered}/{len(exp)} expert tasks ({100*recovered/max(len(exp),1):.0f}%)")
    print("  were independently reconstructed by the inductive literature review (DIRECT")
    print("  or PARTIAL match), with no exposure to the expert list before step 8 ran.")
    print("  This is the headline number for the paper: it is evidence the two processes")
    print("  converge, not just an assertion that they should.")
    print(f"\n  literature tasks with no expert counterpart: {nov}")
    print(f"  expert tasks with no literature support:     {unsupported}")
    print("\n  Both numbers are findings, not problems. The first is what the experts")
    print("  missed. The second is which of your tasks still rest on opinion alone,")
    print("  which is exactly what a reviewer will ask about the word 'high-risk'.")
    print("  Take both to the Delphi. The reconciled union is your candidate inventory.")
