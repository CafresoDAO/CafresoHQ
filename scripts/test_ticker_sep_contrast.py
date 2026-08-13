#!/usr/bin/env python3
"""The ticker separator (and, it turned out, the market-quote colors)
failed WCAG AA contrast in several of the real theme x day/night
combinations — found auditing the first one.

Started narrow: `theme-wallstreet`'s own override of `.ticker-track .line
.sep` (`#00e0a0` at 37.6% alpha) was never put through the same contrast
analysis as the base rule's own documented fix (3.38:1 -> 5.48:1). Fixed
that (day mode: 2.42:1 -> 5.52:1), then audited the REST of the matrix
live rather than assuming "fixed one theme, done" — themes x day/night is
14 combinations, not one, and two more were failing:

  - `theme-coffeeshop` (day mode): its own --office-ticker-bg (#3e2c1e)
    never got the base .sep color (#9a8d7c) re-checked either — 4.09:1.
  - EVERY theme in night mode: `body.night .ticker` hardcodes the ticker
    background to #3a3050 app-wide, unconditionally overriding every
    theme's own --office-ticker-bg (including the wallstreet fix above,
    which was tuned against wallstreet's OWN #0a0a1a and only measured
    4.01:1 against the #3a3050 that actually applies in night mode).
    #9a8d7c against #3a3050 measures 3.77:1.

All three measured via getComputedStyle on a live throwaway office (real
cascade resolution, not hand-resolved CSS), not just this script's own
recomputation. Fixed with three additive rules, each landing at ~5.4:1 to
match the original fix's own precedent rather than a new number each
time:
  - `body.theme-coffeeshop .ticker-track .line .sep` (day only — the
    theme's OWN --office-ticker-bg is unreachable in night mode for the
    same reason above, so night mode already gets the generic fix)
  - `body.night .ticker-track .line .sep` (generic — covers every theme
    that doesn't have its own override: default, sepia, solarized,
    dracula, highcontrast, and coffeeshop.night)
  - `body.theme-wallstreet.night .ticker-track .line .sep` (combined
    selector, so Trading Floor keeps its own green branding in night mode
    instead of falling back to the generic fix's neutral tone)

Finishing that audit turned up one more, in a related but different
selector family: `.mkt-up`/`.mkt-down`/`.kw` (the market-quote colors and
the keyword highlight `marketTicker` — Trading Floor's Coinbase-fed
ticker — actually renders). `.mkt-up` and `.kw` both clear night mode's
real #3a3050 background comfortably (9.11:1, 8.71:1), but `.mkt-down`
does not — same red, same background the .sep fix above had to
re-target: measures 3.74:1. Fixed the same way, additively:
`body.theme-wallstreet.night .ticker-track .line .mkt-down` at 5.39:1.

(The BASE, non-wallstreet `.mkt-up`/`.mkt-down` rules — `var(--ok,
#1f8a4c)` / `var(--danger, #c0392b)`, both variables undefined everywhere
in this codebase so always the fallback — fail every real background
checked too. Not fixed: `marketTicker` is true only for the wallstreet
vocab entry (`ui/primitives.jsx`), so those spans never actually render
outside this theme. Confirmed dead CSS, not a live gap, same as the
`--office-ticker-bg` night variables the earlier entry already flagged.)

Run: python3 scripts/test_ticker_sep_contrast.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / 'styles.css'

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def srgb_to_linear(c):
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def rel_luminance(rgb):
    r, g, b = rgb
    return 0.2126 * srgb_to_linear(r) + 0.7152 * srgb_to_linear(g) + 0.0722 * srgb_to_linear(b)


def contrast(rgb1, rgb2):
    l1, l2 = rel_luminance(rgb1), rel_luminance(rgb2)
    hi, lo = (l1, l2) if l1 > l2 else (l2, l1)
    return (hi + 0.05) / (lo + 0.05)


def composite(fg, alpha, bg):
    return tuple(alpha * f + (1 - alpha) * b for f, b in zip(fg, bg))


def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def hsl_to_rgb(h, s, ll):
    s, ll = s / 100.0, ll / 100.0
    c = (1 - abs(2 * ll - 1)) * s
    x = c * (1 - abs(((h / 60.0) % 2) - 1))
    m = ll - c / 2
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][int(h // 60) % 6]
    return tuple((v + m) * 255 for v in (r, g, b))


def sep_rgb(color_str):
    """A `.sep` `color:` value — 6-hex solid or 8-hex with trailing alpha."""
    m = re.match(r'#([0-9a-fA-F]{6})([0-9a-fA-F]{2})?$', color_str.strip())
    assert m, f'unparsed color: {color_str}'
    rgb = hex_to_rgb('#' + m.group(1))
    alpha = (int(m.group(2), 16) / 255) if m.group(2) else 1.0
    return rgb, alpha


src = CSS.read_text()


def find_one(pattern, label):
    m = re.search(pattern, src)
    check(m, f'styles.css: could not find {label} (pattern: {pattern})')
    return m


# --- Resolve the four real ticker backgrounds from source -----------------

m_coffee = find_one(r'--brand-coffee:\s*hsl\(\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*\)', '--brand-coffee (default ticker bg, via var(--ink))')
bg_default = hsl_to_rgb(*(float(x) for x in m_coffee.groups())) if m_coffee else None

m_cs_bg = find_one(r'--office-ticker-bg:\s*(#[0-9a-fA-F]{6});\s*\n\s*--office-ticker-text:\s*#faf3e8;', 'coffeeshop --office-ticker-bg')
bg_coffeeshop = hex_to_rgb(m_cs_bg.group(1)) if m_cs_bg else None

m_ws_bg = find_one(r'--office-ticker-bg:\s*(#[0-9a-fA-F]{6});\s*\n\s*--office-ticker-text:\s*#00e0a0;', 'wallstreet --office-ticker-bg')
bg_wallstreet = hex_to_rgb(m_ws_bg.group(1)) if m_ws_bg else None

# `body.night .ticker` hardcodes background app-wide, overriding every
# theme's own --office-ticker-bg (see the fix's own comment in styles.css).
m_night_bg = find_one(r'body\.night \.ticker \{ background:\s*(#[0-9a-fA-F]{6});', 'body.night .ticker background')
bg_night = hex_to_rgb(m_night_bg.group(1)) if m_night_bg else None

# --- Resolve the four relevant .sep color rules ----------------------------

m_sep_base = find_one(r'\.ticker-track \.line \.sep \{ color:\s*(#[0-9a-fA-F]{6,8});', 'base .ticker-track .line .sep')
m_sep_cs = find_one(r'body\.theme-coffeeshop \.ticker-track \.line \.sep \{\s*color:\s*(#[0-9a-fA-F]{6,8});', 'body.theme-coffeeshop .ticker-track .line .sep')
m_sep_ws = find_one(r'body\.theme-wallstreet \.ticker-track \.line \.sep \{\s*color:\s*(#[0-9a-fA-F]{6,8});', 'body.theme-wallstreet .ticker-track .line .sep')
m_sep_night = find_one(r'body\.night \.ticker-track \.line \.sep \{ color:\s*(#[0-9a-fA-F]{6,8});', 'body.night .ticker-track .line .sep')
m_sep_ws_night = find_one(r'body\.theme-wallstreet\.night \.ticker-track \.line \.sep \{\s*color:\s*(#[0-9a-fA-F]{6,8});', 'body.theme-wallstreet.night .ticker-track .line .sep')

# --- Check each real combination (CSS cascade winner, not every rule) -----

cases = []
if bg_default and m_sep_base:
    cases.append(('default/sepia/solarized/dracula/highcontrast, day', sep_rgb(m_sep_base.group(1)), bg_default))
if bg_coffeeshop and m_sep_cs:
    cases.append(('coffeeshop, day', sep_rgb(m_sep_cs.group(1)), bg_coffeeshop))
if bg_wallstreet and m_sep_ws:
    cases.append(('wallstreet, day', sep_rgb(m_sep_ws.group(1)), bg_wallstreet))
if bg_night and m_sep_night:
    cases.append(('any non-wallstreet theme, night', sep_rgb(m_sep_night.group(1)), bg_night))
if bg_night and m_sep_ws_night:
    cases.append(('wallstreet, night', sep_rgb(m_sep_ws_night.group(1)), bg_night))

for label, (fg, alpha), bg in cases:
    effective = composite(fg, alpha, bg) if alpha < 1.0 else fg
    ratio = contrast(effective, bg)
    check(
        ratio >= 4.5,
        f'{label}: .sep measures {ratio:.2f}:1 against its real ticker '
        f'background {bg} — below WCAG AA\'s 4.5:1 floor for text.',
    )

# --- Market-quote colors: only wallstreet ever renders these -------------

m_up_ws = find_one(r'body\.theme-wallstreet \.ticker-track \.line \.mkt-up\s*\{\s*color:\s*(#[0-9a-fA-F]{6});', 'body.theme-wallstreet .mkt-up')
m_down_ws = find_one(r'body\.theme-wallstreet \.ticker-track \.line \.mkt-down\s*\{\s*color:\s*(#[0-9a-fA-F]{6});', 'body.theme-wallstreet .mkt-down')
m_down_ws_night = find_one(r'body\.theme-wallstreet\.night \.ticker-track \.line \.mkt-down\s*\{\s*color:\s*(#[0-9a-fA-F]{6});', 'body.theme-wallstreet.night .mkt-down')
# .kw has no wallstreet-specific override — inherits var(--accent-sun),
# already measured comfortably passing (8.71:1+) live, so not re-checked here.

mkt_cases = []
if bg_wallstreet and m_up_ws:
    mkt_cases.append(('wallstreet .mkt-up, day', hex_to_rgb(m_up_ws.group(1)), bg_wallstreet))
if bg_wallstreet and m_down_ws:
    mkt_cases.append(('wallstreet .mkt-down, day', hex_to_rgb(m_down_ws.group(1)), bg_wallstreet))
if bg_night and m_down_ws_night:
    mkt_cases.append(('wallstreet .mkt-down, night', hex_to_rgb(m_down_ws_night.group(1)), bg_night))

for label, fg, bg in mkt_cases:
    ratio = contrast(fg, bg)
    check(
        ratio >= 4.5,
        f'{label}: measures {ratio:.2f}:1 against its real ticker '
        f'background {bg} — below WCAG AA\'s 4.5:1 floor for text.',
    )

if failures:
    print("FAIL:")
    for f in failures:
        print(f" - {f}")
    raise SystemExit(1)

print("ALL PASS")
