"""Post-build checks on dist/.

Returns (errors, warnings). Some checks are warnings in draft builds and errors in
release builds, as noted below.
"""

import gzip
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote

FORBIDDEN_DIRS = {"content", "scripts", "templates", ".claude", ".github"}
FORBIDDEN_FILES = {"", "settings.json"}
BANNED = [(re.compile(r"\bTODO\b"), "TODO"), (re.compile(r"\bTBC\b"), "TBC"),
          (re.compile(r"lorem ipsum", re.I), "lorem ipsum"), (re.compile(r"\bXXX\b"), "XXX"),
          (re.compile(r"\bexample\.(com|org)\b"), "example.com/.org")]
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)*\.[a-z]{2,}", re.I)
TEXT_TYPES = {".html", ".xml", ".txt", ".css", ".js", ".json", ".svg"}

# ui-ux-guide §10 (bytes). HTML/CSS/JS gzip; fonts as shipped.
BUDGETS = {"html_gz": 60_000, "css_gz": 40_000, "js_gz": 50_000, "fonts": 120_000, "critical_css": 14_000}


class _Scan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.h1 = 0
        self.urls = []      # (attr, value)
        self.jsonld = []
        self._in_ld = False
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "h1":
            self.h1 += 1
        for key in ("href", "src"):
            if a.get(key):
                self.urls.append((key, a[key]))
        if tag == "meta" and a.get("property") in ("og:image", "og:url") and a.get("content"):
            self.urls.append(("content", a["content"]))
        if tag == "script" and a.get("type") == "application/ld+json":
            self._in_ld, self._buf = True, []

    def handle_data(self, data):
        if self._in_ld:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._in_ld:
            self.jsonld.append("".join(self._buf))
            self._in_ld = False


def _gz(data):
    return len(gzip.compress(data, 9))


def _target(dist, page, url, site):
    """Map a link to the file it should resolve to in dist/, or None if external."""
    if url.startswith(site):
        url = url[len(site):] or "/"
    parts = urlsplit(url)
    if parts.scheme or url.startswith(("//", "mailto:", "tel:", "data:", "#")) or not parts.path:
        return None
    path = unquote(parts.path)
    target = (dist / path.lstrip("/")) if path.startswith("/") else (page.parent / path)
    if path.endswith("/") or target.is_dir():
        target = target / "index.html"
    return target


def run(dist, content, release, critical_css_bytes=0):
    dist = Path(dist)
    site = content.site["url"].rstrip("/")
    allowed_emails = {e for e in [content["sections/08-contact"].get("general", {}).get("email")] if e}
    errors, warnings = [], []

    def budget(msg):
        (errors if release else warnings).append(msg)

    # Forbidden paths: internal files must never be deployed.
    for p in dist.rglob("*"):
        rel = p.relative_to(dist)
        if set(rel.parts) & FORBIDDEN_DIRS or rel.name in FORBIDDEN_FILES:
            errors.append(f"dist/{rel}: internal file must not be published")

    # Homepage: exactly one H1.
    home = dist / "index.html"
    if not home.exists():
        errors.append("dist/index.html missing")

    for page in sorted(dist.rglob("*.html")):
        rel = page.relative_to(dist)
        text = page.read_text(encoding="utf-8")
        scan = _Scan()
        scan.feed(text)
        if page == home and scan.h1 != 1:
            errors.append(f"dist/{rel}: homepage needs exactly one <h1> (found {scan.h1})")
        for i, block in enumerate(scan.jsonld):
            try:
                json.loads(block)
            except json.JSONDecodeError as e:
                errors.append(f"dist/{rel}: JSON-LD block {i + 1} does not parse ({e})")
        for key, url in scan.urls:
            target = _target(dist, page, url, site)
            if target is not None and not target.exists():
                errors.append(f"dist/{rel}: broken internal link {key}=\"{url}\"")
        if _gz(text.encode()) > BUDGETS["html_gz"]:
            budget(f"dist/{rel}: HTML over {BUDGETS['html_gz'] // 1000} KB gzip")

    # Banned strings and unconfirmed emails.
    for f in sorted(dist.rglob("*")):
        if f.suffix not in TEXT_TYPES or f.name == "LICENSE.txt":
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        rel = f.relative_to(dist)
        for rx, label in BANNED:
            if rx.search(text):
                budget(f"dist/{rel}: contains banned text '{label}'")
        for m in EMAIL.finditer(text):
            if m.group(0) not in allowed_emails and not m.group(0).endswith((".woff2", ".png", ".jpg")):
                budget(f"dist/{rel}: unconfirmed email '{m.group(0)}'")

    # Budgets (ui-ux-guide §10).
    css = sum(_gz(p.read_bytes()) for p in dist.rglob("*.css"))
    js = sum(_gz(p.read_bytes()) for p in dist.rglob("*.js"))
    fonts = sum(p.stat().st_size for p in dist.rglob("*.woff2"))
    for label, value, limit in (("CSS (gzip)", css, BUDGETS["css_gz"]), ("JS (gzip)", js, BUDGETS["js_gz"]),
                                ("Fonts", fonts, BUDGETS["fonts"]),
                                ("Inlined critical CSS (gzip)", critical_css_bytes, BUDGETS["critical_css"])):
        if value > limit:
            budget(f"{label}: {value:,} bytes, over budget {limit:,}")
    # Entity consistency: the same name and descriptors everywhere.
    person = content.person
    if home.exists():
        page = home.read_text(encoding="utf-8")
        for needle in [person["brandName"]] + [d.rstrip(".") for d in person["descriptors"]]:
            if needle.lower() not in page.lower():
                errors.append(f"dist/index.html: entity string '{needle}' (person.json) not visible")
        scan = _Scan()
        scan.feed(page)
        names = set()
        for block in scan.jsonld:
            try:
                for node in json.loads(block).get("@graph", []):
                    if node.get("@type") == "Person" and node.get("@id") == person["id"]:
                        names.add(node.get("name"))
            except (json.JSONDecodeError, AttributeError):
                pass
        if names != {person["name"]}:
            errors.append(f"dist/index.html: JSON-LD Person name {names or 'missing'} ≠ '{person['name']}'")
    llms = dist / "llms.txt"
    if llms.exists() and person["name"] not in llms.read_text(encoding="utf-8"):
        errors.append("dist/llms.txt: person name missing")

    stats = {"css_gz": css, "js_gz": js, "fonts": fonts, "critical_css": critical_css_bytes,
             "home_html_gz": _gz(home.read_bytes()) if home.exists() else 0}
    return errors, warnings, stats
