"""
STEP 7 - Work out whether the AI screen can be trusted.

Compares the 300 records a human screened against what the models said, and
prints sensitivity, specificity and agreement. Sensitivity is the number that
matters: it tells you what fraction of the genuinely relevant papers the AI
would have thrown away.

Run it AFTER you have filled in the human_decision column.
    python3 scripts/07_metrics.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_csv, need, DATA

def stats(pairs):
    tp = sum(1 for h,a in pairs if h=="include" and a=="include")
    fn = sum(1 for h,a in pairs if h=="include" and a!="include")
    fp = sum(1 for h,a in pairs if h=="exclude" and a=="include")
    tn = sum(1 for h,a in pairs if h=="exclude" and a!="include")
    sens = tp/(tp+fn) if tp+fn else float('nan')
    spec = tn/(tn+fp) if tn+fp else float('nan')
    acc  = (tp+tn)/len(pairs) if pairs else float('nan')
    po = acc
    pyes = ((tp+fp)/len(pairs))*((tp+fn)/len(pairs))
    pno  = ((tn+fn)/len(pairs))*((tn+fp)/len(pairs))
    pe = pyes+pno
    kappa = (po-pe)/(1-pe) if pe < 1 else float('nan')
    return tp,fp,fn,tn,sens,spec,acc,kappa

if __name__ == "__main__":
    rows = [r for r in read_csv(need(os.path.join(DATA,"04_validation_sample.csv")))
            if (r.get("human_decision") or "").strip().lower() in ("include","exclude")]
    if not rows:
        sys.exit("No human_decision values filled in yet. Screen the sample first.")
    print(f"  human-screened records: {len(rows)}\n")
    for label, col in (("GPT","_ai_gpt"), ("Claude","_ai_claude"),
                       ("Either model says include","BOTH")):
        pairs = []
        for r in rows:
            h = r["human_decision"].strip().lower()
            if col == "BOTH":
                a = "include" if "include" in (r.get("_ai_gpt",""), r.get("_ai_claude","")) else "exclude"
            else:
                a = (r.get(col) or "").strip().lower()
            pairs.append((h,a))
        tp,fp,fn,tn,sens,spec,acc,kappa = stats(pairs)
        print(f"  {label}")
        print(f"    sensitivity {sens:.2f}   (missed {fn} of {tp+fn} papers the human would include)")
        print(f"    specificity {spec:.2f}   accuracy {acc:.2f}   kappa {kappa:.2f}")
        print(f"    tp {tp}  fp {fp}  fn {fn}  tn {tn}\n")
    print("  How to read this:")
    print("    sensitivity >= 0.90  -> use the AI screen as your screen; report the number.")
    print("    sensitivity 0.75-0.90 -> use 'either model says include' as the screen, human-check exclusions in one batch.")
    print("    sensitivity <  0.75  -> do NOT let AI exclude anything. Use it only to rank")
    print("                            records so humans read the likely-relevant ones first.")
