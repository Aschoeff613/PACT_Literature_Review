"""
STEP 0 - Find out why an API call is failing.

A 400 Bad Request means the request was malformed or the model name is wrong.
The useful detail is in the response BODY, which most scripts throw away. This
prints it, lists the model names your key can actually use, and then tries the
exact call that 03_screen.py makes so you can see which part it dislikes.

Run it with:   python3 scripts/00_diagnose_api.py
"""
import os, json, urllib.request, urllib.error

def call(url, headers, payload=None):
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data,
        headers={**({"Content-Type":"application/json"} if payload else {}), **headers})
    try:
        return "ok", json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}", e.read().decode("utf-8","ignore")[:900]
    except Exception as e:
        return "error", str(e)

print("=== OpenAI: which models can your key use? ===")
k = os.environ.get("OPENAI_API_KEY")
if not k:
    print("  no OPENAI_API_KEY set in this terminal")
else:
    st, r = call("https://api.openai.com/v1/models", {"Authorization":"Bearer "+k})
    if st == "ok":
        names = sorted(m["id"] for m in r.get("data",[]))
        chat = [n for n in names if n.startswith(("gpt-","o1","o3","o4"))]
        print(f"  {len(chat)} chat-capable models:")
        for n in chat: print("    ", n)
        print("\n  >>> Copy one of these EXACTLY into OPENAI_MODEL in scripts/03_screen.py")
    else:
        print(f"  {st}: {r}")

    print("\n=== OpenAI: try the actual screening call, stripping one option at a time ===")
    model = os.environ.get("PROBE_MODEL", "gpt-5.4-mini")
    # The message must contain the literal word "json" - OpenAI's response_format:
    # json_object mode requires it and rejects the request otherwise (reported as
    # "param": "messages", which looks like an unrelated failure if you don't know
    # that). screen_prompt.txt already says "Return ONLY valid JSON", so the real
    # 03_screen.py calls satisfy this; this probe needs to as well or it reports a
    # false failure that has nothing to do with the model or your key.
    base = {"model": model, "messages":[{"role":"user","content":"Reply with a JSON object: {\"ok\":true}"}]}
    variants = [
        ("full request (as 03_screen.py sends it)", {**base, "temperature":0,
            "response_format":{"type":"json_object"}}),
        ("without temperature",                    {**base, "response_format":{"type":"json_object"}}),
        ("without response_format",                {**base, "temperature":0}),
        ("bare minimum",                           base),
        ("max_completion_tokens instead",          {**base, "max_completion_tokens":50}),
    ]
    for label, payload in variants:
        st, r = call("https://api.openai.com/v1/chat/completions",
                     {"Authorization":"Bearer "+k}, payload)
        print(f"  {label}: {st}")
        if st != "ok": print(f"      {r[:400]}")

print("\n=== Anthropic ===")
k2 = os.environ.get("ANTHROPIC_API_KEY")
if not k2:
    print("  no ANTHROPIC_API_KEY set")
else:
    st, r = call("https://api.anthropic.com/v1/models",
                 {"x-api-key":k2, "anthropic-version":"2023-06-01"})
    if st == "ok":
        for m in r.get("data",[]): print("    ", m.get("id"))
    else:
        print(f"  {st}: {r}")

print("""
HOW TO READ THIS
  If 'list models' worked but every completion attempt failed with 400, the model
  name is wrong. Use one from the list printed above.
  If 'full request' failed but 'without temperature' worked, the model only accepts
  the default temperature. Delete the temperature line from 03_screen.py.
  If only 'without response_format' worked, that model does not support JSON mode.
  Remove it and rely on the prompt's instruction to return JSON.
  If everything failed with 401, the key is wrong. With 429, you are out of credit.
""")
