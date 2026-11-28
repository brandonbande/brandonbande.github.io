#!/usr/bin/env python3
"""Open Analytics Work: section builder for brandonbande.co.zw.

Ported from the rogue0015.github.io blog engine (scripts/build_blog.py, Nov 2026)
and adapted for publishing analytics work in the open. Standard library only.

What it keeps from the source ("blog dynamics"):
  Markdown + front matter -> static article pages, a paginated index, a tag filter
  that shows matches from every page and is shareable via ?tag=, previous/next
  pagers, an RSS 2.0 feed with full text, JSON-LD, and GoatCounter view counts.

What changed (see  ):
  - Site identity, navigation and tags come from the data objects in content/
    (site.json, person.json), never from strings in this file.
  - Sources are committed (content/open-analytics/*.md); HTML is written to dist/.
    `draft: true` and future dates are skipped, so nothing leaks early.
  - Analytics front matter: question, summary, data, data_url, methods, tools,
    repo_url, status, canonical. Every piece must open with "## Key findings"
    (answer first, for AEO), which is lifted into a findings block and JSON-LD.
  - Markdown adds pipe tables (with "Table: caption"), heading ids for deep links,
    and root-relative internal links.
  - Pretty URLs: /open-analytics/<slug>/ and /open-analytics/page/<n>/.
  - No /tools sitemap scraping. build() returns sitemap rows; the site build
    (scripts/build.py) owns sitemap.xml.

Usage:
  python3 scripts/open_analytics.py                       # build into dist/
  python3 scripts/open_analytics.py --src DIR --out DIR   # alternative source/output
Preview:
  python3 -m http.server --directory dist 8000   ->  http://localhost:8000/open-analytics/
"""

import argparse
import csv
import html
import json
import re
import shutil
import sys
from datetime import date, datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from string import Template
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
STATIC = ROOT / "static"
DEFAULT_SRC = CONTENT / "open-analytics"
DEFAULT_OUT = ROOT / "dist"
SECTION_DIR = "open-analytics"
TEMPLATE_PLACEHOLDERS = (
    "A clear, specific title for the analysis",
    "One or two sentences that state the main finding plainly.",
)


PUBLISHED = []  # [(url, title)] of the last build(), for llms.txt


class BuildError(Exception):
    """A source file breaks a publishing rule. The message names the file and the fix."""


# --------------------------------------------------------------------- config

def load_config():
    site = json.loads((CONTENT / "site.json").read_text(encoding="utf-8"))
    person = json.loads((CONTENT / "person.json").read_text(encoding="utf-8"))
    sec = site["sections"]["openAnalytics"]
    base = site["url"].rstrip("/")
    path = sec["path"]
    image = person.get("image", {}).get("path") or "/assets/brandon-bande.jpg"
    return {
        "site": base,
        "site_name": site["name"],
        "lang": site.get("language", "en"),
        "locale": site.get("locale", "en_ZW"),
        "theme": site.get("themeColor", "#0F100E"),
        "website_id": f"{base}/#website",
        "path": path,
        "section_url": base + path,
        "title": sec["title"],
        "short_title": sec.get("shortTitle", sec["title"]),
        "description": sec["description"],
        "intro": sec.get("intro", ""),
        "per_page": int(sec.get("perPage", 6)),
        "feed_title": sec.get("feedTitle", sec["title"]),
        "feed_url": f"{base}{path}feed.xml",
        "tags": sec.get("tags", {}),
        "nav": site.get("nav", []),
        "ctas": site.get("ctas", {}),
        "goatcounter": (site.get("analytics", {}).get("goatcounter") or {}).get("code"),
        "image_url": base + image,
        "person": {
            "@type": "Person",
            "@id": person["id"],
            "name": person["name"],
            "alternateName": person.get("brandName"),
            "url": f"{base}/",
            "jobTitle": (person.get("jobTitle") or {}).get("value"),
            "sameAs": [s["url"] for s in person.get("sameAs", [])],
        },
        "author_name": person["name"],
        "brand_name": person.get("brandName", person["name"]),
    }


# --------------------------------------------------------------- front matter

def _split_list(value):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    if not value.strip():
        return []
    return [v.strip() for v in next(csv.reader([value], skipinitialspace=True)) if v.strip()]


def parse_front_matter(text, path):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if not m:
        raise BuildError(f"{path.name}: missing its front matter block (--- ... ---).")
    meta, body = {}, text[m.end():]
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        meta[key.strip()] = val.strip().strip('"').strip("'")
    for key in ("tags", "tools"):
        meta[key] = _split_list(meta.get(key, ""))
    meta["draft"] = meta.get("draft", "").lower() in ("true", "yes", "1")
    for req in ("title", "date", "description", "question", "summary"):
        if not meta.get(req):
            raise BuildError(f"{path.name}: front matter is missing '{req}'. "
                             "Copy content/open-analytics/_post-template.md.")
    for key in ("date", "updated"):
        if meta.get(key):
            try:
                meta[f"{key}_obj"] = date.fromisoformat(meta[key])
            except ValueError:
                raise BuildError(f"{path.name}: invalid {key} '{meta[key]}' (need YYYY-MM-DD).")
    return meta, body


# ------------------------------------------------------------------- markdown

CODE_SPAN = re.compile(r"`([^`]+)`")
TABLE_SEP = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
BLOCK_START = re.compile(r"^(#{1,6}\s|>|```|[-*]\s|\d+\.\s|\|)|^(-{3,}|\*{3,})\s*$")


class Markdown:
    """Small, strict Markdown subset: headings, paragraphs, lists, quotes, code,
    rules, images, links, emphasis and pipe tables. Unique heading ids per page."""

    def __init__(self, site):
        self.site = site
        self.ids = set()

    def url(self, url):
        if url.startswith(self.site):
            url = url[len(self.site):] or "/"
        return url

    def inline(self, text):
        spans = []

        def stash(m):
            spans.append(html.escape(m.group(1), quote=False))
            return f"\x00{len(spans) - 1}\x00"

        text = CODE_SPAN.sub(stash, text)
        text = html.escape(text, quote=False)
        text = re.sub(
            r"!\[([^\]]*)\]\(([^)\s]+)\)",
            lambda m: f'<img src="{self.url(m.group(2))}" alt="{m.group(1).replace(chr(34), "&quot;")}" loading="lazy" decoding="async">',
            text)
        text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
                      lambda m: f'<a href="{self.url(m.group(2))}">{m.group(1)}</a>', text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
        text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<em>\1</em>", text)
        return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{spans[int(m.group(1))]}</code>", text)

    def heading_id(self, text):
        base = re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", text).lower()).strip("-") or "section"
        hid, n = base, 2
        while hid in self.ids:
            hid, n = f"{base}-{n}", n + 1
        self.ids.add(hid)
        return hid

    @staticmethod
    def _cells(line):
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|") and not line.endswith("\\|"):
            line = line[:-1]
        return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line)]

    def table(self, lines, i):
        head = self._cells(lines[i])
        aligns = []
        for spec in self._cells(lines[i + 1]):
            left, right = spec.startswith(":"), spec.endswith(":")
            aligns.append("center" if left and right else "right" if right else "left" if left else "")
        i += 2
        rows = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            rows.append(self._cells(lines[i]))
            i += 1
        caption = ""
        if i < len(lines) and lines[i].startswith("Table:"):
            caption = self.inline(lines[i][len("Table:"):].strip())
            i += 1

        def cell(tag, value, col):
            align = aligns[col] if col < len(aligns) and aligns[col] else ""
            style = f' style="text-align:{align}"' if align else ""
            scope = ' scope="col"' if tag == "th" else ""
            return f"<{tag}{scope}{style}>{self.inline(value)}</{tag}>"

        thead = "<tr>" + "".join(cell("th", h, c) for c, h in enumerate(head)) + "</tr>"
        tbody = "".join(
            "<tr>" + "".join(cell("td", v, c) for c, v in enumerate(r[:len(head)])) + "</tr>" for r in rows)
        label = re.sub(r"<[^>]+>", "", caption) or "Data table"
        cap = f"<caption>{caption}</caption>" if caption else ""
        out = (f'<div class="table-wrap" role="region" tabindex="0" aria-label="{html.escape(label)}">'
               f"<table>{cap}<thead>{thead}</thead><tbody>{tbody}</tbody></table></div>")
        return out, i

    def render(self, md):
        lines = md.split("\n")
        out, i, n = [], 0, len(lines)
        while i < n:
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            if line.startswith("```"):
                i += 1
                buf = []
                while i < n and not lines[i].startswith("```"):
                    buf.append(lines[i])
                    i += 1
                i += 1
                out.append(f"<pre><code>{html.escape(chr(10).join(buf), quote=False)}</code></pre>")
                continue
            m = re.match(r"(#{1,6})\s+(.*)", line)
            if m:
                lvl = len(m.group(1))
                text = self.inline(m.group(2).strip())
                out.append(f'<h{lvl} id="{self.heading_id(text)}">{text}</h{lvl}>')
                i += 1
                continue
            if re.match(r"^(-{3,}|\*{3,})\s*$", line):
                out.append("<hr>")
                i += 1
                continue
            if line.lstrip().startswith("|") and i + 1 < n and TABLE_SEP.match(lines[i + 1].strip()):
                block, i = self.table(lines, i)
                out.append(block)
                continue
            if line.lstrip().startswith(">"):
                buf = []
                while i < n and lines[i].lstrip().startswith(">"):
                    buf.append(lines[i].lstrip()[1:].lstrip())
                    i += 1
                paras = "\n".join(buf).split("\n\n")
                inner = "".join(f"<p>{self.inline(' '.join(p.split()))}</p>" for p in paras if p.strip())
                out.append(f"<blockquote>{inner}</blockquote>")
                continue
            for marker, tag in ((r"^\s*[-*]\s+", "ul"), (r"^\s*\d+\.\s+", "ol")):
                if re.match(marker, line):
                    items = []
                    while i < n and lines[i].strip():
                        if re.match(marker, lines[i]):
                            items.append(re.sub(marker, "", lines[i]).strip())
                        elif lines[i].startswith("  ") and items:
                            items[-1] += " " + lines[i].strip()
                        else:
                            break
                        i += 1
                    out.append(f"<{tag}>" + "".join(f"<li>{self.inline(x)}</li>" for x in items) + f"</{tag}>")
                    break
            else:
                buf = [line.strip()]
                i += 1
                while i < n and lines[i].strip() and not BLOCK_START.match(lines[i].lstrip()):
                    buf.append(lines[i].strip())
                    i += 1
                out.append(f"<p>{self.inline(' '.join(buf))}</p>")
        return "\n".join(out)


# -------------------------------------------------------------------- helpers

def attr(s):
    return html.escape(str(s), quote=True)


def esc(s):
    return html.escape(str(s), quote=False)


def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def words(text):
    return re.findall(r"\w+", re.sub(r"<[^>]+>", " ", text))


def display_date(d):
    return f"{d.day} {d.strftime('%b %Y')}"


def iso_datetime(d):
    """Front-matter date as an ISO 8601 datetime (midnight UTC, as in the RSS feed).

    schema.org datePublished/dateModified and OG article times are DateTimes; Google flags date-only values.
    """
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).isoformat()


def truncate(s, limit=180):
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def page_path(cfg, n):
    return cfg["path"] if n == 1 else f"{cfg['path']}page/{n}/"


KEY_FINDINGS = re.compile(r"^##\s+Key findings\s*$", re.M | re.I)


def split_findings(body, path):
    """Lift the mandatory '## Key findings' list out of the body (answer-first rule)."""
    m = KEY_FINDINGS.search(body)
    if not m:
        raise BuildError(f"{path.name}: needs a '## Key findings' section with a bullet list. "
                         "Lead with the answer; see content/open-analytics/_post-template.md.")
    lines = body[m.end():].split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    start = i
    # The findings block is exactly the bullet list (items plus indented continuation lines).
    while i < len(lines) and (re.match(r"^\s*[-*]\s+\S", lines[i])
                              or (lines[i].startswith("  ") and lines[i].strip() and i > start)):
        i += 1
    block = "\n".join(lines[start:i])
    if not block.strip():
        raise BuildError(f"{path.name}: '## Key findings' must be followed directly by a bullet list.")
    remainder = body[: m.start()] + "\n".join(lines[i:])
    return block, remainder


def check_post(path, slug, meta, cfg):
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
        raise BuildError(f"{path.name}: the file name (slug) must be lowercase-with-hyphens: "
                         "no dates, underscores or capitals.")
    if meta["title"] in TEMPLATE_PLACEHOLDERS or meta["summary"] in TEMPLATE_PLACEHOLDERS:
        raise BuildError(f"{path.name}: still contains template placeholder text.")
    if not meta["tags"]:
        raise BuildError(f"{path.name}: front matter needs 'tags: [..]'.")
    unknown = [t for t in meta["tags"] if t not in cfg["tags"]]
    if unknown:
        raise BuildError(f"{path.name}: unknown tag(s) {unknown}. Use the shared set in "
                         f"content/site.json sections.openAnalytics.tags: {sorted(cfg['tags'])}. "
                         "Add a new tag there only if the piece covers a genuinely new topic.")
    warnings = []
    if not 70 <= len(meta["description"]) <= 160:
        warnings.append(f"description is {len(meta['description'])} chars (aim for 70–160)")
    if len(words(meta["summary"])) > 60:
        warnings.append("summary is over 60 words; answer engines quote short, direct answers")
    for w in warnings:
        print(f"  WARN   {path.name}: {w}")


# ---------------------------------------------------------------------- posts

def load_posts(src, cfg, today):
    posts = []
    if not src.exists():
        return posts
    for path in sorted(src.glob("*.md")):
        if path.name.startswith("_"):
            continue
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"), path)
        if meta["draft"]:
            print(f"  skip   {path.name} (draft)")
            continue
        if meta["date_obj"] > today:
            print(f"  skip   {path.name} (dated {meta['date']}, after today)")
            continue
        slug = path.stem
        check_post(path, slug, meta, cfg)
        findings_md, remainder = split_findings(body, path)
        md = Markdown(cfg["site"])
        md.ids.add("key-findings")
        findings_html = md.render(findings_md)
        content = md.render(remainder)
        canonical = meta.get("canonical") or ""
        url = f"{cfg['section_url']}{slug}/"
        posts.append({
            "slug": slug,
            "title": meta["title"],
            "description": meta["description"],
            "question": meta["question"],
            "summary": meta["summary"],
            "date": meta["date_obj"],
            "updated": meta.get("updated_obj") or meta["date_obj"],
            "tags": meta["tags"],
            "tools": meta["tools"],
            "data": meta.get("data", ""),
            "data_url": meta.get("data_url", ""),
            "methods": meta.get("methods", ""),
            "repo_url": meta.get("repo_url", ""),
            "status": meta.get("status", ""),
            "canonical": canonical or url,
            "external_canonical": bool(canonical) and not canonical.startswith(cfg["site"]),
            "url": url,
            "href": f"{cfg['path']}{slug}/",
            "findings_html": findings_html,
            "findings": [strip_tags(li) for li in re.findall(r"<li>(.*?)</li>", findings_html, re.S)],
            "content": content,
            "words": len(words(findings_html + content + meta["summary"])),
        })
    return sorted(posts, key=lambda p: (p["date"], p["slug"]))  # oldest -> newest


# ------------------------------------------------------------------ templates

PAGE = Template("""<!DOCTYPE html>
<!-- GENERATED by scripts/open_analytics.py from $source. Do not edit dist/; edit the source and rebuild. -->
<html lang="$lang">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<meta name="description" content="$description">
<meta name="author" content="$author">
<meta name="robots" content="$robots">
<meta name="theme-color" content="$theme">
<link rel="canonical" href="$canonical">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="preload" href="/fonts/archivo-latin-wdth-wght.woff2" as="font" type="font/woff2" crossorigin>
$rel_links<link rel="alternate" type="application/rss+xml" title="$feed_title" href="$feed_url">
<meta property="og:type" content="$og_type">
<meta property="og:title" content="$og_title">
<meta property="og:description" content="$description">
<meta property="og:url" content="$canonical">
<meta property="og:site_name" content="$site_name">
<meta property="og:locale" content="$locale">
<meta property="og:image" content="$image">
<meta property="og:image:alt" content="$author">
$article_meta<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="$og_title">
<meta name="twitter:description" content="$description">
<meta name="twitter:image" content="$image">
<script>document.documentElement.classList.add('js')</script>
<style>$critical_css</style>
<link rel="stylesheet" href="/css/open-analytics.css">
<script type="application/ld+json">
$jsonld
</script>
</head>
<body class="oa surface-light">
<a class="skip-link" href="#main">Skip to content</a>
$draft_banner$header
<main id="main" class="oa-main">
$main
</main>
$footer
$shell_scripts
$scripts
</body>
</html>
""")


def default_shell(published):
    """The site shell (header, footer, inline CSS) from scripts/render_site.py."""
    from content_model import Content
    from render_site import Renderer
    return Renderer(Content(), oa_published=published).oa_shell()


def analytics(cfg, with_count):
    if not cfg["goatcounter"]:
        return ""
    code = cfg["goatcounter"]
    count = ""
    if with_count:
        count = f"""
<script>
document.getElementById('goatcounter-script').addEventListener('load', function () {{
  var vc = document.getElementById('view-count');
  if (!vc) return;
  fetch('https://{code}.goatcounter.com/counter/' + encodeURIComponent(location.pathname) + '.json')
    .then(function (r) {{ return r.ok ? r.json() : null; }})
    .then(function (d) {{ if (d && d.count) {{ vc.textContent = ' · ' + d.count + ' views'; }} }})
    .catch(function () {{}});
}});
</script>"""
    return (f'<script id="goatcounter-script" data-goatcounter="https://{code}.goatcounter.com/count" '
            f'async src="https://gc.zgo.at/count.js"></script>{count}')


def head_common(cfg):
    shell = cfg["shell"]
    return {
        "lang": cfg["lang"], "theme": cfg["theme"], "author": cfg["author_name"],
        "feed_title": attr(cfg["feed_title"]), "feed_url": cfg["feed_url"],
        "site_name": attr(cfg["brand_name"]), "locale": cfg["locale"], "image": cfg["image_url"],
        "header": shell["header"], "footer": shell["footer"], "draft_banner": shell["draft_banner"],
        "critical_css": shell["critical_css"], "shell_scripts": shell["scripts"],
    }


def breadcrumb(cfg, extra=None):
    items = [("Home", f"{cfg['site']}/"), (cfg["title"], cfg["section_url"])]
    if extra:
        items.append(extra)
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": n, "item": u} for i, (n, u) in enumerate(items, 1)]}


def person_node(cfg):
    return {k: v for k, v in cfg["person"].items() if v}


# ------------------------------------------------------------------- articles

def build_post(post, older, newer, cfg):
    graph = [
        {
            "@type": "TechArticle",
            "@id": f"{post['url']}#article",
            "headline": post["title"],
            "description": post["description"],
            "abstract": post["summary"],
            "about": post["question"],
            "articleSection": cfg["title"],
            "keywords": ", ".join(post["tags"]),
            "url": post["url"],
            "mainEntityOfPage": post["canonical"],
            "datePublished": iso_datetime(post["date"]),
            "dateModified": iso_datetime(post["updated"]),
            "inLanguage": cfg["lang"],
            "wordCount": post["words"],
            "image": cfg["image_url"],
            "isPartOf": {"@id": f"{cfg['section_url']}#collection"},
            "author": {"@id": cfg["person"]["@id"]},
            "publisher": {"@id": cfg["person"]["@id"]},
        },
        person_node(cfg),
        breadcrumb(cfg, (post["title"], post["url"])),
    ]
    if post["data_url"]:
        graph[0]["isBasedOn"] = {"@type": "Dataset", "name": post["data"] or post["title"], "url": post["data_url"]}
    if post["repo_url"]:
        graph[0]["citation"] = post["repo_url"]

    card_rows = [("Question", esc(post["question"]))]
    if post["data"]:
        data = esc(post["data"])
        if post["data_url"]:
            data += f' (<a href="{attr(post["data_url"])}">dataset</a>)'
        card_rows.append(("Data", data))
    if post["methods"]:
        card_rows.append(("Method", esc(post["methods"])))
    if post["tools"]:
        card_rows.append(("Tools", esc(", ".join(post["tools"]))))
    if post["repo_url"]:
        card_rows.append(("Code", f'<a href="{attr(post["repo_url"])}">{esc(post["repo_url"])}</a>'))
    if post["status"]:
        card_rows.append(("Status", esc(post["status"])))
    method_card = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in card_rows)

    updated = ""
    if post["updated"] != post["date"]:
        updated = f' · Updated <time datetime="{post["updated"].isoformat()}">{display_date(post["updated"])}</time>'
    tags = "".join(f'<li><a href="{attr(cfg["path"])}?tag={attr(t)}">{esc(t)}</a></li>' for t in post["tags"])

    pager = ""
    if older or newer:
        left = (f'<a class="pager-link" href="{older["href"]}" rel="prev"><span>← Older</span>'
                f'<strong>{esc(older["title"])}</strong></a>') if older else '<span></span>'
        right = (f'<a class="pager-link next" href="{newer["href"]}" rel="next"><span>Newer →</span>'
                 f'<strong>{esc(newer["title"])}</strong></a>') if newer else '<span></span>'
        pager = f'<nav class="post-pager" aria-label="More analytics work">{left}{right}</nav>'

    consult = cfg["ctas"].get("consult", {})
    main = f"""<article class="oa-article">
  <header class="article-head">
    <p class="crumbs"><a href="/">Home</a> / <a href="{attr(cfg["path"])}">{esc(cfg["title"])}</a></p>
    <h1>{esc(post["title"])}</h1>
    <p class="article-meta"><time datetime="{post["date"].isoformat()}">{display_date(post["date"])}</time>{updated} · {post["words"] // 200 + 1} min read<span id="view-count"></span> · By <a href="/" rel="author">{esc(cfg["author_name"])}</a></p>
    <ul class="tags" aria-label="Tags">{tags}</ul>
  </header>
  <p class="lede"><span class="label">In short</span> {esc(post["summary"])}</p>
  <section class="key-findings" aria-labelledby="key-findings">
    <h2 id="key-findings">Key findings</h2>
    {post["findings_html"]}
  </section>
  <dl class="method-card" aria-label="How this analysis was done">{method_card}</dl>
  <div class="article-body">
{post["content"]}
  </div>
</article>
{pager}
<aside class="oa-cta surface-dark" aria-label="Work with me">
  <p class="label">Need this kind of analysis?</p>
  <p>I help organisations turn messy questions into evidence they can act on.</p>
  <p class="cta-row"><a class="btn" href="{attr(consult.get("href", "/#contact"))}" data-goatcounter-click="{attr(consult.get("analyticsEvent", ""))}">Discuss a business challenge</a> <a class="btn btn-ghost" href="{attr(cfg["path"])}">All analytics work</a></p>
</aside>"""

    article_meta = (f'<meta property="article:published_time" content="{iso_datetime(post["date"])}">\n'
                    f'<meta property="article:modified_time" content="{iso_datetime(post["updated"])}">\n'
                    + "".join(f'<meta property="article:tag" content="{attr(t)}">\n' for t in post["tags"]))
    return PAGE.substitute(
        head_common(cfg),
        source=f"content/{SECTION_DIR}/{post['slug']}.md",
        title=f"{esc(post['title'])} | {esc(cfg['brand_name'])}",
        og_title=attr(post["title"]),
        description=attr(post["description"]),
        robots=cfg["robots"],
        canonical=attr(post["canonical"]),
        rel_links="",
        og_type="article",
        article_meta=article_meta,
        jsonld=json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=2),
        main=main,
        scripts=analytics(cfg, with_count=True),
    )


# ---------------------------------------------------------------------- index

FILTER_SCRIPT = """<script>
// Tag filter: lists every matching piece from all pages, hides pagination, and keeps
// the tag in the URL (?tag=) so a filtered view can be shared.
(function () {
  var sel = document.getElementById('tag-filter');
  if (!sel) return;
  var list = document.querySelector('.oa-list');
  var all = document.getElementById('all-pieces').content.children;
  var note = document.getElementById('filter-note');
  var pager = document.querySelector('.index-pager');
  var pageItems = Array.prototype.slice.call(list.children);
  var section = sel.getAttribute('data-section');
  function setUrl(url) { try { history.replaceState(null, '', url); } catch (e) {} }
  function apply(tag) {
    list.textContent = '';
    if (!tag) {
      pageItems.forEach(function (li) { list.appendChild(li); });
      if (pager) pager.hidden = false;
      note.textContent = '';
      setUrl(location.pathname);
      return;
    }
    var hits = Array.prototype.filter.call(all, function (li) {
      return (li.getAttribute('data-tags') || '').split(' ').indexOf(tag) !== -1;
    });
    hits.forEach(function (li) { list.appendChild(li.cloneNode(true)); });
    if (pager) pager.hidden = true;
    note.textContent = hits.length + (hits.length === 1 ? ' piece' : ' pieces') + ' tagged ' + tag;
    setUrl(section + '?tag=' + encodeURIComponent(tag));
  }
  sel.addEventListener('change', function () { apply(sel.value); });
  var wanted = new URLSearchParams(location.search).get('tag');
  if (wanted && Array.prototype.some.call(sel.options, function (o) { return o.value === wanted; })) {
    sel.value = wanted;
    apply(wanted);
  }
})();
</script>"""


def card(p, cfg):
    tags = " ".join(p["tags"])
    return f"""  <li data-tags="{attr(tags)}">
    <article class="oa-card">
      <p class="card-meta"><time datetime="{p['date'].isoformat()}">{display_date(p['date'])}</time> · {esc(', '.join(p['tags']))}</p>
      <h2><a href="{p['href']}">{esc(p['title'])}</a></h2>
      <p class="card-question">{esc(p['question'])}</p>
      <p>{esc(truncate(p['summary']))}</p>
    </article>
  </li>
"""


def index_pager(cfg, n, total):
    if total == 1:
        return ""
    prev = (f'<a class="pager-btn" href="{page_path(cfg, n - 1)}" rel="prev">← Newer</a>' if n > 1 else "<span></span>")
    nxt = (f'<a class="pager-btn" href="{page_path(cfg, n + 1)}" rel="next">Older →</a>' if n < total else "<span></span>")
    nums = "".join(
        f'<span class="pager-page" aria-current="page">{i}</span>' if i == n
        else f'<a class="pager-page" href="{page_path(cfg, i)}">{i}</a>' for i in range(1, total + 1))
    return f'<nav class="index-pager" aria-label="Pagination">{prev}<span class="pager-pages">{nums}</span>{nxt}</nav>'


def build_index(chunk, newest_first, n, total, cfg):
    url = cfg["site"] + page_path(cfg, n)
    used = sorted({t for p in newest_first for t in p["tags"]})
    options = "".join(f'<option value="{attr(t)}">{esc(t)}</option>' for t in used)
    graph = [
        {
            "@type": "CollectionPage",
            "@id": f"{cfg['section_url']}#collection",
            "url": cfg["section_url"],
            "name": cfg["title"],
            "description": cfg["description"],
            "inLanguage": cfg["lang"],
            "isPartOf": {"@id": cfg["website_id"]},
            "author": {"@id": cfg["person"]["@id"]},
            "mainEntity": {"@type": "ItemList", "itemListElement": [
                {"@type": "ListItem", "position": i, "url": p["url"], "name": p["title"]}
                for i, p in enumerate(newest_first, 1)]},
        },
        person_node(cfg),
        breadcrumb(cfg),
    ]
    rel = ""
    if n > 1:
        rel += f'<link rel="prev" href="{cfg["site"] + page_path(cfg, n - 1)}">\n'
    if n < total:
        rel += f'<link rel="next" href="{cfg["site"] + page_path(cfg, n + 1)}">\n'
    title = cfg["title"] if n == 1 else f"{cfg['title']}, page {n}"
    main = f"""<header class="index-head">
  <p class="crumbs"><a href="/">Home</a> / {esc(cfg["title"])}</p>
  <h1>{esc(cfg["title"])}</h1>
  <p class="index-intro">{esc(cfg["intro"])}</p>
  <div class="tag-filter-row">
    <label for="tag-filter">Filter by tag</label>
    <select id="tag-filter" data-section="{attr(cfg["path"])}"><option value="">All pieces</option>{options}</select>
  </div>
  <p class="filter-note" id="filter-note" role="status" aria-live="polite"></p>
</header>
<ul class="oa-list">
{"".join(card(p, cfg) for p in chunk)}</ul>
<template id="all-pieces">
{"".join(card(p, cfg) for p in newest_first)}</template>
{index_pager(cfg, n, total)}"""
    return PAGE.substitute(
        head_common(cfg),
        source=f"content/{SECTION_DIR}/*.md",
        title=f"{esc(title)} | {esc(cfg['brand_name'])}",
        og_title=attr(title),
        description=attr(cfg["description"] if n == 1 else f"Page {n} of {cfg['title']} by {cfg['author_name']}."),
        robots=cfg["robots"],
        canonical=url,
        rel_links=rel,
        og_type="website",
        article_meta="",
        jsonld=json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=2),
        main=main,
        scripts=FILTER_SCRIPT + "\n" + analytics(cfg, with_count=False),
    )


# ----------------------------------------------------------------------- feed

def build_feed(posts, cfg):
    def rfc822(d):
        return format_datetime(datetime(d.year, d.month, d.day, tzinfo=timezone.utc))

    def absolute(content, base):
        return re.sub(r'(href|src)="([^"]+)"', lambda m: f'{m.group(1)}="{urljoin(base, m.group(2))}"', content)

    items = []
    for p in list(reversed(posts))[:20]:
        body = (f"<p><strong>In short:</strong> {esc(p['summary'])}</p><h2>Key findings</h2>"
                f"{p['findings_html']}{p['content']}")
        cats = "".join(f"      <category>{esc(t)}</category>\n" for t in p["tags"])
        items.append(
            "    <item>\n"
            f"      <title>{esc(p['title'])}</title>\n"
            f"      <link>{p['url']}</link>\n"
            f'      <guid isPermaLink="true">{p["url"]}</guid>\n'
            f"      <pubDate>{rfc822(p['date'])}</pubDate>\n"
            f"      <description>{esc(p['description'])}</description>\n"
            f"      <content:encoded>{esc(absolute(body, p['url']))}</content:encoded>\n"
            f"{cats}"
            "    </item>\n")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" '
        'xmlns:content="http://purl.org/rss/1.0/modules/content/">\n'
        "  <channel>\n"
        f"    <title>{esc(cfg['feed_title'])}</title>\n"
        f"    <link>{cfg['section_url']}</link>\n"
        f"    <description>{esc(cfg['description'])}</description>\n"
        f"    <language>{cfg['lang']}</language>\n"
        f"    <lastBuildDate>{rfc822(max(p['updated'] for p in posts))}</lastBuildDate>\n"
        f'    <atom:link href="{cfg["feed_url"]}" rel="self" type="application/rss+xml"/>\n'
        + "".join(items)
        + "  </channel>\n</rss>\n")


# ---------------------------------------------------------------------- build

def build(out=DEFAULT_OUT, src=DEFAULT_SRC, today=None, draft=True, shell=None):
    """shell: callable(published: bool) -> shell dict (render_site.Renderer.oa_shell).
    Write the section into out/open-analytics/. Returns sitemap rows
    [(absolute_url, lastmod_iso)]; an empty list means the section is not published.
    Draft builds (the default) mark every page noindex; scripts/build.py --release passes draft=False."""
    cfg = load_config()
    cfg["robots"] = "noindex, nofollow" if draft else "index, follow, max-image-preview:large, max-snippet:-1"
    today = today or date.today()
    target = Path(out) / SECTION_DIR
    if target.exists():
        shutil.rmtree(target)  # fully generated; stale pages must not survive
    posts = load_posts(Path(src), cfg, today)
    cfg["shell"] = (shell or default_shell)(bool(posts))
    if not posts:
        PUBLISHED.clear()
        print("  note   Open Analytics Work: no published pieces; section not built "
              "(the homepage must not link to it).")
        return []
    for i, post in enumerate(posts):
        older = posts[i - 1] if i > 0 else None
        newer = posts[i + 1] if i + 1 < len(posts) else None
        dest = target / post["slug"] / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(build_post(post, older, newer, cfg), encoding="utf-8")
        print(f"  built  {dest.relative_to(out)}  ({post['words']} words)")
    newest_first = list(reversed(posts))
    per = cfg["per_page"]
    chunks = [newest_first[i:i + per] for i in range(0, len(newest_first), per)]
    for n, chunk in enumerate(chunks, 1):
        dest = Path(out) / page_path(cfg, n).lstrip("/") / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(build_index(chunk, newest_first, n, len(chunks), cfg), encoding="utf-8")
        print(f"  built  {dest.relative_to(out)}")
    (target / "feed.xml").write_text(build_feed(posts, cfg), encoding="utf-8")
    print(f"  built  {SECTION_DIR}/feed.xml")
    PUBLISHED[:] = [(p["url"], p["title"]) for p in newest_first if not p["external_canonical"]]
    newest = max(p["updated"] for p in posts).isoformat()
    rows = [(cfg["site"] + page_path(cfg, n), newest) for n in range(1, len(chunks) + 1)]
    rows += [(p["url"], p["updated"].isoformat()) for p in newest_first if not p["external_canonical"]]
    print(f"OK: Open Analytics Work: {len(posts)} piece(s), {len(chunks)} index page(s).")
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the Open Analytics Work section.")
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC, help="folder of .md sources")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="site output folder (default: dist/)")
    args = ap.parse_args(argv)
    try:
        args.out.mkdir(parents=True, exist_ok=True)
        if STATIC.exists():  # standalone runs need the stylesheets; build.py does this for the full site
            shutil.copytree(STATIC, args.out, dirs_exist_ok=True)
        build(out=args.out, src=args.src)
    except BuildError as e:
        sys.exit(f"ERROR: {e}")


if __name__ == "__main__":
    main()
