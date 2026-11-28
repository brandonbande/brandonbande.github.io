"""Discoverability surfaces: homepage JSON-LD graph, llms.txt, robots.txt.

Everything is generated from content objects, and only facts that are visible on the
page are marked up .
"""

import json
import re

SEARCH_AND_ANSWER_BOTS = ["Googlebot", "Bingbot", "OAI-SearchBot", "ChatGPT-User", "PerplexityBot",
                          "Perplexity-User", "Claude-SearchBot", "Claude-User", "DuckAssistBot", "Applebot"]
TRAINING_BOTS = ["GPTBot", "ClaudeBot", "Google-Extended", "CCBot", "Applebot-Extended", "Meta-ExternalAgent"]


def _clean(d):
    """Drop empty values so the graph never states nulls."""
    if isinstance(d, dict):
        return {k: _clean(v) for k, v in d.items() if v not in (None, "", [], {})}
    if isinstance(d, list):
        return [_clean(v) for v in d if v not in (None, "", [], {})]
    return d


def person_node(content, full=True):
    p, site = content.person, content.site
    base = site["url"].rstrip("/")
    node = {
        "@type": "Person",
        "@id": p["id"],
        "name": p["name"],
        "alternateName": p.get("brandName"),
        "url": f"{base}/",
        "sameAs": [s["url"] for s in p.get("sameAs", [])],
    }
    if not full:
        return _clean(node)
    hero = content["sections/01-hero"]
    node.update({
        "givenName": p.get("givenName"),
        "familyName": p.get("familyName"),
        "jobTitle": (p.get("jobTitle") or {}).get("value"),
        "description": p["bio"]["oneLine"],
        "image": base + p["image"]["path"],
        "nationality": {"@type": "Country", "name": p.get("nationality")},
        "knowsAbout": p.get("knowsAbout"),
    })
    works = p.get("worksFor") or {}
    if works.get("name"):
        node["worksFor"] = {"@type": "CollegeOrUniversity", "name": works["name"], "url": works.get("url")}
    edu = [e for e in p.get("education", []) if e.get("institution")]
    if edu:
        node["alumniOf"] = [{"@type": "CollegeOrUniversity", "name": e["institution"]} for e in edu]
    loc = p.get("location") or {}
    if (hero.get("locationLine") or {}).get("text") and loc.get("locality"):  # only when shown on the page
        node["address"] = {"@type": "PostalAddress", "addressLocality": loc["locality"], "addressCountry": loc["country"]}
    node["memberOf"] = [
        {"@type": "OrganizationRole", "roleName": a["role"], "startDate": a.get("start"), "endDate": a.get("end"),
         "memberOf": {"@type": "Organization", "name": a["organisation"], "url": a.get("url")}}
        for a in p.get("affiliations", [])]
    return _clean(node)


def _datetime(value):
    """A content date (YYYY-MM-DD) as an ISO 8601 datetime at midnight UTC; schema.org dates here are DateTimes."""
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return f"{value}T00:00:00+00:00"
    return value


def home_graph(content, faq_items, lastmod):
    site, base = content.site, content.site["url"].rstrip("/")
    pid = content.person["id"]
    graph = [person_node(content, full=True)]
    graph.append({"@type": "WebSite", "@id": f"{base}/#website", "url": f"{base}/", "name": site["name"],
                  "description": site["description"], "inLanguage": site["language"], "publisher": {"@id": pid}})
    graph.append({"@type": "ProfilePage", "@id": f"{base}/#profile", "url": f"{base}/", "name": site["title"],
                  "dateModified": lastmod, "inLanguage": site["language"], "mainEntity": {"@id": pid},
                  "isPartOf": {"@id": f"{base}/#website"}})
    business = next(o for o in content["sections/03-bring"]["offerings"] if o["id"] == "business")
    graph.append({"@type": "OfferCatalog", "@id": f"{base}/#services", "name": business["tabLabel"],
                  "itemListElement": [
                      {"@type": "Offer", "itemOffered": {"@type": "Service", "name": s["name"], "description": s["summary"],
                                                         "provider": {"@id": pid}}}
                      for s in business["services"]]})
    prod = content["sections/05-building"]["product"]
    graph.append(_clean({"@type": "CreativeWork", "@id": f"{base}/#studybuddy", "name": prod["name"],
                         "description": prod.get("oneLine"), "creativeWorkStatus": prod["statusLabel"],
                         "creator": {"@id": pid}}))
    for proj in content["sections/06-exploring"]["projects"]:
        creators = [{"@id": pid}] + [{"@type": "Person", "name": c["name"], "url": c.get("url")}
                                     for c in (proj.get("collaboration") or {}).get("people", [])]
        graph.append(_clean({"@type": "CreativeWork", "@id": f"{base}/#{proj['id']}", "name": proj["name"],
                             "description": proj["description"], "genre": proj["category"],
                             "creativeWorkStatus": proj.get("statusLabel"), "creator": creators}))
    writing = content.objects.get("sections/07-writing")
    if writing:
        posts = [writing["featured"]] + writing["articles"]
        graph.append({"@type": "ItemList", "@id": f"{base}/#writing", "name": writing["heading"],
                      "itemListElement": [
                          {"@type": "ListItem", "position": i, "item": _clean({
                              "@type": "BlogPosting", "headline": a["title"], "url": a["url"],
                              "datePublished": _datetime(a["date"]), "description": a.get("summary"), "author": {"@id": pid}})}
                          for i, a in enumerate(posts, 1)]})
    if faq_items:
        graph.append({"@type": "FAQPage", "@id": f"{base}/#faq", "mainEntity": [
            {"@type": "Question", "name": i["question"], "acceptedAnswer": {"@type": "Answer", "text": i["answer"]}}
            for i in faq_items]})
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=2)


def page_graph(content, url, name, crumbs):
    base = content.site["url"].rstrip("/")
    graph = [person_node(content, full=False),
             {"@type": "WebPage", "@id": f"{url}#page", "url": url, "name": name,
              "isPartOf": {"@id": f"{base}/#website"}, "about": {"@id": content.person["id"]}},
             {"@type": "BreadcrumbList", "itemListElement": [
                 {"@type": "ListItem", "position": i, "name": n, "item": u} for i, (n, u) in enumerate(crumbs, 1)]}]
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=2)


def llms_txt(content, faq_items, oa_pieces):
    """llms.txt (llmstxt.org format): a plain-language summary with links. ."""
    site, p = content.site, content.person
    base = site["url"].rstrip("/")
    bring = content["sections/03-bring"]
    business = next(o for o in bring["offerings"] if o["id"] == "business")
    events = next(o for o in bring["offerings"] if o["id"] == "events")
    prod = content["sections/05-building"]["product"]
    lines = [f"# {p['name']}", "", f"> {site['llms']['summary']}", "",
             f"{p['brandName']}: {', '.join(d.rstrip('.') for d in p['descriptors'])}.", "",
             "## Services for organisations", ""]
    lines += [f"- {s['name']}: {s['summary']}" for s in business["services"]]
    lines += [f"- [Enquire about a business challenge]({base}/?for=business#contact)", "",
              "## Speaking", "", f"Themes: {'; '.join(events['themes'])}.", f"Formats: {'; '.join(events['formats'])}.",
              f"- [Invite {p['brandName']} to speak]({base}/?for=events#contact)", "", "## Projects", ""]
    lines.append(f"- {prod['name']} ({prod['statusLabel'].title()}): "
                 f"{prod.get('oneLine') or 'Flagship learning product in development.'} [{base}/#building]")
    for proj in content["sections/06-exploring"]["projects"]:
        collab = (proj.get("collaboration") or {}).get("text", "")
        status = f" Status: {proj['statusLabel']}." if proj.get("statusLabel") else " Status: exploration."
        lines.append(f"- {proj['name']}: {proj['description']}{status} {collab} [{base}/#exploring]".replace("  ", " "))
    writing = content.objects.get("sections/07-writing")
    if writing:
        lines += ["", "## Writing", "", writing["intro"], ""]
        lines += [f"- [{a['title']}]({a['url']}) ({a['date']})" for a in [writing["featured"]] + writing["articles"]]
        lines.append(f"- [All articles]({writing['allUrl']})")
    if faq_items:
        lines += ["", "## Quick answers", ""]
        lines += [f"- {i['question']} {i['answer']}" for i in faq_items]
    if oa_pieces:
        oa = site["sections"]["openAnalytics"]
        lines += ["", f"## {oa['title']}", "", f"- [{oa['title']}]({base}{oa['path']}): {oa['description']}"]
        lines += [f"- [{t}]({u})" for u, t in oa_pieces]
    lines += ["", "## Profiles", ""]
    lines += [f"- [{s['label']}]({s['url']})" for s in p.get("sameAs", [])]
    return "\n".join(lines).rstrip() + "\n"


def robots_txt(content):
    site = content.site
    base = site["url"].rstrip("/")
    allow_training = (site.get("crawlers") or {}).get("allowTrainingCrawlers", True)
    out = ["# Crawler policy (content/site.json → crawlers).",
           "# Search engines and AI answer engines are welcome.", ""]
    for bot in SEARCH_AND_ANSWER_BOTS:
        out += [f"User-agent: {bot}", "Allow: /", ""]
    for bot in TRAINING_BOTS:
        out += [f"User-agent: {bot}", "Allow: /" if allow_training else "Disallow: /", ""]
    out += ["User-agent: *", "Allow: /", "", f"Sitemap: {base}/sitemap.xml", ""]
    return "\n".join(out)
