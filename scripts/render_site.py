"""Render site pages from content objects into HTML.

Templates in templates/ hold structure only; every string shown to a visitor comes from
content/. Section bodies live in render_sections.py; structured data in discovery.py.
"""

import html
import re
import mimetypes
from datetime import date
from pathlib import Path
from string import Template

import discovery
from render_sections import Sections

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
CRITICAL_CSS = ("css/fonts.css", "css/tokens.css", "css/base.css", "css/sections.css")
MODULES = ("/js/site.js", "/js/audience.js", "/js/forms.js", "/js/motion.js")

# Section surfaces (ui-ux-guide §3). 03 is provisional until design review 1.
SURFACES = {"about": "surface-light", "bring": "surface-dark", "standing": "surface-light",
            "building": "surface-dark", "exploring": "surface-light", "writing": "surface-dark",
            "contact": "surface-dark"}


def esc(s):
    return html.escape(str(s), quote=False)


def attr(s):
    return html.escape(str(s), quote=True)


def tpl(name):
    return Template((TEMPLATES / name).read_text(encoding="utf-8"))


def minify_css(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{}:;,>])\s*", r"\1", css)
    return css.replace(";}", "}").strip()


class Renderer:
    def __init__(self, content, release=False, oa_published=False, today=None, lastmod=None):
        self.c = content
        self.site = content.site
        self.person = content.person
        self.release = release
        self.oa_published = oa_published
        self.today = today or date.today()
        self.lastmod = lastmod or self.today.isoformat()
        self.base_url = self.site["url"].rstrip("/")
        self._css = minify_css("\n".join((STATIC / p).read_text(encoding="utf-8") for p in CRITICAL_CSS))
        self.sections = Sections(self)

    # ------------------------------------------------------------------ shell
    def social_meta(self, title, description, url, og_type="website"):
        og = self.site.get("ogImage", {})
        if (STATIC / og.get("path", "/none").lstrip("/")).exists():
            image, alt, card = self.base_url + og["path"], og.get("alt", ""), "summary_large_image"
            dims = (f'<meta property="og:image:secure_url" content="{attr(self.base_url + og["path"])}">\n'
                    f'<meta property="og:image:type" content="{mimetypes.guess_type(og["path"])[0] or "image/jpeg"}">\n'
                    f'<meta property="og:image:width" content="{og["width"]}">\n'
                    f'<meta property="og:image:height" content="{og["height"]}">\n')
        else:
            img = self.person.get("image", {})
            image, alt, card, dims = self.base_url + img.get("path", ""), img.get("alt", ""), "summary", ""
        return (
            f'<meta property="og:type" content="{og_type}">\n'
            f'<meta property="og:title" content="{attr(title)}">\n'
            f'<meta property="og:description" content="{attr(description)}">\n'
            f'<meta property="og:url" content="{attr(url)}">\n'
            f'<meta property="og:site_name" content="{attr(self.site["name"])}">\n'
            f'<meta property="og:locale" content="{attr(self.site["locale"])}">\n'
            f'<meta property="og:image" content="{attr(image)}">\n{dims}'
            f'<meta property="og:image:alt" content="{attr(alt)}">\n'
            f'<meta name="twitter:card" content="{card}">\n'
            f'<meta name="twitter:title" content="{attr(title)}">\n'
            f'<meta name="twitter:description" content="{attr(description)}">\n'
            f'<meta name="twitter:image" content="{attr(image)}">'
        )

    def robots(self, indexable=True):
        if not self.release or not indexable:
            return "noindex, nofollow"
        return "index, follow, max-image-preview:large, max-snippet:-1"

    def analytics_tags(self):
        code = (self.site.get("analytics", {}).get("goatcounter") or {}).get("code")
        if not code:
            return ""
        return (f'<script data-goatcounter="https://{attr(code)}.goatcounter.com/count" async '
                f'src="https://gc.zgo.at/count.js"></script>')

    def head_extra(self, jsonld=None, home=False):
        out = []
        if home:
            v = self.site.get("verification") or {}
            if v.get("google"):
                out.append(f'<meta name="google-site-verification" content="{attr(v["google"])}">')
            if v.get("bing"):
                out.append(f'<meta name="msvalidate.01" content="{attr(v["bing"])}">')
        if jsonld:
            out.append(f'<script type="application/ld+json">\n{jsonld}\n</script>')
        out += [f'<link rel="modulepreload" href="{m}">' for m in MODULES[1:]]
        return "\n".join(out)

    def scripts(self):
        mods = "\n".join(f'<script type="module" src="{m}"></script>' for m in MODULES)
        return mods + ("\n" + self.analytics_tags() if self.analytics_tags() else "")

    def draft_banner(self):
        if self.release:
            return ""
        return ('<p class="draft-banner" role="note">Draft build: content not yet verified. '
                'Not for publication.</p>\n')

    def cta_links(self, kind):
        out = []
        for c in self.site["ctas"].values():
            event = attr(c.get("analyticsEvent", ""))
            data = f'data-audience-set="all" data-value="{attr(c["audience"])}" data-goatcounter-click="{event}"'
            if kind == "compact":
                out.append(f'<a class="btn{"" if c["audience"] == "business" else " btn-ghost"}" href="{attr(c["href"])}" '
                           f'{data}>{esc(c["label"])}<span class="visually-hidden">: {esc(c["sublabel"])}</span></a>')
            else:
                cls = "cta cta-primary" if c["audience"] == "business" else "cta"
                out.append(f'<a class="{cls}" href="{attr(c["href"])}" {data}>'
                           f'<span class="cta-label">{esc(c["label"])}</span>'
                           f'<span class="cta-sub">{esc(c["sublabel"])}</span></a>')
        return "".join(out)

    def header(self, on_home):
        items = []
        for n in self.site["nav"]:
            href = n["href"][1:] if on_home and n["href"].startswith("/#") else n["href"]
            items.append(f'<li><a href="{attr(href)}">{esc(n["label"])}</a></li>')
        return tpl("header.html").substitute(
            home_href="#home" if on_home else "/",
            brand=esc(self.person["name"]),
            nav_items="".join(items),
            ctas=self.cta_links("compact"),
        )

    def footer(self):
        links = [f'<li><a href="{attr(s["url"])}">{esc(s["label"])}</a></li>' for s in self.person.get("sameAs", [])]
        oa = self.site["sections"]["openAnalytics"]
        if self.oa_published:
            links.insert(0, f'<li><a href="{attr(oa["path"])}">{esc(oa["title"])}</a></li>')
        legal = esc(self.site.get("footer", {}).get("legal", "").replace("{year}", str(self.today.year)))
        privacy = self.c["sections/08-contact"].get("privacyNotice", {})
        if privacy.get("status") not in ("missing", None):
            legal += f' · <a href="{attr(privacy["href"])}">{esc(self.c["pages/privacy"]["title"])}</a>'
        return tpl("footer.html").substitute(
            name=esc(self.person["name"]),
            descriptors=esc(" · ".join(d.rstrip(".") for d in self.person["descriptors"])),
            links="".join(links),
            legal=legal,
        )

    def page(self, *, title, description, path, main, body_class, on_home=False, indexable=True, jsonld=None):
        url = self.base_url + path
        return tpl("base.html").substitute(
            lang=self.site["language"],
            title=esc(title),
            description=attr(description),
            author=attr(self.person["name"]),
            robots=self.robots(indexable),
            theme=attr(self.site.get("themeColor", "")),
            canonical=attr(url),
            social_meta=self.social_meta(title, description, url),
            critical_css=self._css,
            head_extra=self.head_extra(jsonld, home=on_home),
            body_class=body_class,
            draft_banner=self.draft_banner(),
            header=self.header(on_home),
            main=main,
            footer=self.footer(),
            scripts=self.scripts(),
        )

    # ----------------------------------------------------------------- pages
    def section(self, s, body=""):
        label = next((n["label"] for n in self.site["nav"] if n["id"] == s["id"]), "")
        return tpl("sections/section.html").substitute(
            id=attr(s["id"]),
            surface=SURFACES.get(s["id"], "surface-dark"),
            number=esc(s["number"]),
            label=esc(label),
            heading=esc(s["heading"]),
            body=body,
        )

    def home(self):
        main = "\n".join(self.sections.render(s) for s in self.c.sections())
        jsonld = discovery.home_graph(self.c, self.sections.faq_items(), self.lastmod)
        return self.page(title=self.site["title"], description=self.site["description"], path="/",
                         main=main, body_class="home", on_home=True, jsonld=jsonld)

    def privacy(self):
        pg = self.c["pages/privacy"]
        url = self.base_url + pg["path"]
        jsonld = discovery.page_graph(self.c, url, pg["title"], [("Home", self.base_url + "/"), (pg["title"], url)])
        return self.page(title=f'{pg["title"]} | {self.site["name"]}', description=pg["intro"], path=pg["path"],
                         main=self.sections.privacy_page(), body_class="page-legal surface-light", jsonld=jsonld)

    def not_found(self):
        nf = self.site["pages"]["notFound"]
        links = "".join(
            f'<li><a class="btn{" btn-ghost" if i else ""}" href="{attr(l["href"])}">{esc(l["label"])}</a></li>'
            for i, l in enumerate(nf["links"]))
        main = tpl("not-found.html").substitute(heading=esc(nf["heading"]), body=esc(nf["body"]), links=links)
        return self.page(title=f'{nf["title"]} | {self.site["name"]}', description=nf["body"],
                         path="/404.html", main=main, body_class="page-404", indexable=False)

    def oa_shell(self):
        """Shared shell for Open Analytics Work pages."""
        return {
            "header": self.header(on_home=False),
            "footer": self.footer(),
            "draft_banner": self.draft_banner(),
            "critical_css": self._css,
            "scripts": '<script type="module" src="/js/site.js"></script>',
            "analytics": self.analytics_tags(),
            "robots": self.robots(),
        }

    def critical_css_bytes(self):
        """Gzipped size of the inlined CSS: the 14 KB first-round-trip budget."""
        import gzip
        return len(gzip.compress(self._css.encode("utf-8"), 9))
