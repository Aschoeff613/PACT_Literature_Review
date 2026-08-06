#!/usr/bin/env python3
"""Build two blinded 150-record browser reviewers from the validation CSV."""

import argparse
import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "templates/pact_reviewer_template.html"
DEFAULT_VALIDATION = ROOT / "data/11_neutral_validation_sample.csv"
DEFAULT_SCREENING = ROOT / "data/11_neutral_screening.csv"
SEED_PATTERN = re.compile(
    r'(<script id="seed-data" type="application/json">)(.*?)(</script>)', re.S
)

STOP_WORDS = {
    "about", "after", "among", "also", "analyze", "analyzed", "and", "are",
    "assessment", "associated", "based", "been", "before", "between", "both",
    "care", "clinical", "clinician", "clinicians", "conducted", "during", "each",
    "explicit", "explicitly", "from", "have", "having", "into", "medical", "model",
    "paper", "patient", "patients", "physician", "physicians", "primary", "reported",
    "reports", "result", "results", "setting", "study", "than", "that", "their",
    "there", "these", "they", "this", "those", "through", "using", "were", "which",
    "while", "with", "without", "would",
}

TASK_CUE = re.compile(
    r"\b(?:clinical|diagnostic|medical)\s+(?:reasoning|decision(?:[-\s]?making)?|judg(?:e|ment)|assessment|interpretation)\b"
    r"|\b(?:decision(?:[-\s]?making)?|hand ?off|handover|follow[- ]?up|medication reconciliation|risk stratification|triage|disposition|shared decision making)\b"
    r"|\b(?:decid(?:e|es|ed|ing)|interpret(?:s|ed|ing|ation)?|assess(?:es|ed|ing|ment)?|diagnos(?:e|es|ed|ing|is|tic)|"
    r"communicat(?:e|es|ed|ing|ion)|prioriti[sz](?:e|es|ed|ing|ation)|reconcil(?:e|es|ed|ing|iation)|"
    r"recogn(?:ize|ise|ized|ised|izing|ising|ition)|monitor(?:s|ed|ing)?|prescrib(?:e|es|ed|ing)|"
    r"select(?:s|ed|ing|ion)|weigh(?:s|ed|ing)?|refer(?:s|red|ring|ral)?|document(?:s|ed|ing|ation)?)\b",
    re.I,
)

ACTOR_CUE = re.compile(
    r"\b(?:clinician|physician|doctor|provider|prescriber|resident|general practitioner|GP)s?\b",
    re.I,
)

def normalized_tokens(text: str) -> set[str]:
    tokens = set()
    for token in re.findall(r"[a-z][a-z-]{2,}", text.lower()):
        token = token.replace("-", "")
        if token in STOP_WORDS:
            continue
        for prefix, root in (
            ("decision", "decid"), ("deciding", "decid"), ("decide", "decid"),
            ("diagnos", "diagnos"), ("interpret", "interpret"), ("assess", "assess"),
            ("communicat", "communicat"), ("prescrib", "prescrib"), ("monitor", "monitor"),
            ("recogn", "recogn"), ("reconcil", "reconcil"), ("priorit", "priorit"),
            ("handover", "handover"), ("handoff", "handover"),
        ):
            if token.startswith(prefix):
                token = root
                break
        if token.endswith("s") and len(token) > 4:
            token = token[:-1]
        tokens.add(token)
    return tokens


def sentences(text: str) -> list[str]:
    found = []
    start = 0
    for match in re.finditer(r"[.!?](?=\s+[A-Z0-9]|\s*$)", text):
        sentence = text[start : match.end()].strip()
        if sentence:
            found.append(sentence)
        start = match.end()
    tail = text[start:].strip()
    if tail:
        found.append(tail)
    return found


def model_evidence(screening_row: dict) -> str:
    parts = []
    for model in ("gpt", "claude"):
        if (screening_row.get(f"{model}_decision") or "").strip().lower() != "include":
            continue
        for field in ("reason", "demands"):
            value = (screening_row.get(f"{model}_{field}") or "").strip()
            if value:
                parts.append(value)
    return " ".join(parts)


def sentence_score(sentence: str, evidence_tokens: set[str]) -> tuple[int, int, int]:
    tokens = normalized_tokens(sentence)
    overlap = len(tokens & evidence_tokens)
    cue_count = len(TASK_CUE.findall(sentence))
    actor = 1 if ACTOR_CUE.search(sentence) else 0
    score = overlap * 2 + min(cue_count, 3) * 3 + actor * 2
    if re.match(
        r"^(?:we |this (?:study|was)|an? (?:observational|retrospective|prospective)|"
        r"data were|outcome data|measurements included|participants |patients were |"
        r"the (?:study|survey|analysis) |our aim |to (?:evaluate|assess|investigate|explore))",
        sentence,
        re.I,
    ):
        score -= 5
    if re.search(r"\b(?:should|must|need(?:s|ed)? to|recommend(?:s|ed)?|important to)\b", sentence, re.I):
        score += 3
    return score, overlap, cue_count


def task_annotations(record: dict, screening_row: dict) -> tuple[bool, list[str]]:
    evidence = model_evidence(screening_row)
    if not evidence:
        return False, []
    evidence_tokens = normalized_tokens(evidence)

    title_score, title_overlap, title_cues = sentence_score(record.get("title", ""), evidence_tokens)
    title_highlight = title_score >= 7 and title_overlap >= 2 and title_cues >= 1

    candidates = []
    for position, sentence in enumerate(sentences(record.get("abstract", ""))):
        score, overlap, cues = sentence_score(sentence, evidence_tokens)
        if score >= 7 and overlap >= 2 and cues >= 1:
            candidates.append((score, overlap, cues, -position, sentence))
    selected = sorted(candidates, reverse=True)[:1]
    selected_sentences = [item[-1] for item in sorted(selected, key=lambda item: -item[3])]
    return title_highlight, selected_sentences


def annotate_records(records: list[dict], screening_by_pmid: dict[str, dict]) -> list[dict]:
    annotated = []
    for record in records:
        title_highlight, task_evidence = task_annotations(
            record, screening_by_pmid.get(str(record.get("pmid", "")), {})
        )
        annotated.append(
            {
                **record,
                "_ai_gpt": "",
                "_ai_claude": "",
                "_task_title": title_highlight,
                "_task_evidence": task_evidence,
            }
        )
    return annotated


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"Expected exactly one match, found {count}: {old[:80]!r}")
    return text.replace(old, new, 1)


def embedded_records(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    match = SEED_PATTERN.search(text)
    if not match:
        raise ValueError(f"Could not find embedded reviewer data in {path}")
    return json.loads(match.group(2))


def build_version(source: str, records: list[dict], start: int, end: int) -> str:
    subset = records[start - 1 : end]
    total = len(records)
    assigned = len(subset)
    range_label = f"{start:03d}-{end:03d}"

    output = SEED_PATTERN.sub(
        lambda match: (
            match.group(1)
            + json.dumps(subset, ensure_ascii=True, separators=(",", ":"))
            + match.group(3)
        ),
        source,
        count=1,
    )

    output = replace_once(
        output,
        "<title>PACT validation review — 300 records</title>",
        f"<title>PACT validation review — records {start}–{end}</title>",
    )
    output = replace_once(
        output,
        "<div class=\"sub\">300-record human validation sample &middot; step 4 of the literature pipeline</div>",
        f"<div class=\"sub\">Records {start}&ndash;{end} of the 300-record human validation sample &middot; step 4</div>",
    )
    output = replace_once(
        output,
        '<input type="number" id="jumpInput" min="1" max="300">',
        f'<input type="number" id="jumpInput" min="{start}" max="{end}">',
    )
    output = replace_once(output, "<span>/ 300</span>", f"<span>/ {total}</span>")
    output = replace_once(
        output,
        "All 300 records have a decision. Export whenever you're ready — you can still go back",
        f"All {assigned} assigned records ({start}–{end}) have a decision. Export whenever you're ready — you can still go back",
    )
    output = replace_once(
        output,
        '<div class="progress-label" id="progressLabel">0 / 300 reviewed</div>',
        f'<div class="progress-label" id="progressLabel">0 / {assigned} reviewed</div>',
    )
    output = replace_once(
        output,
        '<span><span class="dot rem"></span>Remaining: <b id="statRemaining">300</b></span>',
        f'<span><span class="dot rem"></span>Remaining: <b id="statRemaining">{assigned}</b></span>',
    )
    output = replace_once(
        output,
        "    --focus:#3b6ea5;",
        "    --focus:#3b6ea5; --setting:#3b6ea5; --setting-soft:#dceeff;",
    )
    output = replace_once(
        output,
        "      --focus:#7fa9d6;",
        "      --focus:#7fa9d6; --setting:#7fa9d6; --setting-soft:#17324b;",
    )
    output = replace_once(
        output,
        "  mark.candidate-cue{\n"
        "    color:inherit; background:var(--amber-soft); border-bottom:2px solid var(--amber);\n"
        "    border-radius:2px; padding:0 .08em; box-decoration-break:clone; -webkit-box-decoration-break:clone;\n"
        "  }",
        "  mark.setting-cue, mark.task-cue{\n"
        "    color:inherit; border-radius:2px; padding:0 .08em;\n"
        "    box-decoration-break:clone; -webkit-box-decoration-break:clone;\n"
        "  }\n"
        "  mark.setting-cue{background:var(--setting-soft); border-bottom:2px solid var(--setting);}\n"
        "  mark.task-cue{background:var(--amber-soft); border-bottom:2px solid var(--amber);}\n"
        "  mark.setting-cue.task-cue{\n"
        "    background:linear-gradient(to bottom,var(--setting-soft) 0 52%,var(--amber-soft) 52% 100%);\n"
        "    border-bottom-color:var(--amber);\n"
        "  }\n"
        "  .highlight-legend{\n"
        "    display:flex; flex-direction:column; align-items:flex-start; gap:7px;\n"
        "    color:var(--ink-soft); font-size:12px; line-height:1.35;\n"
        "  }\n"
        "  .highlight-legend .legend-row{display:flex; align-items:center; gap:7px;}\n"
        "  .highlight-legend .legend-note{font-size:11px;}\n"
        "  .intro-screen{\n"
        "    position:fixed; inset:0; z-index:100; overflow:auto; padding:28px 18px;\n"
        "    display:flex; align-items:flex-start; justify-content:center; background:var(--bg);\n"
        "  }\n"
        "  .intro-screen[hidden]{display:none;}\n"
        "  .intro-card{\n"
        "    width:min(900px,100%); margin:auto; background:var(--panel); border:1px solid var(--border);\n"
        "    border-radius:16px; padding:30px; box-shadow:var(--shadow);\n"
        "  }\n"
        "  .intro-card h1{font-size:26px; margin:0 0 7px;}\n"
        "  .intro-card .intro-sub{margin:0 0 22px; color:var(--ink-soft);}\n"
        "  .intro-question{font-size:18px; font-weight:650; line-height:1.4; margin:0 0 15px;}\n"
        "  .intro-grid{display:grid; grid-template-columns:1fr 1fr; gap:12px; margin:0 0 15px;}\n"
        "  .intro-type{padding:15px; border:1px solid var(--border); border-radius:10px; background:var(--bg);}\n"
        "  .intro-type h2{font-size:16px; margin:0 0 6px;}\n"
        "  .intro-type p{font-size:14px; line-height:1.45; margin:0;}\n"
        "  .intro-note{font-size:14px; line-height:1.45; padding:12px 14px; margin:0 0 12px;\n"
        "    border-left:3px solid var(--accent); background:var(--accent-soft); border-radius:0 8px 8px 0;}\n"
        "  .example-block{margin:0 0 12px;}\n"
        "  .example-block h2{font-size:16px; margin:0 0 8px;}\n"
        "  .example-grid{display:grid; grid-template-columns:1fr 1fr; gap:9px;}\n"
        "  .example-card{border:1px solid var(--border); border-radius:9px; padding:11px 12px; background:var(--bg);}\n"
        "  .example-card strong{display:block; font-size:11px; letter-spacing:.04em; margin-bottom:4px;}\n"
        "  .example-card.include{border-left:3px solid var(--accent);}\n"
        "  .example-card.include strong{color:var(--accent);}\n"
        "  .example-card.exclude{border-left:3px solid var(--danger);}\n"
        "  .example-card.exclude strong{color:var(--danger);}\n"
        "  .example-card span{font-size:12.5px; line-height:1.38;}\n"
        "  .example-note{font-size:11px; color:var(--ink-soft); margin:7px 0 0;}\n"
        "  .intro-exclude{font-size:13px; line-height:1.45; color:var(--ink-soft); margin:0 0 18px;}\n"
        "  .intro-start{font:inherit; font-size:16px; font-weight:650; color:#fff; background:var(--accent);\n"
        "    border:0; border-radius:10px; padding:13px 22px; cursor:pointer;}\n"
        "  .intro-start:hover{filter:brightness(1.06);}\n"
        "  @media (max-width:680px){.intro-grid,.example-grid{grid-template-columns:1fr}.intro-card{padding:22px;}}",
    )
    output = replace_once(
        output,
        "<body>\n<div class=\"wrap\">",
        f"<body>\n"
        f"<div class=\"intro-screen\" id=\"introScreen\">\n"
        f"  <div class=\"intro-card\">\n"
        f"    <h1>How to review these abstracts</h1>\n"
        f"    <p class=\"intro-sub\">Your assigned records: {start}&ndash;{end}. Read the title and abstract, then choose Include or Exclude.</p>\n"
        f"    <p class=\"intro-question\">Is clinician reasoning, decision-making, communication, or judgment-dependent work something the paper actually examines?</p>\n"
        f"    <div class=\"intro-grid\">\n"
        f"      <section class=\"intro-type\"><h2>1. Cognitive task</h2><p>The thinking itself: noticing, interpreting, recognizing, weighing uncertainty, prioritizing, deciding, communicating, or reconciling information.</p></section>\n"
        f"      <section class=\"intro-type\"><h2>2. Clinical task requiring judgment</h2><p>The care activity where that thinking occurs: triage, diagnosis, choosing tests or treatment, admission or discharge, handoff, medication review, or follow-up.</p></section>\n"
        f"    </div>\n"
        f"    <p class=\"intro-note\"><strong>Simple rule:</strong> Ask what the paper is studying. A medical decision happening in the background is not enough.</p>\n"
        f"    <section class=\"example-block\">\n"
        f"      <h2>Clear examples</h2>\n"
        f"      <div class=\"example-grid\">\n"
        f"        <div class=\"example-card exclude\"><strong>EXCLUDE</strong><span>Is antibiotic A more effective than antibiotic B?</span></div>\n"
        f"        <div class=\"example-card include\"><strong>INCLUDE</strong><span>Why do clinicians select antibiotic A rather than antibiotic B?</span></div>\n"
        f"        <div class=\"example-card exclude\"><strong>EXCLUDE</strong><span>How often does antibiotic A cause adverse effects?</span></div>\n"
        f"        <div class=\"example-card include\"><strong>INCLUDE</strong><span>Does a decision-support alert change antibiotic selection?</span></div>\n"
        f"      </div>\n"
        f"      <p class=\"example-note\">When genuinely uncertain, include the paper for later review.</p>\n"
        f"    </section>\n"
        f"    <p class=\"intro-exclude\"><strong>Exclude:</strong> pediatric, ICU/inpatient-only, prehospital, nursing-only or specialty-only work; case reports; editorials; or education/theory without real patient care.</p>\n"
        f"    <button class=\"intro-start\" id=\"startReviewBtn\">Proceed to screening &rarr;</button>\n"
        f"  </div>\n"
        f"</div>\n"
        f"<div class=\"wrap\">",
    )
    output = replace_once(
        output,
        "    <div class=\"toolbar\">\n"
        "      <label class=\"filebtn\" title=\"Load a CSV you exported earlier to pick up where you left off\">",
        "    <div class=\"toolbar\">\n"
        "      <button id=\"instructionsBtn\">ⓘ Instructions</button>\n"
        "      <label class=\"filebtn\" title=\"Load a CSV you exported earlier to pick up where you left off\">",
    )
    output = replace_once(
        output,
        "        <div class=\"candidate-evidence\" id=\"candidateEvidence\" hidden>\n"
        "          <strong>Candidate cue</strong>\n"
        "          <span id=\"candidateEvidenceText\"></span>\n"
        "        </div>",
        "",
    )
    output = replace_once(
        output,
        "      <div class=\"panel guide\">\n"
        "        <h3 class=\"guide-title\">Screening guide</h3>\n\n"
        "        <div class=\"guide-question\">\n"
        "          <div class=\"qlabel\">Primary question</div>\n"
        "          <p>Is this paper about a cognitive task during active clinical care?</p>\n"
        "        </div>\n\n"
        "        <div class=\"guide-section gs-include\">\n"
        "          <div class=\"gs-label\">Include</div>\n"
        "          <p class=\"gs-desc\">A cognitive task performed during active clinical care.</p>\n"
        "          <p class=\"gs-caption\">The clinician must:</p>\n"
        "          <div class=\"tag-row\">\n"
        "            <span class=\"tag\">notice</span><span class=\"tag\">interpret</span>\n"
        "            <span class=\"tag\">decide</span><span class=\"tag\">communicate</span>\n"
        "            <span class=\"tag\">prioritise</span><span class=\"tag\">reconcile</span>\n"
        "            <span class=\"tag\">follow up</span>\n"
        "          </div>\n"
        "          <p class=\"gs-desc gs-inline\"><span class=\"gs-caption-inline\">Active clinical care:</span> adult\n"
        "            emergency medicine &middot; adult primary care &middot; admission/discharge decisions\n"
        "            &middot; transitions, handoffs, med review</p>\n"
        "        </div>\n\n"
        "        <div class=\"guide-section gs-exclude\">\n"
        "          <div class=\"gs-label\">Exclude</div>\n"
        "          <p class=\"gs-desc\">No clinician cognitive work during active care — e.g. papers only about\n"
        "            a drug, diagnosis, test, risk score, AI tool, outcome, or quality metric; or education/theory\n"
        "            with no real clinical-care situation.</p>\n"
        "        </div>\n\n"
        "        <div class=\"guide-section gs-scope\">\n"
        "          <div class=\"gs-label\">Out of scope</div>\n"
        "          <p class=\"gs-desc\">Paediatric care &middot; ICU or inpatient care after admission &middot;\n"
        "            prehospital care &middot; nursing-only or specialty-only care &middot; case reports &middot; editorials.</p>\n"
        "        </div>\n"
        "      </div>",
        "      <div class=\"panel\">\n"
        "        <h3>Highlight key</h3>\n"
        "        <div class=\"highlight-legend\" aria-label=\"Highlight legend\">\n"
        "          <div class=\"legend-row\"><mark class=\"setting-cue\">Setting</mark><span>Where the care happens</span></div>\n"
        "          <div class=\"legend-row\"><mark class=\"task-cue\">Task evidence</mark><span>Possible clinician thinking or judgment</span></div>\n"
        "          <div class=\"legend-note\">AI-assisted cues only. Make your own decision from the full abstract.</div>\n"
        "        </div>\n"
        "      </div>\n\n"
        "      <div class=\"panel guide\">\n"
        "        <h3 class=\"guide-title\">What counts?</h3>\n\n"
        "        <div class=\"guide-question\">\n"
        "          <div class=\"qlabel\">Include when</div>\n"
        "          <p>The paper actually examines clinician reasoning, decisions, communication, or judgment-dependent work.</p>\n"
        "        </div>\n\n"
        "        <div class=\"guide-section gs-include\">\n"
        "          <div class=\"gs-label\">1. Cognitive task</div>\n"
        "          <p class=\"gs-desc\">The thinking itself: interpreting, recognizing, weighing uncertainty, prioritizing, deciding, communicating, or reconciling.</p>\n"
        "        </div>\n\n"
        "        <div class=\"guide-section gs-include\">\n"
        "          <div class=\"gs-label\">2. Clinical task requiring judgment</div>\n"
        "          <p class=\"gs-desc\">Where the thinking happens: triage, diagnosis, choosing tests or treatment, admission or discharge, handoff, medication review, or follow-up.</p>\n"
        "        </div>\n\n"
        "        <div class=\"guide-section gs-scope\">\n"
        "          <div class=\"gs-label\">Setting</div>\n"
        "          <p class=\"gs-desc\">Adult emergency department or adult primary care. A clinical activity counts only when the abstract also shows clinician thinking or judgment.</p>\n"
        "        </div>\n\n"
        "        <div class=\"guide-section gs-exclude\">\n"
        "          <div class=\"gs-label\">Exclude</div>\n"
        "          <p class=\"gs-desc\">The paper only asks whether a treatment or test works, reports outcomes or adverse effects, or never examines clinician work.</p>\n"
        "        </div>\n"
        "      </div>",
    )
    output = replace_once(
        output,
        "  const seed = JSON.parse(document.getElementById('seed-data').textContent);",
        f"  const RECORD_OFFSET = {start - 1};\n"
        f"  const ORIGINAL_TOTAL = {total};\n"
        "  const seed = JSON.parse(document.getElementById('seed-data').textContent);",
    )
    output = replace_once(
        output,
        "    abstract: r.abstract, source_setting: r.source_setting,\n"
        "    human_decision: (r.human_decision||\"\").trim(),",
        "    abstract: r.abstract, source_setting: r.source_setting,\n"
        "    _task_title: Boolean(r._task_title), _task_evidence: r._task_evidence||[],\n"
        "    human_decision: (r.human_decision||\"\").trim(),",
    )
    output = replace_once(
        output,
        "  const toastEl = el('toast');\n"
        "  function toast(msg){",
        "  const toastEl = el('toast');\n"
        "  const introScreen = el('introScreen');\n"
        "  el('startReviewBtn').onclick = ()=>{ introScreen.hidden = true; };\n"
        "  el('instructionsBtn').onclick = ()=>{ introScreen.hidden = false; };\n"
        "  function toast(msg){",
    )
    output = replace_once(
        output,
        "  function renderMarkedText(node, text, span){\n"
        "    node.replaceChildren();\n"
        "    if (!span){\n"
        "      node.textContent = text;\n"
        "      return;\n"
        "    }\n"
        "    node.append(document.createTextNode(text.slice(0, span.start)));\n"
        "    const mark = document.createElement('mark');\n"
        "    mark.className = 'candidate-cue';\n"
        "    mark.textContent = text.slice(span.start, span.end);\n"
        "    node.append(mark, document.createTextNode(text.slice(span.end)));\n"
        "  }",
        "  const SETTING_PATTERN = /\\b(?:adults?|emergency department|emergency medicine|EDs?|primary care|primary health care|general practice|general practitioners?|family practice|family physicians?)\\b/gi;\n\n"
        "  function renderAnnotatedText(node, text, taskEvidence){\n"
        "    node.replaceChildren();\n"
        "    const ranges = [];\n"
        "    const settingPattern = new RegExp(SETTING_PATTERN.source, SETTING_PATTERN.flags);\n"
        "    let match;\n"
        "    while ((match = settingPattern.exec(text)) !== null){\n"
        "      ranges.push({start:match.index, end:match.index + match[0].length, type:'setting-cue'});\n"
        "    }\n"
        "    for (const excerpt of (taskEvidence || [])){\n"
        "      const start = text.indexOf(excerpt);\n"
        "      if (start >= 0) ranges.push({start, end:start + excerpt.length, type:'task-cue'});\n"
        "    }\n"
        "    if (!ranges.length){ node.textContent = text; return; }\n"
        "    const boundaries = [...new Set([0, text.length, ...ranges.flatMap(r=>[r.start,r.end])])].sort((a,b)=>a-b);\n"
        "    for (let i=0; i<boundaries.length-1; i++){\n"
        "      const start = boundaries[i], end = boundaries[i+1];\n"
        "      if (end <= start) continue;\n"
        "      const classes = ranges.filter(r=>r.start < end && r.end > start).map(r=>r.type);\n"
        "      const value = text.slice(start,end);\n"
        "      if (!classes.length){ node.append(document.createTextNode(value)); continue; }\n"
        "      const mark = document.createElement('mark');\n"
        "      mark.className = [...new Set(classes)].join(' ');\n"
        "      mark.textContent = value;\n"
        "      node.append(mark);\n"
        "    }\n"
        "  }",
    )
    output = replace_once(
        output,
        "    const models = candidateModels(r);\n"
        "    const titleCue = models.length ? bestCueSpan(r.title, true) : null;\n"
        "    const abstractCue = models.length ? bestCueSpan(r.abstract, false) : null;\n"
        "    const hasSpecificCue = (titleCue && titleCue.score > 0) || (abstractCue && abstractCue.score > 0);\n"
        "    const useTitleCue = models.length && (!hasSpecificCue ||\n"
        "      (titleCue && titleCue.score >= (abstractCue ? abstractCue.score : 0) && titleCue.score > 0));\n"
        "    renderMarkedText(el('fieldTitle'), r.title, useTitleCue ? titleCue : null);\n\n"
        "    const evidence = el('candidateEvidence');\n"
        "    if (models.length){\n"
        "      evidence.hidden = false;\n"
        "      el('candidateEvidenceText').replaceChildren(\n"
        "        document.createTextNode('Flagged by '),\n"
        "        (() => { const span = document.createElement('span'); span.className = 'models'; span.textContent = models.join(' + '); return span; })(),\n"
        "        document.createTextNode(hasSpecificCue\n"
        "          ? '. The highlight is the strongest match to the screening criteria; the original run did not retain an exact evidence span.'\n"
        "          : '. No specific cue could be recovered, so the title is marked for manual review; the original run did not retain an exact evidence span.')\n"
        "      );\n"
        "    } else {\n"
        "      evidence.hidden = true;\n"
        "    }",
        "    // AI outputs locate candidate evidence only; model identity and decisions stay hidden.\n"
        "    renderAnnotatedText(el('fieldTitle'), r.title, r._task_title ? [r.title] : []);",
    )
    output = replace_once(
        output,
        "      renderMarkedText(abs, r.abstract, !useTitleCue && abstractCue && abstractCue.score > 0 ? abstractCue : null);",
        "      renderAnnotatedText(abs, r.abstract, r._task_evidence);",
    )
    output = replace_once(
        output,
        "    el('jumpInput').value = idx+1;",
        "    el('jumpInput').value = RECORD_OFFSET + idx + 1;",
    )
    output = replace_once(
        output,
        "    v = Math.max(1, Math.min(records.length, v));\n"
        "    records[idx].human_notes = el('notesInput').value;\n"
        "    idx = v-1;",
        "    v = Math.max(RECORD_OFFSET + 1, Math.min(RECORD_OFFSET + records.length, v));\n"
        "    records[idx].human_notes = el('notesInput').value;\n"
        "    idx = v - RECORD_OFFSET - 1;",
    )
    output = replace_once(
        output,
        "    download('11_validation_sample_reviewed.csv', toCSV(records));",
        f"    download('11_validation_sample_reviewed_{range_label}.csv', toCSV(records));",
    )
    output = replace_once(
        output,
        "  document.addEventListener('keydown', e=>{\n"
        "    if (document.activeElement && document.activeElement.tagName === 'TEXTAREA') {",
        "  document.addEventListener('keydown', e=>{\n"
        "    if (!introScreen.hidden) return;\n"
        "    if (document.activeElement && document.activeElement.tagName === 'TEXTAREA') {",
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build records 1-150 and 151-300 as self-contained browser reviewers."
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_SOURCE,
                        help="reviewer HTML template")
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION,
                        help="300-record validation CSV")
    parser.add_argument("--screening", type=Path, default=DEFAULT_SCREENING,
                        help="AI screening CSV used only to locate optional evidence cues")
    parser.add_argument("--output-dir", type=Path, default=ROOT,
                        help="directory for the two generated HTML files")
    args = parser.parse_args()

    source = args.template.read_text(encoding="utf-8")
    if not SEED_PATTERN.search(source):
        raise ValueError("Could not find the seed-data element in the HTML template")
    if args.validation.exists():
        with args.validation.open(newline="", encoding="utf-8-sig") as handle:
            records = list(csv.DictReader(handle))
    else:
        existing = [
            args.output_dir / "pact_validation_review_001-150.html",
            args.output_dir / "pact_validation_review_151-300.html",
        ]
        if not all(path.exists() for path in existing):
            raise FileNotFoundError(
                f"Validation CSV not found at {args.validation}, and existing reviewer HTML files "
                "were not available as a fallback."
            )
        records = embedded_records(existing[0]) + embedded_records(existing[1])
    if len(records) != 300:
        raise ValueError(f"Expected 300 records, found {len(records)}")
    if args.screening.exists():
        with args.screening.open(newline="", encoding="utf-8-sig") as handle:
            screening_by_pmid = {row["pmid"]: row for row in csv.DictReader(handle)}
        records = annotate_records(records, screening_by_pmid)
    else:
        records = [{**record, "_ai_gpt": "", "_ai_claude": ""} for record in records]

    outputs = [
        (1, 150, args.output_dir / "pact_validation_review_001-150.html"),
        (151, 300, args.output_dir / "pact_validation_review_151-300.html"),
    ]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for start, end, path in outputs:
        path.write_text(build_version(source, records, start, end), encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
