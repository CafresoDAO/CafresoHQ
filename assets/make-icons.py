"""
Generate square iOS / PWA icons from the master cf-black.png logo.

The master logo is a tall portrait PNG (~1697x2000) with a black cursive "Cf"
on white. iOS Safari's "Add to Home Screen" expects a SQUARE opaque icon and
falls back to the page title letter when given a non-square source.

This script produces:
  - apple-touch-icon.png   (180x180)  iPhone home screen
  - apple-touch-icon-152.png (152x152) iPad retina
  - apple-touch-icon-167.png (167x167) iPad Pro
  - icon-192.png            (192x192)  PWA manifest
  - icon-512.png            (512x512)  PWA manifest / install splash
  - favicon-32.png          (32x32)    browser tab
  - favicon-16.png          (16x16)    browser tab small

All outputs use a banana-yellow background (#F5D25D, Cafreso brand-banana)
with the centered Cf monogram tinted coffee (#262313, brand-coffee). 12%
safe padding so iOS's rounded-corner mask doesn't clip the mark.

Run from the project root:
    python assets/make-icons.py
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent           # .../assets
MASTER = ROOT / 'cf-black.png'

# Cafreso brand palette
BG_BANANA = (245, 210, 93, 255)   # #F5D25D
FG_COFFEE = (38,  35, 19, 255)    # #262313  (re-tint the Cf mark)

# Output sizes
TARGETS = [
    ('apple-touch-icon.png',     180),
    ('apple-touch-icon-152.png', 152),
    ('apple-touch-icon-167.png', 167),
    ('icon-192.png',             192),
    ('icon-512.png',             512),
    ('favicon-32.png',            32),
    ('favicon-16.png',            16),
]

# Safe-area padding so iOS's rounded-square mask doesn't crop the mark.
PAD_RATIO = 0.16


def _trim_to_content(im: Image.Image) -> Image.Image:
    """Crop transparent / near-white margins so the Cf mark is centered."""
    # Convert to RGBA for alpha sniffing
    rgba = im.convert('RGBA')
    # Build a mask: pixel counts as "content" if it's clearly non-white AND
    # not fully transparent. This handles both white-bg and transparent-bg
    # versions of the master.
    bbox = rgba.getbbox()
    if not bbox:
        return rgba
    # Tighten the bbox by scanning for visible (dark) pixels
    pixels = rgba.load()
    w, h = rgba.size
    min_x, min_y, max_x, max_y = w, h, 0, 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a < 16:
                continue
            # near-white ignored
            if r > 235 and g > 235 and b > 235:
                continue
            if x < min_x: min_x = x
            if y < min_y: min_y = y
            if x > max_x: max_x = x
            if y > max_y: max_y = y
    if max_x <= min_x or max_y <= min_y:
        return rgba
    return rgba.crop((min_x, min_y, max_x + 1, max_y + 1))


# _tint() (defined below) covers both coffee and white variants; the old
# _tint_to_coffee helper has been replaced by the general version.


def _composite(size: int, mark: Image.Image) -> Image.Image:
    canvas = Image.new('RGBA', (size, size), BG_BANANA)
    inner = int(size * (1 - 2 * PAD_RATIO))
    # Resize mark to fit inside the safe area while preserving aspect
    mw, mh = mark.size
    scale = min(inner / mw, inner / mh)
    new_w = max(1, int(mw * scale))
    new_h = max(1, int(mh * scale))
    resized = mark.resize((new_w, new_h), Image.LANCZOS)
    ox = (size - new_w) // 2
    oy = (size - new_h) // 2
    canvas.alpha_composite(resized, (ox, oy))
    return canvas.convert('RGB')  # drop alpha — iOS prefers opaque RGB


def _tint(mark: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    """Generic luminance-as-alpha tint for the Cf mask.
    Dark source pixels become opaque `color`; near-white pixels drop to alpha 0."""
    rgba = mark.convert('RGBA')
    pixels = rgba.load()
    w, h = rgba.size
    cr, cg, cb = color
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a < 16 or (r > 230 and g > 230 and b > 230):
                pixels[x, y] = (cr, cg, cb, 0)
                continue
            lum = (r + g + b) // 3
            new_a = max(0, min(255, 255 - lum))
            new_a = (new_a * a) // 255
            pixels[x, y] = (cr, cg, cb, new_a)
    return rgba


def _write_topbar_marks(trimmed: Image.Image) -> None:
    """Write transparent-background Cf marks for the in-app topbar / EcosystemNav.
    Two variants:
      - cf-mark-coffee.png  for light mode (coffee on transparent)
      - cf-mark-white.png   for dark mode (white on transparent)
    These are sized 256px on the longer axis (plenty for retina sizes at ~44px CSS height).
    """
    targets = [
        ('cf-mark-coffee.png', FG_COFFEE[:3]),
        ('cf-mark-white.png',  (255, 255, 255)),
    ]
    # Resize the trimmed mask so the longer side is 256, preserving aspect ratio
    mw, mh = trimmed.size
    target_long = 256
    scale = target_long / max(mw, mh)
    new_w, new_h = max(1, int(mw * scale)), max(1, int(mh * scale))
    base = trimmed.resize((new_w, new_h), Image.LANCZOS)
    for name, color in targets:
        out = _tint(base, color)
        path = ROOT / name
        out.save(path, 'PNG', optimize=True)
        print(f'  wrote {name:30s} ({new_w}x{new_h})  {path.stat().st_size // 1024} KB')


def main() -> None:
    print(f'Reading master: {MASTER}')
    master = Image.open(MASTER)
    print(f'  size={master.size} mode={master.mode}')

    trimmed = _trim_to_content(master)
    print(f'  trimmed to content: {trimmed.size}')

    tinted_coffee = _tint(trimmed, FG_COFFEE[:3])

    for name, sz in TARGETS:
        out_path = ROOT / name
        icon = _composite(sz, tinted_coffee)
        icon.save(out_path, 'PNG', optimize=True)
        print(f'  wrote {name:30s} ({sz}x{sz})  {out_path.stat().st_size // 1024} KB')

    print('writing topbar marks…')
    _write_topbar_marks(trimmed)

    print('done.')


if __name__ == '__main__':
    main()
