#!/usr/bin/env python3
"""
Generate clean, on-brand PLACEHOLDER images for assets referenced by the
frontend but missing from the repo. Output lands in repo-root assets/ (the
canonical source); frontend/scripts/sync-static-assets.mjs mirrors it into
frontend/static/assets/ at build time.

These are honest placeholders (text badges / branded tiles), NOT final art.
Replace any file listed in docs/ASSETS_NEEDED.md with real artwork; the prebuild
sync will publish the replacement automatically.

Rasterizes via macOS `sips` (ImageIO renders the SVG at its native aspect),
then forces exact dimensions. No third-party deps.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")

# Cafreso palette
BG = "#14110d"        # coffee black
SURFACE = "#1f1810"   # raised tile
GOLD = "#e8b84b"      # brand gold
CREAM = "#f5ead6"
MUTED = "#9a8c78"
LINE = "#3a2f22"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def badge_svg(w, h, label, sub=None, accent=GOLD, coin=False):
    """A rounded tile with a centered label (+ optional sub-label)."""
    cx, cy = w / 2, h / 2
    r = min(w, h) * 0.16
    fs = min(w, h) * (0.20 if len(label) <= 5 else 0.13)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{SURFACE}"/><stop offset="1" stop-color="{BG}"/></linearGradient></defs>',
        f'<rect width="{w}" height="{h}" rx="{r}" fill="url(#g)" stroke="{LINE}" stroke-width="{max(1,w*0.012)}"/>',
    ]
    if coin:
        cr = min(w, h) * 0.30
        parts.append(f'<circle cx="{cx}" cy="{cy-h*0.06}" r="{cr}" fill="{accent}"/>')
        parts.append(
            f'<text x="{cx}" y="{cy-h*0.06+cr*0.34}" font-family="Helvetica,Arial,sans-serif" '
            f'font-size="{cr*0.95}" font-weight="700" fill="{BG}" text-anchor="middle">{esc(label)}</text>'
        )
        if sub:
            parts.append(
                f'<text x="{cx}" y="{cy+h*0.34}" font-family="Helvetica,Arial,sans-serif" '
                f'font-size="{h*0.10}" fill="{MUTED}" text-anchor="middle" letter-spacing="1">{esc(sub)}</text>'
            )
    else:
        ty = cy + fs * 0.34 if not sub else cy + fs * 0.10
        parts.append(
            f'<text x="{cx}" y="{ty}" font-family="Helvetica,Arial,sans-serif" '
            f'font-size="{fs}" font-weight="700" fill="{accent}" text-anchor="middle" letter-spacing="1">{esc(label)}</text>'
        )
        if sub:
            parts.append(
                f'<text x="{cx}" y="{ty + fs*0.85}" font-family="Helvetica,Arial,sans-serif" '
                f'font-size="{fs*0.42}" fill="{MUTED}" text-anchor="middle" letter-spacing="2">{esc(sub)}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def hero_svg(w, h, title, sub):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<defs><linearGradient id="b" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="#241a10"/><stop offset="0.6" stop-color="{BG}"/>'
        f'<stop offset="1" stop-color="#0d0b07"/></linearGradient></defs>'
        f'<rect width="{w}" height="{h}" fill="url(#b)"/>'
        f'<rect x="{w*0.5}" y="0" width="{w*0.5}" height="{h}" fill="{GOLD}" opacity="0.04"/>'
        f'<text x="{w*0.5}" y="{h*0.5}" font-family="Helvetica,Arial,sans-serif" font-size="{h*0.2}" '
        f'font-weight="800" fill="{CREAM}" text-anchor="middle" letter-spacing="3">{esc(title)}</text>'
        f'<text x="{w*0.5}" y="{h*0.5 + h*0.16}" font-family="Helvetica,Arial,sans-serif" font-size="{h*0.07}" '
        f'fill="{GOLD}" text-anchor="middle" letter-spacing="4">{esc(sub)}</text>'
        f'</svg>'
    )


# name -> (width, height, svg)
ASSETS = {
    # partner / ecosystem logos (honest text badges)
    "icp.png":               (256, 256, badge_svg(256, 256, "ICP", "Internet Computer")),
    "gold-dao.png":          (256, 256, badge_svg(256, 256, "GOLD", "DAO")),
    "banking-brave-logo.png":(256, 256, badge_svg(256, 256, "B.BRAVE", "Banking")),
    "nanas-coin.png":        (256, 256, badge_svg(256, 256, "$N", "nanas", coin=True)),
    "open-chat.jpg":         (256, 256, badge_svg(256, 256, "CHAT", "OpenChat", accent=CREAM)),
    # Cafreso brand
    "cf-gold.png":           (256, 256, badge_svg(256, 256, "cf", accent=GOLD)),
    "cafreso.png":           (800, 400, hero_svg(800, 400, "CAFRESO", "VERTICAL FARM")),
    "cafreso-roaster.png":   (512, 512, badge_svg(512, 512, "ROASTER", "Cafreso Coffee", accent=GOLD)),
    "not-yet-available.png": (512, 512, badge_svg(512, 512, "COMING", "soon", accent=MUTED)),
}


def rasterize(svg_text, w, h, out_path):
    with tempfile.TemporaryDirectory() as td:
        svg_path = os.path.join(td, "in.svg")
        with open(svg_path, "w") as f:
            f.write(svg_text)
        # sips/ImageIO renders the SVG at its native aspect ratio (no padding).
        raw_png = os.path.join(td, "raw.png")
        subprocess.run(["sips", "-s", "format", "png", svg_path, "--out", raw_png],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Force exact pixel dimensions, then write out in the final format.
        tmp_png = os.path.join(td, "exact.png")
        subprocess.run(["sips", "-z", str(h), str(w), raw_png, "--out", tmp_png],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if out_path.lower().endswith((".jpg", ".jpeg")):
            subprocess.run(["sips", "-s", "format", "jpeg", tmp_png, "--out", out_path],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.replace(tmp_png, out_path)


def main():
    only = set(sys.argv[1:])
    os.makedirs(OUT, exist_ok=True)
    made = []
    for name, (w, h, svg) in ASSETS.items():
        if only and name not in only:
            continue
        out_path = os.path.join(OUT, name)
        rasterize(svg, w, h, out_path)
        made.append((name, w, h, os.path.getsize(out_path)))
    width = max((len(n) for n, *_ in made), default=0)
    for n, w, h, size in made:
        print(f"  {n.ljust(width)}  {w}x{h}  {size:>6} B")
    print(f"generated {len(made)} placeholder asset(s) -> {OUT}")


if __name__ == "__main__":
    main()
