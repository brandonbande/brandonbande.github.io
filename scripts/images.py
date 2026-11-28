#!/usr/bin/env python3
"""Image pipeline. Needs Pillow; run locally, commit the output.

Reads the approved portrait original (person.json → image.source) and writes:
  static/assets/portrait/portrait-<w>.webp and .jpg  responsive variants (never upscaled)
  static/assets/og/brandon-bande-og.jpg             1200×630 social card
  static/favicon.svg, favicon.ico, icons/*.png      site icon in every format browsers ask for
  assets-src/images.json                            manifest read by scripts/build.py

The face is never generated or altered: only crop, scale and re-encode .
AVIF is not produced because this Pillow build lacks an AVIF encoder.

Usage:  python3 scripts/images.py
"""

import json
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow is required: pip install Pillow")

ROOT = Path(__file__).resolve().parent.parent
WIDTHS = (400, 640, 800, 1000)
INK, PAPER, LIME, GREY = (15, 16, 14), (244, 241, 234), (198, 242, 78), (163, 163, 154)


def load_json(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def font(size, weight=700, width=100, mono=False):
    if mono:
        return ImageFont.truetype(str(ROOT / "static/fonts/jetbrains-mono-latin-500.woff2"), size)
    f = ImageFont.truetype(str(ROOT / "static/fonts/archivo-latin-wdth-wght.woff2"), size)
    try:
        axes = {a["name"].decode() if isinstance(a["name"], bytes) else a["name"]: a for a in f.get_variation_axes()}
        values = [width if "dth" in name.lower() else weight for name in axes]
        f.set_variation_by_axes(values)
    except (OSError, AttributeError):
        pass  # static rendering is acceptable
    return f


def portrait_variants(src, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("portrait-*"):
        old.unlink()
    im = Image.open(src).convert("RGB")
    variants = []
    for w in WIDTHS:
        if w > im.width:
            continue
        h = round(im.height * w / im.width)
        scaled = im.resize((w, h), Image.LANCZOS)
        scaled.save(out_dir / f"portrait-{w}.webp", "WEBP", quality=60, method=6)
        scaled.save(out_dir / f"portrait-{w}.jpg", "JPEG", quality=68, optimize=True, progressive=True)
        variants.append({"width": w, "height": h})
    if not variants or variants[-1]["width"] != im.width:  # always include the original width
        scaled = im
        scaled.save(out_dir / f"portrait-{im.width}.webp", "WEBP", quality=60, method=6)
        scaled.save(out_dir / f"portrait-{im.width}.jpg", "JPEG", quality=68, optimize=True, progressive=True)
        variants.append({"width": im.width, "height": im.height})
    return im, variants


def og_card(portrait, person, site, dest):
    W, H = 1200, 630
    card = Image.new("RGB", (W, H), INK)
    # Portrait: square crop scaled to full height, placed so the face sits inside both the
    # 1.91:1 frame and a centred square crop (WhatsApp/X 'summary' previews).
    side = min(portrait.size)
    left = (portrait.width - side) // 2
    square = portrait.crop((left, 0, left + side, side)).resize((H, H), Image.LANCZOS)
    x0 = 120
    card.paste(square, (x0, 0))
    draw = ImageDraw.Draw(card)
    draw.rectangle([x0 + H, 0, x0 + H + 8, H], fill=LIME)
    tx = x0 + H + 44
    *given, family = person["name"].split()
    draw.text((tx, 150), " ".join(given), font=font(64, 800), fill=PAPER)
    draw.text((tx, 218), family + ".", font=font(64, 800), fill=PAPER)
    y = 330
    for d in person["descriptors"]:
        draw.text((tx, y), d.rstrip(".").upper(), font=font(22, mono=True), fill=LIME if y == 330 else GREY)
        y += 38
    draw.text((tx, H - 70), site["url"].replace("https://", ""), font=font(20, mono=True), fill=GREY)
    dest.parent.mkdir(parents=True, exist_ok=True)
    card.save(dest, "JPEG", quality=72, optimize=True)  # baseline: some link-preview scrapers reject progressive JPEGs


ICON_SIZES = {"icon-48.png": 48, "icon-192.png": 192, "icon-512.png": 512}

# The mark on a 64-unit grid, drawn in paint order: ink tile, a geometric 'B' (stem and two bowls
# whose right corners are rounded, then their counters), and the lime block. One definition feeds
# favicon.svg and every raster icon, so all browsers show the same thing whatever fonts they have.
# Each shape: (x0, y0, x1, y1, right-corner radius, colour).
ICON_SHAPES = [
    (0, 0, 64, 64, 0, INK),
    (10, 16, 33, 31.5, 7.75, PAPER),     # top bowl
    (10, 29, 36, 47, 9, PAPER),          # bottom bowl
    (17, 21.5, 26.5, 26.5, 2.5, INK),    # top counter
    (17, 35, 28, 41.5, 3.25, INK),       # bottom counter
    (42, 38, 51, 47, 0, LIME),
]


def _hex(rgb):
    return "#%02X%02X%02X" % rgb


def icon_svg():
    parts = []
    for x0, y0, x1, y1, r, c in ICON_SHAPES:
        if r:
            d = (f"M{x0} {y0}H{x1 - r}A{r} {r} 0 0 1 {x1} {y0 + r}V{y1 - r}"
                 f"A{r} {r} 0 0 1 {x1 - r} {y1}H{x0}Z")
            parts.append(f'<path d="{d}" fill="{_hex(c)}"/>')
        else:
            parts.append(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="{_hex(c)}"/>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">' + "".join(parts) + "</svg>\n"


def icon_master(size=512):
    k = size / 64
    im = Image.new("RGB", (size, size), INK)
    draw = ImageDraw.Draw(im)
    for x0, y0, x1, y1, r, c in ICON_SHAPES:
        box = [x0 * k, y0 * k, x1 * k - 1, y1 * k - 1]
        if r:
            radius = min(r * k, (box[3] - box[1]) / 2 - 1)  # Pillow rejects a radius of half the height or more
            draw.rounded_rectangle(box, radius=radius, fill=c, corners=(False, True, True, False))
        else:
            draw.rectangle(box, fill=c)
    return im


def icons(static_dir):
    """favicon.svg, favicon.ico (16/32/48), icons/*.png, and /apple-touch-icon.png at the root,
    where iOS and some crawlers request it without reading the page."""
    (static_dir / "favicon.svg").write_text(icon_svg(), encoding="utf-8")
    master = icon_master()
    out = static_dir / "icons"
    out.mkdir(parents=True, exist_ok=True)
    for name, px in ICON_SIZES.items():
        master.resize((px, px), Image.LANCZOS).save(out / name, "PNG", optimize=True)
    master.resize((180, 180), Image.LANCZOS).save(static_dir / "apple-touch-icon.png", "PNG", optimize=True)
    master.save(static_dir / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])


def main():
    person, site = load_json("content/person.json"), load_json("content/site.json")
    src = ROOT / person["image"]["source"]
    if not src.exists():
        sys.exit(f"Portrait original not found: {src}")
    icons(ROOT / "static")
    portrait, variants = portrait_variants(src, ROOT / "static/assets/portrait")
    og_dest = ROOT / site["ogImage"]["path"].lstrip("/").replace("assets/", "static/assets/", 1)
    og_card(portrait, person, site, og_dest)
    manifest = {
        "_note": "GENERATED by scripts/images.py. Do not edit.",
        "portrait": {"base": "/assets/portrait/portrait", "variants": variants, "formats": ["webp", "jpg"],
                     "source": person["image"]["source"]},
        "og": {"path": site["ogImage"]["path"], "width": 1200, "height": 630},
    }
    (ROOT / "assets-src/images.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    sizes = sum(p.stat().st_size for p in (ROOT / "static/assets/portrait").iterdir())
    print(f"OK: {len(variants)} portrait widths ({sizes:,} B total), OG card → {og_dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
