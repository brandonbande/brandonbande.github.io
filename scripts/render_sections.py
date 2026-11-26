"""Homepage section bodies and secondary pages.

Structure only: every visible string comes from content/ (section objects, person,
evidence, faq, ui). In draft builds, owed facts (null value + sibling `<key>Note`)
render as visible "Pending" notes; release builds never reach that state because
the integrity gate refuses them first.
"""

import html
import json
from datetime import date
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "assets-src" / "images.json"


def esc(s):
    return html.escape(str(s), quote=False)


def attr(s):
    return html.escape(str(s), quote=True)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")


def wrap_words(text, limit):
    lines, line = [], ""
    for word in str(text).split():
        if line and len(line) + 1 + len(word) > limit:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return lines + ([line] if line else [])


class Sections:
    def __init__(self, renderer):
        self.r = renderer
        self.c = renderer.c
        self.ui = self.c["ui"]
        self.release = renderer.release
        self.today = renderer.today
        self.manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}

    # ------------------------------------------------------------------ helpers
    def pending(self, note, inline=False):
        if self.release or not note:
            return ""
        tag = "span" if inline else "p"
        return f'<{tag} class="pending" data-pending>Pending: {esc(note)}</{tag}>'

    def value(self, obj, key, inline=False):
        """Escaped value, or a draft-only pending note when the value is owed."""
        if obj.get(key):
            return esc(obj[key])
        return self.pending(obj.get(f"{key}Note"), inline)

    def badge(self, key, kind="state"):
        label = self.ui["badges"].get(key, key)
        return f'<span class="badge badge-{attr(slug(key))}" data-kind="{kind}">{esc(label)}</span>'

    def picture(self, alt, sizes, cls="", priority=False):
        p = self.manifest.get("portrait")
        if not p:
            return self.pending("Portrait variants missing: run python3 scripts/images.py")
        largest = p["variants"][-1]
        srcsets = {fmt: ", ".join(f'{p["base"]}-{v["width"]}.{fmt} {v["width"]}w' for v in p["variants"])
                   for fmt in p["formats"]}
        fallback = f'{p["base"]}-{largest["width"]}.jpg'
        load = 'fetchpriority="high" decoding="async"' if priority else 'loading="lazy" decoding="async"'
        return (f'<picture class="{cls}"><source type="image/webp" srcset="{srcsets["webp"]}" sizes="{sizes}">'
                f'<img src="{fallback}" srcset="{srcsets["jpg"]}" sizes="{sizes}" width="{largest["width"]}" '
                f'height="{largest["height"]}" alt="{attr(alt)}" {load}></picture>')

    def tabs(self, group, label, items):
        """Tab buttons (hidden until audience.js enhances them; ). items: [(value, text)]"""
        btns = "".join(
            f'<button type="button" class="tab" id="{group}-tab-{v}" data-tab="{group}" data-value="{v}" '
            f'aria-controls="{group}-panel-{v}">{esc(t)}<span class="tab-nudge" aria-hidden="true">'
            f'{esc(self.ui["toggleNudge"])}</span></button>' for v, t in items)
        return f'<div class="tabs" data-tabs="{group}" aria-label="{attr(label)}" hidden>{btns}</div>'

    def panel(self, group, value, inner, extra_cls=""):
        return (f'<div class="panel {extra_cls}" id="{group}-panel-{value}" data-panel="{group}" '
                f'data-value="{value}">{inner}</div>')

    def link_list(self, items, cls="link-list"):
        return f'<ul class="{cls}">' + "".join(f"<li>{i}</li>" for i in items) + "</ul>" if items else ""

    # --------------------------------------------------------------------- hero
    def hero(self, s):
        person = self.c.person
        loc = s.get("locationLine", {})
        location = f'<p class="hero-location mono">{esc(loc["text"])}</p>' if loc.get("text") else ""
        portrait = self.picture(person["image"]["alt"], "(min-width: 64rem) 40vw, 100vw", "hero-portrait-img",
                                priority=True)
        identities = "".join(f"<li>{esc(i)}</li>" for i in s["identities"])
        return f"""<section id="{attr(s["id"])}" class="hero surface-dark" aria-labelledby="{attr(s["id"])}-title">
  <canvas class="hero-network" data-network aria-hidden="true"></canvas>
  <div class="wrap hero-grid">
    <div class="hero-copy">
      <p class="section-label"><span class="num">{esc(s["number"])}</span></p>
      <h1 id="{attr(s["id"])}-title" class="display">{esc(s["h1"])}</h1>
      <ul class="identities" data-identities>{identities}</ul>
      <p class="lead hero-statement">{esc(s["statement"])}</p>
      {location}
      <div class="cta-pair">{self.r.cta_links("full")}</div>
    </div>
    <figure class="hero-portrait">{portrait}</figure>
  </div>
</section>"""

    # -------------------------------------------------------------------- about
    def about(self, s):
        tabs = self.tabs("about", s["toggleLabel"], [(p["audience"], p["tabLabel"]) for p in s["profiles"]])
        panels = []
        for p in s["profiles"]:
            paras = "".join(f"<p>{esc(t)}</p>" for t in p["paragraphs"])
            focus = "".join(f"<li>{esc(f)}</li>" for f in p["focusAreas"])
            link = p["link"]
            inner = f"""<p class="kicker">{esc(p["tabLabel"])}</p>
<h3 class="panel-headline">{esc(p["headline"])}</h3>
<div class="about-grid">
  <div class="prose">{paras}</div>
  <div><ul class="focus-list">{focus}</ul>
  <p><a class="arrow-link" href="{attr(link["href"])}" data-audience-set="bring" data-value="{p["audience"]}">{esc(link["label"])}</a></p></div>
</div>"""
            panels.append(self.panel("about", p["audience"], inner))
        return self.r.section(s, tabs + f'<div class="panels" data-panels="about">{"".join(panels)}</div>')

    # -------------------------------------------------------------------- bring
    def bring(self, s):
        ui = self.ui["bring"]
        tabs = self.tabs("bring", s["toggleLabel"], [(o["id"], o["tabLabel"]) for o in s["offerings"]])
        panels = []
        for o in s["offerings"]:
            head = f'<h3 class="panel-headline">{esc(o["headline"])}</h3><p class="lead">{esc(o["intro"])}</p>'
            body = ""
            if o.get("services"):
                rows = []
                for i, svc in enumerate(o["services"], 1):
                    scope = "".join(f"<li>{esc(x)}</li>" for x in svc["scope"])
                    rows.append(f"""<li class="service">
  <span class="service-num mono">{i:02d}</span>
  <div><h4>{esc(svc["name"])}</h4><p>{esc(svc["summary"])}</p>
  <details><summary>{esc(ui["scope"])}</summary><ul class="scope-list">{scope}</ul></details></div>
</li>""")
                body += f'<ol class="services">{"".join(rows)}</ol>'
            if o.get("stats"):
                stats = []
                for st in o["stats"]:
                    definition = (f'<p class="stat-def">{esc(st["definition"])}</p>' if st.get("definition")
                                  else self.pending("Definition of this statistic") if "definition" in st else "")
                    stats.append(f'<div class="stat"><p class="stat-value" data-count>{esc(st["value"])}</p>'
                                 f'<p class="stat-label">{esc(st["label"])}</p>{definition}'
                                 f'{self.pending(st.get("note")) if st.get("status") == "draft" else ""}</div>')
                body += (f'<h4 class="mono-heading">{esc(ui["reach"])}</h4>'
                         f'<div class="stats">{"".join(stats)}</div>')
                if o.get("emphasis"):
                    body += '<p class="triad">' + "".join(f"<span>{esc(e)}</span>" for e in o["emphasis"]) + "</p>"
                body += '<div class="two-lists">'
                body += (f'<div><h4 class="mono-heading">{esc(ui["themes"])}</h4>'
                         f'<ul class="tick-list">{"".join(f"<li>{esc(t)}</li>" for t in o["themes"])}</ul></div>')
                body += (f'<div><h4 class="mono-heading">{esc(ui["formats"])}</h4>'
                         f'<ul class="tick-list">{"".join(f"<li>{esc(t)}</li>" for t in o["formats"])}</ul></div>')
                body += "</div>"
            cta = o["cta"]
            body += (f'<p class="panel-cta"><a class="btn btn-large" href="{attr(cta["href"])}" '
                     f'data-audience-set="contact" data-value="{o["id"]}" '
                     f'data-goatcounter-click="{attr(cta.get("analyticsEvent", ""))}">{esc(cta["label"])}</a></p>')
            panels.append(self.panel("bring", o["id"], head + body))
        return self.r.section(s, tabs + f'<div class="panels panels-swap" data-panels="bring">{"".join(panels)}</div>')

    # ----------------------------------------------------------------- standing
    def affiliation_dates(self, a):
        if not a.get("start"):
            return ""
        end = a.get("end")
        if end and int(str(end)[:4]) < self.today.year:
            return f'{esc(a["start"])}–{esc(end)}'
        return f'{esc(a["start"])}–{self.badge("now", "time")}'

    def timeline_date(self, item):
        ref = item.get("evidenceRef", "")
        if ref.startswith("person.affiliations["):
            try:
                return self.affiliation_dates(self.c.resolve(ref))
            except KeyError:
                pass
        if item.get("dateDisplay"):
            return esc(item["dateDisplay"])
        return esc(item["date"]) if item.get("date") else ""

    def evidence_items(self, block):
        ref = block["itemsRef"]
        items = self.c.resolve(ref) if ref else []
        out = []
        for it in items:
            if block.get("filter") == "featured" and not it.get("featured"):
                continue
            if block["id"] == "community":
                text = f'{esc(it["role"])}, {esc(it["organisation"])}'
                dates = self.affiliation_dates(it)
                out.append(text + (f' <span class="meta">{dates}</span>' if dates else ""))
            elif block["id"] == "talks":
                country = self.ui.get("countries", {}).get(it.get("country"), it.get("country"))
                where = ", ".join(x for x in (it.get("city"), country) if x)
                when = date.fromisoformat(it["date"]).strftime("%b %Y") if it.get("date") else None
                label = esc(it.get("talkTitle") or it["name"])
                link = f'<a href="{attr(it["evidenceUrl"])}">{label}</a>' if it.get("evidenceUrl") else label
                meta = " · ".join(esc(x) for x in (it.get("name") if it.get("talkTitle") else None, when,
                                                   where, (it.get("role") or "").capitalize()) if x)
                out.append(f'{link} <span class="meta">{meta}</span>')
            elif block["id"] == "ba-contributions":
                if it.get("shareable") is True:
                    out.append(f'<strong>{esc(it["title"])}</strong> <span class="meta">{esc(it.get("period", ""))}</span>'
                               f'<br>{esc(it.get("summary", ""))}')
            else:  # publications, certifications, recognitions
                name = esc(it.get("title") or it.get("name"))
                url = it.get("url") or it.get("credentialUrl")
                meta = " · ".join(esc(x) for x in (it.get("venue") or it.get("issuer"), it.get("date")) if x)
                out.append((f'<a href="{attr(url)}">{name}</a>' if url else name) + f' <span class="meta">{meta}</span>')
        if block["id"] == "writing" and self.r.oa_published:
            oa = self.c.site["sections"]["openAnalytics"]
            out.append(f'<a href="{attr(oa["path"])}">{esc(self.ui["standing"]["openAnalyticsLink"])}</a>')
        return out

    def standing(self, s):
        ui = self.ui["standing"]
        bio = "".join(f"<p>{esc(p)}</p>" for p in self.c.resolve(s["bioRef"]))
        rows = []
        for item in s["timeline"]:
            date = self.timeline_date(item)
            rows.append(f'<li><span class="tl-date mono">{date}</span><span class="tl-label">{esc(item["label"])}</span></li>')
        blocks = []
        for block in s["evidenceBlocks"]:
            items = self.evidence_items(block)
            if items:
                blocks.append(f'<div class="evidence-block"><h4 class="mono-heading">{esc(block["title"])}</h4>'
                              f'{self.link_list(items, "evidence-list")}</div>')
            elif block.get("renderIfEmpty", True):
                blocks.append(f'<div class="evidence-block is-empty"><h4 class="mono-heading">{esc(block["title"])}</h4>'
                              f'{self.pending("No entries yet in " + block["itemsRef"])}</div>') if not self.release else None
        body = f"""<div class="standing-grid">
  <div class="prose bio" data-reveal><h3 class="visually-hidden">{esc(ui["biography"])}</h3>{bio}</div>
  <div data-reveal><h3 class="mono-heading">{esc(ui["timeline"])}</h3><ol class="timeline">{"".join(rows)}</ol></div>
</div>
<h3 class="mono-heading evidence-heading">{esc(ui["evidence"])}</h3>
<div class="evidence-grid" data-reveal>{"".join(b for b in blocks if b)}</div>"""
        return self.r.section(s, body)

    # ----------------------------------------------------------------- building
    def building(self, s):
        ui = self.ui["building"]
        prod = s["product"]
        one_line = self.value(prod, "oneLine")
        one_line = f'<p class="lead">{one_line}</p>' if prod.get("oneLine") else one_line
        stages = []
        for i, st in enumerate(s["stages"], 1):
            body = self.value(st, "body")
            body = f"<p>{body}</p>" if st.get("body") else body
            extra = ""
            if st.get("steps"):
                extra += (f'<h4 class="mono-heading">{esc(ui["steps"])}</h4><ol class="steps">'
                          + "".join(f'<li><span class="step-num mono">{n:02d}</span>{esc(x)}</li>'
                                    for n, x in enumerate(st["steps"], 1)) + "</ol>")
            if "features" in st:
                feats = []
                for f in st["features"]:
                    av = f.get("availability")
                    b = self.badge(av, "availability") if av in ("mvp", "planned") else self.pending("MVP or planned?", True)
                    feats.append(f'<li class="feature" data-availability="{attr(av or "unknown")}">{b}<span>{esc(f["name"])}</span></li>')
                extra += (f'<h4 class="mono-heading">{esc(ui["features"])}</h4><p class="small muted">{esc(ui["featuresKey"])}</p>'
                          f'<ul class="features">{"".join(feats)}</ul>{self.pending(st.get("featuresNote"))}')
            if "screenshots" in st:
                shots = [s_ for s_ in st["screenshots"] if s_.get("status") in ("approved", "verified") or not self.release]
                if shots:
                    figs = "".join(
                        f'<figure class="shot" data-reveal><img src="{attr(x["src"])}" alt="{attr(x["alt"])}" '
                        f'loading="lazy" decoding="async"{" width=" + chr(34) + str(x["width"]) + chr(34) if x.get("width") else ""}'
                        f'{" height=" + chr(34) + str(x["height"]) + chr(34) if x.get("height") else ""}>'
                        f'<figcaption>{esc(x["caption"])}</figcaption></figure>' for x in shots)
                    extra += f'<h4 class="mono-heading">{esc(ui["screenshots"])}</h4><div class="shots">{figs}</div>'
                else:
                    extra += self.pending("Real MVP screenshots")
            if "milestones" in st:
                if st["milestones"]:
                    ms = "".join(f'<li data-state="{attr(m["state"])}">{self.badge(m["state"])}'
                                 f'<span class="ms-date mono">{esc(m.get("date", ""))}</span><span>{esc(m["label"])}</span></li>'
                                 for m in st["milestones"])
                    extra += f'<h4 class="mono-heading">{esc(ui["milestones"])}</h4><ol class="milestones">{ms}</ol>'
                else:
                    extra += self.pending("Milestones: done, in progress and next")
                extra += f'<p class="launch-label">{esc(prod["statusLabel"])}</p>'
            stages.append(f"""<section class="stage" data-reveal aria-labelledby="stage-{attr(st["id"])}">
  <p class="kicker"><span class="mono">{i:02d}</span> {esc(st["label"])}</p>
  <h3 id="stage-{attr(st["id"])}">{esc(st["headline"])}</h3>
  {body}{extra}
</section>""")
        cta = prod["cta"]
        if prod.get("url"):
            cta_html = f'<p class="panel-cta"><a class="btn btn-large" href="{attr(prod["url"])}" data-goatcounter-click="project-link">{esc(cta["alternateLabel"])}</a></p>'
        elif cta.get("href"):
            cta_html = f'<p class="panel-cta"><a class="btn btn-large" href="{attr(cta["href"])}">{esc(cta["label"])}</a></p>'
        else:
            cta_html = self.pending("Where 'Follow the journey' should lead (newsletter, LinkedIn, or product page)")
        body = f"""<div class="product-head">
  <p class="product-name">{esc(prod["name"])} <span class="badge badge-launch">{esc(prod["statusLabel"])}</span></p>
  {one_line}
</div>
<div class="stages">{"".join(stages)}</div>
{cta_html}"""
        return self.r.section(s, body)

    # ---------------------------------------------------------------- exploring
    def diagram(self, d):
        """Inline SVG, drawn from the content object only."""
        did = f"dg-{slug(d['title'])[:24]}"

        def box(x, y, w, h, label, cls="dg-box"):
            lines = wrap_words(label, max(10, int(w / 9)))
            ty = y + h / 2 - (len(lines) - 1) * 9
            texts = "".join(f'<tspan x="{x + w / 2}" y="{ty + i * 18:.0f}">{esc(t)}</tspan>' for i, t in enumerate(lines))
            return (f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="2"/>'
                    f'<text class="dg-text" text-anchor="middle" dominant-baseline="middle">{texts}</text>')

        def arrow(x1, y1, x2, y2):
            return f'<line class="dg-arrow" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" marker-end="url(#{did}-head)"/>'

        parts = []
        if d.get("steps"):
            n, bw, gap = len(d["steps"]), 140, 36
            ox = 30 + (150 if d.get("outside") else 0)
            W = ox + n * bw + (n - 1) * gap + 40
            H = 230
            parts.append(f'<rect class="dg-boundary" x="{ox - 20}" y="24" width="{n * bw + (n - 1) * gap + 40}" height="{H - 44}"/>')
            parts.append(f'<text class="dg-label" x="{ox - 8}" y="46">{esc(d["boundary"])}</text>')
            if d.get("outside"):
                parts.append(box(20, 85, 110, 64, d["outside"], "dg-box dg-outside"))
                parts.append(arrow(130, 117, ox - 4, 117))
            for i, step in enumerate(d["steps"]):
                x = ox + i * (bw + gap)
                parts.append(box(x, 80, bw, 74, step))
                if i:
                    parts.append(arrow(x - gap, 117, x - 4, 117))
        else:
            W, H = 660, 320
            parts.append(f'<rect class="dg-boundary" x="10" y="10" width="{W - 20}" height="{H - 20}"/>')
            parts.append(f'<text class="dg-label" x="24" y="34">{esc(d["boundary"])}</text>')
            parts.append(box(W / 2 - 130, 56, 260, 70, d["hub"], "dg-box dg-hub"))
            spokes = d.get("spokes", [])
            for i, sp in enumerate(spokes):
                x = 40 + i * ((W - 80) / max(1, len(spokes))) + 10
                w = (W - 80) / max(1, len(spokes)) - 20
                parts.append(box(x, 200, w, 80, sp))
                parts.append(f'<line class="dg-arrow dg-both" x1="{W / 2:.0f}" y1="126" x2="{x + w / 2:.0f}" y2="196" '
                             f'marker-end="url(#{did}-head)" marker-start="url(#{did}-tail)"/>')
        defs = (f'<defs><marker id="{did}-head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
                f'<path class="dg-head" d="M0,0 L10,5 L0,10 z"/></marker>'
                f'<marker id="{did}-tail" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
                f'<path class="dg-head" d="M10,0 L0,5 L10,10 z"/></marker></defs>')
        svg = (f'<svg class="diagram" viewBox="0 0 {W:.0f} {H}" role="img" aria-labelledby="{did}-t {did}-d">'
               f'<title id="{did}-t">{esc(d["title"])}</title><desc id="{did}-d">{esc(d["description"])}</desc>'
               f'{defs}{"".join(parts)}</svg>')
        note = self.pending(d.get("note")) if d.get("status") == "draft" else ""
        return (f'<figure class="diagram-figure" data-reveal>{svg}'
                f'<figcaption>{esc(d["title"])}</figcaption>{note}</figure>')

    def exploring(self, s):
        ui = self.ui["exploring"]
        out = []
        for i, p in enumerate(s["projects"]):
            collab = p.get("collaboration") or {}
            if collab.get("required") and not collab.get("text"):
                raise ValueError(f"{p['name']}: collaboration credit is required")
            collab_html = f'<p class="collab">{esc(collab["text"])}</p>' if collab.get("text") else ""
            status = (f'<span class="badge badge-status">{esc(p["statusLabel"])}</span>' if p.get("statusLabel")
                      else self.pending(p.get("statusNote") or "Status label", True))
            rows = []
            for key in ("problem", "hypothesis", "approach", "learned"):
                v = self.value(p, key)
                if v or p.get(key) is None and not self.release:
                    rows.append(f'<div><dt>{esc(ui[key])}</dt><dd>{v or self.pending("To be written")}</dd></div>')
            if status:  # release builds omit an unset status rather than show an empty row
                rows.append(f'<div><dt>{esc(ui["statusLabel"])}</dt><dd>{status}</dd></div>')
            if collab.get("text"):
                rows.append(f'<div><dt>{esc(ui["collaboration"])}</dt><dd>{esc(collab["text"])}</dd></div>')
            lists = ""
            for key, label in (("themes", ui["themes"]), ("apps", ui["apps"])):
                if p.get(key):
                    lis = []
                    for t in p[key]:
                        st = t.get("state")
                        b = self.badge(st) if st else self.pending("Built, prototype or proposed?", True)
                        role = f' <span class="meta">{esc(t["role"])}</span>' if t.get("role") else ""
                        lis.append(f"<li>{b}<span>{esc(t['name'])}{role}</span></li>")
                    lists += f'<h4 class="mono-heading">{esc(label)}</h4><ul class="state-list">{"".join(lis)}</ul>'
                    lists += self.pending(p.get(f"{key}Note"))
            related = ""
            rw = p.get("relatedWriting")
            if rw:
                related = (f'<p><a class="arrow-link" href="{attr(rw["url"])}" data-goatcounter-click="project-link">'
                           f'{esc(ui["related"])}: {esc(rw["title"])}</a></p>')
            diagram = self.diagram(p["diagram"]) if p.get("diagram") else ""
            out.append(f"""<article class="project{' project-alt' if i % 2 else ''}" aria-labelledby="proj-{attr(p["id"])}" data-reveal>
  <header class="project-head">
    <p class="kicker">{esc(p["category"])}</p>
    <h3 id="proj-{attr(p["id"])}">{esc(p["name"])}</h3>
    {collab_html}
    <p class="lead">{esc(p["description"])}</p>
  </header>
  <div class="project-body">
    <div>{diagram}{lists}{related}</div>
    <dl class="project-parts">{"".join(rows)}</dl>
  </div>
</article>""")
        return self.r.section(s, "".join(out))

    # ------------------------------------------------------------------ contact
    def field(self, form_id, f):
        ui = self.ui["contact"]
        fid = f"{form_id}-{f['name']}"
        req = f'<span class="req">({esc(ui["required"])})</span>' if f.get("required") else ""
        hint = f'<p class="field-hint" id="{fid}-hint">{esc(f["hint"])}</p>' if f.get("hint") else ""
        described = " ".join(x for x in (f"{fid}-hint" if f.get("hint") else "", f"{fid}-error") if x)
        common = (f'id="{fid}" name="{attr(f["name"])}" aria-describedby="{described}"'
                  f'{" required" if f.get("required") else ""}'
                  f'{" autocomplete=" + chr(34) + attr(f["autocomplete"]) + chr(34) if f.get("autocomplete") else ""}')
        if f["type"] == "textarea":
            control = f'<textarea {common} rows="5"></textarea>'
        elif f["type"] == "select":
            opts = f'<option value="">{esc(ui["choose"])}</option>' + "".join(
                f'<option>{esc(o)}</option>' for o in f["options"])
            control = f'<select {common}>{opts}</select>'
        else:
            control = f'<input type="{attr(f["type"])}" {common}>'
        return (f'<div class="field"><label for="{fid}">{esc(f["label"])} {req}</label>{hint}{control}'
                f'<p class="field-error" id="{fid}-error" hidden></p></div>')

    def contact(self, s):
        ui = self.ui["contact"]
        general = s.get("general", {})
        email = general.get("email")
        tabs = self.tabs("contact", ui["chooser"], [(f["audience"], f["tabLabel"]) for f in s["forms"]])
        privacy = s.get("privacyNotice", {})
        privacy_link = (f'<a href="{attr(privacy["href"])}">{esc(ui["privacyLink"])}</a>'
                        if privacy.get("status") not in ("missing", None) else "")
        panels = []
        for f in s["forms"]:
            head = f'<h3 class="panel-headline">{esc(f["headline"])}</h3><p>{esc(f["context"])}</p>'
            provider = s.get("formProvider", {})
            action = provider.get("endpoint") if provider.get("accessKey") else None
            fields = "".join(self.field(f["id"], fl) for fl in f["fields"])
            honeypot = (f'<div class="hp" aria-hidden="true"><label>{esc(ui["honeypot"])}'
                        f'<input type="checkbox" name="{attr(provider.get("honeypot", "botcheck"))}" tabindex="-1"></label></div>')
            hidden = ""
            if action:
                hidden = (f'<input type="hidden" name="access_key" value="{attr(provider["accessKey"])}">'
                          f'<input type="hidden" name="subject" value="{attr(f["tabLabel"])} enquiry from brandonbande.co.zw">'
                          f'<input type="hidden" name="from_name" value="brandonbande.co.zw">')
            unconfigured = "" if action else f' data-unconfigured="{attr(ui["unconfigured"])}"'

            msgs = (f' data-msg-required="{attr(ui["errorRequired"])}" data-msg-email="{attr(ui["errorEmail"])}"'
                    f' data-msg-sending="{attr(ui["sending"])}" data-msg-success="{attr(ui["success"])}"'
                    f' data-msg-failure="{attr(ui["failure"])}" data-msg-summary="{attr(ui["errorSummary"])}"')
            inner = f"""{head}
<form class="enquiry" id="form-{attr(f["id"])}" method="post" action="{attr(action or "#contact")}" data-form
  data-event="{attr(f["analyticsEvent"])}"{unconfigured}{msgs}>
  {hidden}{fields}{honeypot}
  <div class="form-foot">
    <button class="btn btn-large" type="submit">{esc(ui["submit"][f["id"]])}</button>
    <p class="small">{privacy_link}</p>
  </div>
  <p class="form-status" role="status" aria-live="polite"></p>
</form>{self.pending(provider.get("accessKeyNote")) if not action else ""}"""
            panels.append(self.panel("contact", f["audience"], inner))
        links = []
        if email:
            links.append(f'<a href="mailto:{attr(email)}">{esc(email)}</a>')
        for ref in general.get("links", []):
            try:
                item = self.c.resolve(ref)
                links.append(f'<a href="{attr(item["url"])}">{esc(item["label"])}</a>')
            except KeyError:
                pass
        general_html = (f'<div class="general"><h3 class="mono-heading">{esc(ui["general"])}</h3>'
                        f'{self.link_list(links)}</div>')
        body = f"""<p class="lead contact-headline">{esc(s["headline"])}</p>
<p class="contact-intro">{esc(s["intro"])}</p>
<div class="contact-grid">
  <div>{tabs}<div class="panels panels-swap" data-panels="contact">{"".join(panels)}</div></div>
  <div class="contact-aside">{general_html}{self.faq()}</div>
</div>"""
        return self.r.section(s, body)

    # ------------------------------------------------------------------ writing
    def writing(self, s):
        ui = self.ui["writing"]
        ft = s["featured"]
        excerpt = "".join(f"<p>{esc(p)}</p>" for p in ft["excerpt"])
        when = lambda d: f'<time datetime="{attr(d)}">{esc(date.fromisoformat(d).strftime("%-d %b %Y"))}</time>'
        featured = f"""<article class="post-card" data-reveal>
  <p class="mono-heading">{esc(ui["latest"])}</p>
  <h3 class="post-title"><a href="{attr(ft["url"])}">{esc(ft["title"])}</a></h3>
  <p class="meta mono">{when(ft["date"])} · {ft["readingMinutes"]} {esc(ui["readingTime"])}</p>
  <p class="post-summary">{esc(ft["summary"])}</p>
  <div class="post-excerpt prose">{excerpt}</div>
  <p><a class="text-link" href="{attr(ft["url"])}">{esc(ui["continue"])}<span class="visually-hidden">: {esc(ft["title"])}</span> →</a></p>
</article>"""
        items = "".join(f'<li><a href="{attr(a["url"])}">{esc(a["title"])}</a> <span class="meta mono">{when(a["date"])}</span></li>'
                        for a in s["articles"])
        more = f"""<div class="post-list" data-reveal>
  <h3 class="mono-heading">{esc(ui["more"])}</h3>
  <ul class="link-list articles">{items}</ul>
  <p><a class="text-link" href="{attr(s["allUrl"])}">{esc(ui["all"])} →</a></p>
</div>"""
        body = f"""<p class="lead writing-intro">{esc(s["intro"])}</p>
<div class="writing-grid">{featured}{more}</div>"""
        return self.r.section(s, body)

    def faq_items(self):
        return [i for i in self.c["faq"]["items"] if i.get("answer")]

    def faq(self):
        items = self.faq_items()
        if not items:
            return ""
        qa = "".join(f'<details class="qa"><summary>{esc(i["question"])}</summary><p>{esc(i["answer"])}</p></details>'
                     for i in items)
        missing = [i["question"] for i in self.c["faq"]["items"] if not i.get("answer")]
        note = self.pending("Answer owed for: " + "; ".join(missing)) if missing else ""
        return f'<div class="faq"><h3 class="mono-heading">{esc(self.c["faq"]["heading"])}</h3>{qa}{note}</div>'

    # ------------------------------------------------------------------ privacy
    def privacy_page(self):
        pg = self.c["pages/privacy"]
        parts = "".join(f'<h2>{esc(sec["heading"])}</h2>' + (f'<p>{esc(sec["body"])}</p>' if sec.get("body")
                        else self.pending(sec.get("bodyNote"))) for sec in pg["sections"])
        return f"""<section class="section surface-light legal" aria-labelledby="legal-title">
  <div class="wrap narrow">
    <p class="section-label"><a href="/">{esc(self.c.person["brandName"])}</a></p>
    <h1 id="legal-title" class="display-sm">{esc(pg["title"])}</h1>
    <p class="lead">{esc(pg["intro"])}</p>
    <p class="mono small"><time datetime="{attr(pg["updated"])}">{esc(pg["updated"])}</time></p>
    <div class="prose">{parts}</div>
  </div>
</section>"""

    # ----------------------------------------------------------------- dispatch
    def render(self, s):
        return {"home": self.hero, "about": self.about, "bring": self.bring, "standing": self.standing,
                "building": self.building, "exploring": self.exploring, "writing": self.writing, "contact": self.contact}[s["id"]](s)
