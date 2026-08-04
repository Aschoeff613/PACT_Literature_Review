"""Shared helpers. You don't run this file directly."""
import urllib.request, urllib.parse, json, time, os, csv, sys

EMAIL = os.environ.get("PACT_EMAIL", "your.name@stanford.edu")
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

def fetch(url, tries=4, timeout=90):
    """Download a URL. Retries a few times, because NCBI sometimes returns 502."""
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"PACT-review/1.0 ({EMAIL})"})
            return urllib.request.urlopen(req, timeout=timeout).read()
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last

def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"  wrote {len(rows)} rows -> {path}")

def read_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def need(path):
    if not os.path.exists(path):
        sys.exit(f"ERROR: expected file not found:\n  {path}\nRun the earlier numbered script first.")
    return path
