#!/usr/bin/env python3
"""Build brandonbande.co.zw: content/ data objects -> dist/ HTML.

Steps:
  1. Validate every content object (structure, required fields, references).
  2. --release only: the integrity gate refuses drafts, missing assets,
     owed facts and unverified statistics.
  3. Clean dist/, copy static/, write CNAME.
  4. Build Open Analytics Work (scripts/open_analytics.py).
  5. Render the homepage and 404 page from templates/ + content/.
  6. Discovery files: sitemap.xml, robots.txt (and llms.txt).
  7. Checks: one H1, JSON-LD parses, internal links resolve, no internal files,
     banned strings, budgets (warnings in draft, errors in release).

Usage:
  python3 scripts/build.py              # draft build: DRAFT banner + noindex everywhere
  python3 scripts/build.py --release    # release build: fails on anything unverified
  python3 scripts/build.py --out DIR    # alternative output folder
Standard library only; no network access.
"""

import argparse
import html
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import discovery  # noqa: E402
import open_analytics  # noqa: E402
import site_checks  # noqa: E402
from content_model import Content, ContentError, stat_problems  # noqa: E402
from render_site import Renderer  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
HOME_SOURCES = ("content", "templates", "static")


def fail(title, lines):
    print(f"\nBUILD FAILED: {title}", file=sys.stderr)
    for line in lines:
        print(f"  - {line}", file=sys.stderr)
    sys.exit(1)


def safe_out(out):
    out = out.resolve()
    if out == ROOT or out in ROOT.parents or out == Path(out.anchor):
        fail("unsafe output folder", [f"{out} would delete the project or a parent folder"])
    return out


def homepage_lastmod(today):
    """Last commit date of the homepage sources, or today if they have uncommitted changes."""
    def git(*args):
        return subprocess.run(["git", *args, "--", *HOME_SOURCES], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    try:
        if git("status", "--porcelain"):
            return today.isoformat()
        return git("log", "-1", "--format=%cs") or today.isoformat()
    except (OSError, subprocess.CalledProcessError):
        return today.isoformat()


def sitemap(rows):
    body = "\n".join(f"  <url><loc>{html.escape(u)}</loc><lastmod>{m}</lastmod></url>" for u, m in rows)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{body}\n</urlset>\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build brandonbande.co.zw into dist/.")
    ap.add_argument("--release", action="store_true", help="enforce the content-integrity gate")
    ap.add_argument("--override", action="store_true",
                    help="with --release: report gate items as warnings instead of failing (Brandon's call)")
    ap.add_argument("--out", type=Path, default=ROOT / "dist", help="output folder (default: dist/)")
    ap.add_argument("--content", type=Path, default=None, help=argparse.SUPPRESS)  # test fixtures only
    ap.add_argument("--oa-src", type=Path, default=open_analytics.DEFAULT_SRC, help=argparse.SUPPRESS)  # test fixtures only
    args = ap.parse_args(argv)
    started = time.monotonic()
    today = date.today()
    mode = "release" if args.release else "draft"
    print(f"Building brandonbande.co.zw ({mode})")

    # 1-2. Content
    try:
        content = Content(args.content) if args.content else Content()
    except ContentError as e:
        fail("content does not parse", [str(e)])
    errors = content.validate()
    if errors:
        fail("content validation", errors)
    print(f"  ok     {len(content.objects)} content objects valid")
    stats = stat_problems(content)
    if args.release:
        problems = content.release_problems() + stats
        if problems and args.override:
            print(f"  OVERRIDE release gate: {len(problems)} item(s) not approved/verified")
        elif problems:
            fail(f"release gate: {len(problems)} item(s) not approved/verified", problems)
        else:
            print("  ok     release gate passed")
    if not (args.release and args.override):
        for p in stats:
            print(f"  WARN   {p}")

    # 3. Output folder
    out = safe_out(args.out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(STATIC, out)
    shutil.copy2(ROOT / "CNAME", out / "CNAME")
    portrait = content.person["image"]["path"]
    if not (out / portrait.lstrip("/")).exists():  # JSON-LD Person.image must resolve
        fail("portrait", [f"person.json image.path {portrait} is not in static/ (run scripts/images.py and update the path)"])
    lastmod = homepage_lastmod(today)

    def shell(published):
        return Renderer(content, release=args.release, oa_published=published, today=today, lastmod=lastmod).oa_shell()

    # 4. Open Analytics Work
    try:
        oa_rows = open_analytics.build(out=out, src=args.oa_src, today=today, draft=not args.release, shell=shell)
    except open_analytics.BuildError as e:
        fail("Open Analytics Work", [str(e)])

    # 5. Pages
    renderer = Renderer(content, release=args.release, oa_published=bool(oa_rows), today=today, lastmod=lastmod)
    try:
        (out / "index.html").write_text(renderer.home(), encoding="utf-8")
        privacy_path = content["pages/privacy"]["path"].strip("/")
        (out / privacy_path).mkdir(parents=True, exist_ok=True)
        (out / privacy_path / "index.html").write_text(renderer.privacy(), encoding="utf-8")
        (out / "404.html").write_text(renderer.not_found(), encoding="utf-8")
    except ValueError as e:  # integrity rule raised by a renderer
        fail("rendering", [str(e)])
    print("  built  index.html, privacy/, 404.html")

    # 6. Discovery files
    site_url = content.site["url"].rstrip("/")
    rows = [(f"{site_url}/", lastmod), (f"{site_url}/privacy/", lastmod)] + oa_rows
    (out / "sitemap.xml").write_text(sitemap(rows), encoding="utf-8")
    (out / "robots.txt").write_text(discovery.robots_txt(content), encoding="utf-8")
    (out / "llms.txt").write_text(discovery.llms_txt(content, renderer.sections.faq_items(), open_analytics.PUBLISHED),
                                  encoding="utf-8")
    print(f"  built  sitemap.xml ({len(rows)} URLs), robots.txt, llms.txt")

    # 7. Checks
    errors, warnings, stats = site_checks.run(out, content, args.release, renderer.critical_css_bytes())
    for w in warnings:
        print(f"  WARN   {w}")
    if errors:
        fail("post-build checks", errors)
    print(f"  ok     checks passed · home HTML {stats['home_html_gz']:,} B gz · critical CSS "
          f"{stats['critical_css']:,} B · CSS {stats['css_gz']:,} B gz · JS {stats['js_gz']:,} B gz · "
          f"fonts {stats['fonts']:,} B")
    print(f"OK: {mode} build in {time.monotonic() - started:.2f}s → {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")


if __name__ == "__main__":
    main()
