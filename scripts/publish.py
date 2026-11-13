#!/usr/bin/env python3
"""Publish finished enrichment apps from the build tracker to GitHub Pages.

Three subcommands, run from the repo root:

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
      updates apps.json and site.json, and rebuilds the home page index.html.
      ORDERS is a comma-separated list of orders that were flagged (e.g. they
      call window.claude) and must not be published.
      --manual publishes FILE's pages even for done apps the plan skips
      because their url isn't a claude.ai artifact (HTML uploaded by hand).

  render
      Rebuilds index.html from apps.json and site.json alone, without the
      tracker. Use it after changing the home page's markup in this file.

The home page's styles, script and drawing are in assets/. Each app page
loads assets/home-link.js, a small button that leads back to the home page.
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
SITE = "site.json"
HOME_LINK = '<script src="../../assets/home-link.js" defer></script>'
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
    """Make sure the page has a doctype, charset, viewport and a way back to the home page."""
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
    return with_home_link(page)


def with_home_link(page):
    """Add the small 'all apps' button that leads back to the home page."""
    if "assets/home-link.js" in page:
        return page
    i = page.lower().rfind("</body>")
    return page + HOME_LINK if i < 0 else page[:i] + HOME_LINK + page[i:]


def nice_date(s):
    try:
        d = dt.date.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return f"{d.strftime('%b')} {d.day}, {d.year}"


GRADE_CLASS = {"K": "g-k", "Grade 1": "g-1", "Grade 2": "g-2", "Grade 3": "g-3", "Grade 4": "g-4", "Grade 5": "g-5"}
SEARCH_ICON = ('<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" '
               'stroke-linecap="round" aria-hidden="true"><circle cx="8.5" cy="8.5" r="6"/><path d="M13 13l5 5"/></svg>')


def render_index(manifest, labels, total, today):
    """The home page. Its look lives in assets/site.css, its filtering in assets/site.js."""
    rank = lambda m: (GRADES.index(m["grade"]) if m["grade"] in GRADES else 99, m["order"])
    groups = {k: [] for k in SECTION_ORDER}
    for m in manifest:
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

    def card(m):
        href = m["path"][: -len("index.html")]
        built = nice_date(m.get("builtOn"))
        note = (m.get("note") or "").strip()
        grade = m["grade"]
        chap = ""
        if section_of(m) == "mif":
            bits = [f"Chapter {m['chapter']}" if m.get("chapter") not in (None, "") else "",
                    f"Lesson {m['mifLesson']}" if m.get("mifLesson") else "", m.get("chapterTitle") or ""]
            chap = " · ".join(b for b in bits if b)
        return (
            f'<a class="card {GRADE_CLASS.get(grade, "")}" href="{html.escape(href)}" data-grade="{html.escape(grade)}">'
            f'<span class="tag">{"Kindergarten" if grade == "K" else html.escape(grade)}</span>'
            f'<span class="card-body"><h3>{html.escape(m["activity"])}</h3>'
            + (f'<p class="chap">{html.escape(chap)}</p>' if chap else "")
            + (f'<p class="note">{html.escape(note)}</p>' if note else "")
            + '<span class="meta">'
            + (f"<span>Built {built}</span>" if built else "")
            + '<span class="go">Open &rarr;</span></span></span></a>'
        )

    def count(n):
        return f"<small>{n} app{'s' if n != 1 else ''}</small>"

    def jump(k):
        off = "" if groups[k] else " off"
        if isinstance(k, int) and k <= 10:
            return f'<a class="jump wk{off}" href="#{anchor(k)}" aria-label="Week {k}">{k}</a>'
        return f'<a class="jump{off}" href="#{anchor(k)}">{html.escape(short(k))}</a>'

    weeks = "".join(jump(k) for k in shown if isinstance(k, int) and k <= 10)
    rest = "".join(jump(k) for k in shown if not (isinstance(k, int) and k <= 10))
    def chip_label(g):  # phones get the short form: K, 1, 2 ...
        if g == "K":
            return 'K<span class="wide">indergarten</span>'
        return f'<span class="wide">Grade </span>{g.split()[-1]}'

    chips = '<button type="button" class="chip all" data-grade="" aria-pressed="true"><span>All<span class="wide"> grades</span></span></button>' + "".join(
        f'<button type="button" class="chip {GRADE_CLASS[g]}" data-grade="{g}" aria-label="{"Kindergarten" if g == "K" else g}" aria-pressed="false"><span>{chip_label(g)}</span></button>'
        for g in GRADES if any(m["grade"] == g for m in manifest)
    )
    sections = []
    for k in shown:
        apps = groups[k]
        if apps:
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
<link href="https://fonts.googleapis.com/css2?family=Nunito+Sans:opsz,wght@6..12,400;6..12,700;6..12,800&family=Shantell+Sans:wght@600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="assets/site.css">
</head>
<body>
<a class="skip" href="#apps">Skip to the apps</a>
<div class="wrap" id="top">
<header class="banner">
<div class="banner-text">
<h1>Enrichment Apps</h1>
<p>Interactive K–5 math activities for the classroom board. Pick a grade, then tap a card to open an app.</p>
</div>
<img src="assets/crowd.svg" width="1220" height="232" alt="">
</header>
<form class="search needs-js" role="search" onsubmit="return false" hidden>
{SEARCH_ICON}
<input id="q" type="search" placeholder="Search apps, e.g. fractions" aria-label="Search apps" autocomplete="off">
</form>
<div class="bar needs-js" hidden>
<div class="row" role="group" aria-label="Show one grade"><span class="row-label">Grade</span>{chips}</div>
<nav class="row" aria-label="Jump to section"><span class="row-label">Week</span>{weeks}<span class="gap"></span>{rest}</nav>
</div>
<p class="status needs-js" id="status" aria-live="polite" hidden><span></span><button type="button" hidden>Show everything</button></p>
<main id="apps">
{chr(10).join(sections)}
<p class="none" id="none" hidden>No apps match. Try another word or grade.</p>
</main>
<footer><span>Updated {updated}</span><span>{len(manifest)} of {total} apps built so far</span></footer>
</div>
<a class="top" href="#top" aria-label="Back to top" hidden>&uarr;</a>
<script src="assets/site.js"></script>
</body>
</html>
"""


def load_site():
    """Facts about the tracker that the home page needs, kept so `render` can run without it."""
    if not os.path.exists(SITE):
        return {}
    with open(SITE) as fh:
        return json.load(fh)


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
    sub.add_parser("render")
    a = ap.parse_args()

    if a.cmd == "render":
        site = load_site()
        manifest = load_manifest()
        labels = {int(k): v for k, v in site.get("labels", {}).items()}
        with open("index.html", "w", encoding="utf-8") as fh:
            fh.write(render_index(manifest, labels, site.get("total", len(manifest)), site.get("updated")))
        print(json.dumps({"published": len(manifest)}))
        return

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
    for m in manifest:  # card descriptions follow the tracker's notes
        d = by_order.get(m["order"])
        if d and "note" in d:
            note = (d.get("note") or "").strip()
            if note:
                m["note"] = note
            else:
                m.pop("note", None)
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    labels = {}
    for d in docs:
        sec = section_of(d)
        if d.get("weekLabel") and sec in PROJECT_SETS:
            labels.setdefault(sec, d["weekLabel"])
    unknown = sorted({str(d.get("week")) for d in docs if section_of(d) == "extra" and str(d.get("week")) != "13"})
    with open("index.html", "w", encoding="utf-8") as fh:
        fh.write(render_index(manifest, labels, len(docs), a.today))
    with open(SITE, "w", encoding="utf-8") as fh:
        json.dump({"total": len(docs), "updated": a.today, "labels": {str(k): v for k, v in labels.items()}}, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(json.dumps({"added": added, "flaggedRuntime": runtime, "published": len(manifest), "unknownWeeks": unknown}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
