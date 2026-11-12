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
      apps to (re)publish (orders may be fractional, e.g. "25.1"). Writes each
      page to week-NN/<grade>-<activity>/ (week 11 -> set3-projects/,
      week 12 -> set4-projects/, week 13 or any unknown week -> extra-lessons/,
      source "mif" -> mif-lessons/<grade>-<mifLesson>-<activity>/),
      updates apps.json, and rebuilds the home page index.html.
      ORDERS is a comma-separated list of orders that were flagged (e.g. they
      call window.claude) and must not be published.
      --manual publishes FILE's pages even for done apps the plan skips
      because their url isn't a claude.ai artifact (HTML uploaded by hand).
"""
import argparse
import datetime as dt
import glob
import html
import json
import os
import re
import sys

GRADES = ["K", "Grade 1", "Grade 2", "Grade 3", "Grade 4", "Grade 5"]
MANIFEST = "apps.json"
RUNTIME_PATTERNS = [r"window\.claude", r"\bclaude\.(complete|ask|storage|db)\b", r"window\.storage\b", r"sendPrompt\s*\("]


# Project sets live after the ten weekly sections, under their own folders.
PROJECT_SETS = {11: ("set3-projects", "Set 3 projects"), 12: ("set4-projects", "Set 4 projects")}
EXTRA = ("extra-lessons", "Extra lessons")
MIF = ("mif-lessons", "Math in Focus chapter lessons")
MIF_GRADES = ["Grade 1", "Grade 2", "Grade 3", "Grade 4"]
# Section keys in page order: 1..10 (weeks), 11, 12 (project sets), "extra", "mif".
SECTION_ORDER = list(range(1, 11)) + sorted(PROJECT_SETS) + ["extra", "mif"]


def section_of(doc):
    """Which home-page section (and folder) a tracker row / manifest entry belongs to."""
    if doc.get("source") == "mif":
        return "mif"
    try:
        w = float(doc.get("week"))
    except (TypeError, ValueError):
        return "extra"
    if w.is_integer() and (1 <= w <= 10 or int(w) in PROJECT_SETS):
        return int(w)
    return "extra"  # week 13 and any unknown week value


def okey(x):
    """Normalize an order value so 7, 7.0 and "7" match, and 25.1 stays 25.1."""
    f = float(x)
    return int(f) if f.is_integer() else f


def slug(s):
    s = s.lower().replace("&", " ").replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def app_path(doc):
    sec = section_of(doc)
    name = f"{slug(doc['grade'])}-{slug(doc['activity'])}"
    if sec == "mif":
        return f"{MIF[0]}/{slug(doc['grade'])}-{slug(doc.get('mifLesson') or '')}-{slug(doc['activity'])}/index.html".replace("--", "-")
    if sec == "extra":
        folder = EXTRA[0]
    elif sec in PROJECT_SETS:
        folder = PROJECT_SETS[sec][0]
    else:
        folder = f"week-{sec:02d}"
    return f"{folder}/{name}/index.html"


def load_tracker(d):
    docs = []
    for f in sorted(glob.glob(os.path.join(d, "*.json"))):
        with open(f) as fh:
            doc = json.load(fh)
        doc = doc.get("data", doc)
        doc.setdefault("id", os.path.splitext(os.path.basename(f))[0])
        doc["order"] = okey(doc["order"])
        docs.append(doc)
    return docs


def load_manifest():
    if not os.path.exists(MANIFEST):
        return []
    with open(MANIFEST) as fh:
        manifest = json.load(fh)
    for m in manifest:
        m["order"] = okey(m["order"])
    return manifest


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
            # Built elsewhere (e.g. Gemini): published only from HTML David supplies by hand.
            pub = by_order.get(d["order"])
            if not pub:
                out["skipped"].append({**item, "reason": "not a claude.ai artifact (needs HTML uploaded by hand)"})
            elif pub["sourceUrl"] != url:
                out["skipped"].append({**item, "reason": "external link changed since its HTML was uploaded (old version still live)"})
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
.chap{margin:0; font-size:15px; font-weight:500; color:var(--ink)}
h3.sub{margin:22px 0 10px; font-size:19px; font-weight:600; display:flex; align-items:baseline; gap:10px}
h3.sub small{font-size:14px; font-weight:500; color:var(--muted)}
.soon{padding:18px; border:1.5px dashed var(--line); border-radius:16px; color:var(--muted); font-family:var(--serif); font-style:italic}
footer{margin-top:48px; padding-top:18px; border-top:1.5px solid var(--line); display:flex; flex-wrap:wrap; justify-content:space-between; gap:8px; color:var(--muted); font-size:15px}
@media (prefers-reduced-motion: reduce){a.card{transition:none} a.card:hover{transform:none}}
@media (max-width:540px){.wrap{padding-top:22px} .grid{grid-template-columns:1fr} a.card{min-height:0}}
"""


def render_index(manifest, docs_by_order, labels, total, today):
    def info(m):
        d = docs_by_order.get(m["order"], {})
        return {**d, **m}

    rows = [info(m) for m in manifest]
    rank = lambda m: (GRADES.index(m["grade"]) if m["grade"] in GRADES else 99, m["order"])
    groups = {k: [] for k in SECTION_ORDER}
    for m in rows:
        groups[section_of(m)].append(m)
    # Weeks 1-10 always show; the later sections show once one of their apps is published.
    shown = [k for k in SECTION_ORDER if isinstance(k, int) and k <= 10 or groups[k]]

    def anchor(k):
        if k == "extra":
            return "extra-lessons"
        if k == "mif":
            return "math-in-focus"
        return f"set-{k - 8}" if k in PROJECT_SETS else f"week-{k}"

    def short(k):
        if k == "extra":
            return EXTRA[1]
        if k == "mif":
            return "Math in Focus"
        return PROJECT_SETS[k][1] if k in PROJECT_SETS else f"Week {k}"

    def title(k):
        if k in PROJECT_SETS:
            return labels.get(k) or short(k)
        if k == "mif":
            return MIF[1]
        return short(k)

    def card(m, tag=None, sub=None):
        href = m["path"][: -len("index.html")]
        built = nice_date(m.get("builtOn"))
        note = (m.get("note") or "").strip()
        return (
            f'<a class="card" href="{html.escape(href)}">'
            f'<span class="grade">{html.escape(tag or m["grade"])}</span>'
            f'<h3>{html.escape(m["activity"])}</h3>'
            + (f'<p class="chap">{html.escape(sub)}</p>' if sub else "")
            + (f'<p class="note" title="{html.escape(note)}">{html.escape(note)}</p>' if note else "")
            + f'<span class="meta"><span>{"Built " + built if built else "Build date not recorded"}</span>'
            f'<span class="go">Open app &rarr;</span></span></a>'
        )

    def count(n):
        return f"<small>{n} app{'s' if n != 1 else ''}</small>"

    empty = ' class="empty"'
    nav = "".join(f'<a href="#{anchor(k)}"{"" if groups[k] else empty}>{short(k)}</a>' for k in shown)
    sections = []
    for k in shown:
        apps = groups[k]
        if k == "mif":
            parts = []
            for g in MIF_GRADES + sorted({m["grade"] for m in apps} - set(MIF_GRADES)):
                ga = sorted([m for m in apps if m["grade"] == g], key=lambda m: m["order"])
                if not ga:
                    continue
                cards = "".join(
                    card(m, tag=f"Ch {m.get('chapter', '?')} · {m.get('mifLesson', '')}", sub=m.get("chapterTitle"))
                    for m in ga
                )
                parts.append(f'<h3 class="sub">{html.escape(g)} {count(len(ga))}</h3><div class="grid">{cards}</div>')
            body = "".join(parts)
        elif apps:
            body = '<div class="grid">' + "".join(card(m) for m in sorted(apps, key=rank)) + "</div>"
        else:
            body = '<p class="soon">Apps for this week are on the way.</p>'
        sections.append(f'<section id="{anchor(k)}"><h2>{html.escape(title(k))} {count(len(apps)) if apps else ""}</h2>{body}</section>')
    updated = nice_date(today)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Enrichment Apps</title>
<meta name="description" content="Interactive K–5 math enrichment apps, organized by week, project set and Math in Focus chapter.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;1,8..60,400&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
<h1>Enrichment Apps</h1>
<p>Interactive K–5 math enrichment activities for the classroom board, organized by week, project and chapter. Tap a card to open an app.</p>
</header>
<nav class="weeks" aria-label="Jump to section">{nav}</nav>
<main>
{chr(10).join(sections)}
</main>
<footer><span>Updated {updated}</span><span>{len(manifest)} of {total} apps</span></footer>
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
    b.add_argument("--manual", action="store_true",
                   help="publish the fetched files even for apps the plan skips (HTML uploaded by hand, e.g. Gemini builds)")
    b.add_argument("--today", default=dt.date.today().isoformat())
    a = ap.parse_args()

    docs = load_tracker(a.tracker)
    if not docs:
        sys.exit(f"no tracker documents found in {a.tracker}")
    manifest = load_manifest()

    if a.cmd == "plan":
        print(json.dumps(plan(docs, manifest), indent=2, ensure_ascii=False))
        return

    by_order = {d["order"]: d for d in docs}
    fetched = {}
    if a.fetched:
        with open(a.fetched) as fh:
            fetched = {okey(k): v for k, v in json.load(fh).items()}
    flagged = {okey(x) for x in a.flagged.split(",") if x.strip()}
    pending = {i["order"] for k in ("new", "rebuilt") for i in plan(docs, manifest)[k]}
    if a.manual:
        pending |= {d["order"] for d in docs if d.get("status") == "done" and (d.get("url") or "").strip()}

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
        if doc.get("source"):
            entries[order]["source"] = doc["source"]
        if doc.get("source") == "mif":
            for k in ("mifLesson", "chapter", "chapterTitle"):
                if doc.get(k) not in (None, ""):
                    entries[order][k] = doc[k]
        added.append({"order": order, "activity": doc["activity"], "path": path, "rebuilt": bool(old)})

    manifest = sorted(entries.values(), key=lambda m: m["order"])
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    docs_by_order = {d["order"]: d for d in docs}
    labels = {}
    for d in docs:
        sec = section_of(d)
        if d.get("weekLabel") and sec in PROJECT_SETS:
            labels.setdefault(sec, d["weekLabel"])
    unknown = sorted({str(d.get("week")) for d in docs if section_of(d) == "extra" and str(d.get("week")) != "13"})
    with open("index.html", "w", encoding="utf-8") as fh:
        fh.write(render_index(manifest, docs_by_order, labels, len(docs), a.today))
    print(json.dumps({"added": added, "flaggedRuntime": runtime, "published": len(manifest), "unknownWeeks": unknown}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
