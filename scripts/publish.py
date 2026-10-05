#!/usr/bin/env python3
"""Publish finished enrichment apps from the build tracker to GitHub Pages.

Two subcommands, run from the repo root:

  plan  --tracker DIR
      Reads the tracker documents (one JSON file per doc, as saved by
      ArtifactData with out_dir) and apps.json, and prints a JSON plan:
      which apps are new, which were rebuilt (url changed), which are
      skipped (done but no url, or url is not a claude.ai artifact).

  build --tracker DIR [--fetched FILE] [--flagged ORDERS] [--today YYYY-MM-DD]
      FILE is JSON {"<order>": "<path to fetched index.html>", ...} for the
      apps to (re)publish. Writes each page to week-NN/<grade>-<activity>/,
      updates apps.json, and rebuilds the home page index.html.
      ORDERS is a comma-separated list of orders that were flagged (e.g. they
      call window.claude) and must not be published.
"""
import argparse
import datetime as dt
import glob
import html
import json
import os
import re
import sys

TOTAL = 55
GRADES = ["K", "Grade 1", "Grade 2", "Grade 3", "Grade 4", "Grade 5"]
MANIFEST = "apps.json"
RUNTIME_PATTERNS = [r"window\.claude", r"\bclaude\.(complete|ask|storage|db)\b", r"window\.storage\b", r"sendPrompt\s*\("]


def slug(s):
    s = s.lower().replace("&", " ").replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def app_path(doc):
    return f"week-{int(doc['week']):02d}/{slug(doc['grade'])}-{slug(doc['activity'])}/index.html"


def load_tracker(d):
    docs = []
    for f in sorted(glob.glob(os.path.join(d, "*.json"))):
        with open(f) as fh:
            doc = json.load(fh)
        doc = doc.get("data", doc)
        doc.setdefault("id", os.path.splitext(os.path.basename(f))[0])
        docs.append(doc)
    return docs


def load_manifest():
    if not os.path.exists(MANIFEST):
        return []
    with open(MANIFEST) as fh:
        return json.load(fh)


def is_artifact(url):
    return bool(re.match(r"https://claude\.ai/(code/)?artifact/", url or ""))


def plan(docs, manifest):
    by_order = {m["order"]: m for m in manifest}
    out = {"new": [], "rebuilt": [], "skipped": [], "published": len(manifest)}
    for d in sorted(docs, key=lambda d: d["order"]):
        if d.get("status") != "done":
            continue
        url = (d.get("url") or "").strip()
        item = {"order": d["order"], "grade": d["grade"], "week": d["week"], "activity": d["activity"], "url": url}
        if not url:
            out["skipped"].append({**item, "reason": "no url in tracker"})
        elif not is_artifact(url):
            out["skipped"].append({**item, "reason": "not a claude.ai artifact (can't copy)"})
        elif d["order"] not in by_order:
            out["new"].append(item)
        elif by_order[d["order"]]["sourceUrl"] != url:
            out["rebuilt"].append(item)
    return out


def needs_runtime(page):
    return any(re.search(p, page) for p in RUNTIME_PATTERNS)


def standalone(page, title):
    """Make sure the page has a doctype, charset and viewport."""
    head_meta = ""
    if not re.search(r"<meta[^>]+charset", page, re.I):
        head_meta += '<meta charset="utf-8">'
    if not re.search(r"<meta[^>]+name=[\"']?viewport", page, re.I):
        head_meta += '<meta name="viewport" content="width=device-width, initial-scale=1">'
    if not re.search(r"<title>", page, re.I):
        head_meta += f"<title>{html.escape(title)}</title>"
    if head_meta:
        if re.search(r"<head[^>]*>", page, re.I):
            page = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + head_meta, page, count=1, flags=re.I)
        elif re.search(r"<html[^>]*>", page, re.I):
            page = re.sub(r"(<html[^>]*>)", lambda m: m.group(1) + "<head>" + head_meta + "</head>", page, count=1, flags=re.I)
        else:
            page = "<head>" + head_meta + "</head>" + page
    if not re.match(r"\s*<!doctype html", page, re.I):
        page = "<!doctype html>\n" + page
    return page


def nice_date(s):
    try:
        d = dt.date.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return f"{d.strftime('%b')} {d.day}, {d.year}"


CSS = """
:root{
  --paper:#F3F4F6; --card:#FFFFFF; --ink:#1C2130; --muted:#5B6170; --line:#D6D8DD;
  --accent:#DF661A; --accent-soft:#FDEBDD;
  --sans:"Poppins","Segoe UI",system-ui,sans-serif;
  --serif:"Source Serif 4",Georgia,"Times New Roman",serif;
  color-scheme:light;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --paper:#14161B; --card:#1D2027; --ink:#ECEBE8; --muted:#A4A8B2; --line:#353A46;
    --accent:#F2893C; --accent-soft:#3A2618; color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --paper:#14161B; --card:#1D2027; --ink:#ECEBE8; --muted:#A4A8B2; --line:#353A46;
  --accent:#F2893C; --accent-soft:#3A2618; color-scheme:dark;
}
*,*::before,*::after{box-sizing:border-box}
body{margin:0; background:var(--paper); color:var(--ink); font-family:var(--sans); line-height:1.4; -webkit-tap-highlight-color:transparent}
.wrap{max-width:1120px; margin:0 auto; padding:32px 16px 48px}
header h1{margin:0; font-size:clamp(30px,5vw,44px); font-weight:700; letter-spacing:-0.01em}
header p{margin:6px 0 0; font-family:var(--serif); font-style:italic; color:var(--muted); font-size:clamp(17px,2.2vw,20px)}
nav.weeks{display:flex; flex-wrap:wrap; gap:8px; margin:22px 0 4px}
nav.weeks a{min-width:48px; min-height:48px; display:inline-grid; place-items:center; padding:0 14px; border-radius:24px; border:1.5px solid var(--line); background:var(--card); color:var(--ink); text-decoration:none; font-weight:600}
nav.weeks a:hover{border-color:var(--ink)}
nav.weeks a.empty{color:var(--muted); font-weight:500}
section{margin-top:34px; scroll-margin-top:16px}
section h2{margin:0 0 14px; font-size:clamp(22px,3vw,28px); font-weight:700; display:flex; align-items:baseline; gap:12px}
section h2 small{font-size:15px; font-weight:500; color:var(--muted)}
.grid{display:grid; grid-template-columns:repeat(auto-fill,minmax(min(250px,100%),1fr)); gap:14px}
a.card{min-width:0; display:flex; flex-direction:column; gap:6px; min-height:150px; padding:18px 18px 16px; background:var(--card); border:1.5px solid var(--line); border-radius:16px; color:var(--ink); text-decoration:none; transition:border-color .15s, transform .15s}
a.card:hover{border-color:var(--accent); transform:translateY(-2px)}
a.card:focus-visible{outline:3px solid var(--accent); outline-offset:2px}
.grade{align-self:flex-start; font-size:13px; font-weight:600; letter-spacing:.04em; text-transform:uppercase; color:var(--accent); background:var(--accent-soft); padding:3px 10px; border-radius:12px}
.card h3{margin:2px 0 0; font-size:19px; font-weight:600; line-height:1.25}
.note{margin:0; font-family:var(--serif); color:var(--muted); font-size:15px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
.meta{margin-top:auto; display:flex; justify-content:space-between; align-items:center; gap:8px; padding-top:8px; font-size:14px; color:var(--muted)}
.meta span{white-space:nowrap}
.go{font-weight:600; color:var(--accent)}
.soon{padding:18px; border:1.5px dashed var(--line); border-radius:16px; color:var(--muted); font-family:var(--serif); font-style:italic}
footer{margin-top:48px; padding-top:18px; border-top:1.5px solid var(--line); display:flex; flex-wrap:wrap; justify-content:space-between; gap:8px; color:var(--muted); font-size:15px}
@media (prefers-reduced-motion: reduce){a.card{transition:none} a.card:hover{transform:none}}
@media (max-width:540px){.wrap{padding-top:22px} .grid{grid-template-columns:1fr} a.card{min-height:0}}
"""


def render_index(manifest, notes, today):
    rows = sorted(manifest, key=lambda m: (m["week"], GRADES.index(m["grade"]) if m["grade"] in GRADES else 99, m["order"]))
    weeks = {w: [m for m in rows if m["week"] == w] for w in range(1, 11)}
    empty = ' class="empty"'
    nav = "".join(f'<a href="#week-{w}"{"" if weeks[w] else empty}>Week {w}</a>' for w in range(1, 11))
    sections = []
    for w in range(1, 11):
        apps = weeks[w]
        if apps:
            cards = []
            for m in apps:
                href = m["path"][: -len("index.html")]
                built = nice_date(m.get("builtOn"))
                note = (notes.get(m["order"]) or "").strip()
                cards.append(
                    f'<a class="card" href="{html.escape(href)}">'
                    f'<span class="grade">{html.escape(m["grade"])}</span>'
                    f'<h3>{html.escape(m["activity"])}</h3>'
                    + (f'<p class="note" title="{html.escape(note)}">{html.escape(note)}</p>' if note else "")
                    + f'<span class="meta"><span>{"Built " + built if built else "Build date not recorded"}</span>'
                    f'<span class="go">Open app &rarr;</span></span></a>'
                )
            body = '<div class="grid">' + "".join(cards) + "</div>"
            count = f"<small>{len(apps)} app{'s' if len(apps) != 1 else ''}</small>"
        else:
            body = '<p class="soon">Apps for this week are on the way.</p>'
            count = ""
        sections.append(f'<section id="week-{w}"><h2>Week {w} {count}</h2>{body}</section>')
    updated = nice_date(today)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Enrichment Apps</title>
<meta name="description" content="Interactive K–5 math enrichment apps, organized by week.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;1,8..60,400&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
<h1>Enrichment Apps</h1>
<p>Interactive K–5 math enrichment activities for the classroom board, organized by week. Tap a card to open an app.</p>
</header>
<nav class="weeks" aria-label="Jump to week">{nav}</nav>
<main>
{chr(10).join(sections)}
</main>
<footer><span>Updated {updated}</span><span>{len(manifest)} of {TOTAL} apps</span></footer>
</div>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--tracker", required=True)
    b = sub.add_parser("build")
    b.add_argument("--tracker", required=True)
    b.add_argument("--fetched")
    b.add_argument("--flagged", default="")
    b.add_argument("--today", default=dt.date.today().isoformat())
    a = ap.parse_args()

    docs = load_tracker(a.tracker)
    if len(docs) != TOTAL:
        print(f"warning: tracker has {len(docs)} documents, expected {TOTAL}", file=sys.stderr)
    manifest = load_manifest()

    if a.cmd == "plan":
        print(json.dumps(plan(docs, manifest), indent=2, ensure_ascii=False))
        return

    by_order = {d["order"]: d for d in docs}
    fetched = {}
    if a.fetched:
        with open(a.fetched) as fh:
            fetched = {int(k): v for k, v in json.load(fh).items()}
    flagged = {int(x) for x in a.flagged.split(",") if x.strip()}
    pending = {i["order"] for k in ("new", "rebuilt") for i in plan(docs, manifest)[k]}

    entries = {m["order"]: m for m in manifest}
    added, runtime = [], []
    for order, src in sorted(fetched.items()):
        if order in flagged or order not in pending:
            continue
        doc = by_order[order]
        with open(src, encoding="utf-8") as fh:
            page = fh.read()
        if needs_runtime(page):
            runtime.append(doc["activity"])
            continue
        path = app_path(doc)
        old = entries.get(order)
        if old and old["path"] != path and os.path.exists(old["path"]):
            os.remove(old["path"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(standalone(page, doc["activity"]))
        entries[order] = {
            "order": order,
            "grade": doc["grade"],
            "week": doc["week"],
            "activity": doc["activity"],
            "sourceUrl": doc["url"].strip(),
            "path": path,
            "builtOn": doc.get("builtOn") or None,
            "publishedOn": a.today,
        }
        added.append({"order": order, "activity": doc["activity"], "path": path, "rebuilt": bool(old)})

    manifest = sorted(entries.values(), key=lambda m: m["order"])
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    notes = {d["order"]: d.get("note", "") for d in docs}
    with open("index.html", "w", encoding="utf-8") as fh:
        fh.write(render_index(manifest, notes, a.today))
    print(json.dumps({"added": added, "flaggedRuntime": runtime, "published": len(manifest)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
