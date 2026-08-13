#!/usr/bin/env python3
"""The Trading Floor theme's ticker separator failed WCAG AA contrast.

`.ticker-track .line .sep` (styles.css) already has an extensive comment
documenting a real accessibility fix for the DEFAULT theme's separator —
measured at 3.38:1 against the ticker's dark background, raised to 5.48:1.
The `theme-wallstreet` override of the same selector was never put through
that same analysis: `#00e0a060` (37.6% alpha) against this theme's own
`--office-ticker-bg` (#0a0a1a) measures at 2.42:1 — well under WCAG AA's
4.5:1 floor, and actually worse than the failure the base rule was fixed
for.

Fixed by raising the alpha (same hue, same green) to land at 5.51:1 --
matching the base rule's own 5.48:1 target rather than picking a new
number by eye. Verified with the WCAG relative-luminance formula, not
eyeballed: see the calculation this test re-derives.

Run: python3 scripts/test_ticker_wallstreet_contrast.py
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


src = CSS.read_text()

# Pull the wallstreet ticker background and the separator override, so
# this test tracks the real values rather than hardcoding a duplicate.
m_bg = re.search(r'--office-ticker-bg:\s*(#[0-9a-fA-F]{6});[^}]*\n\s*--office-ticker-text:\s*#00e0a0;', src)
check(m_bg, "styles.css: could not find the wallstreet theme's "
            "--office-ticker-bg (identified by its --office-ticker-text: #00e0a0 neighbor).")

m_sep = re.search(r'body\.theme-wallstreet \.ticker-track \.line \.sep \{\s*color:\s*(#[0-9a-fA-F]{6})([0-9a-fA-F]{2})?;', src)
check(m_sep, "styles.css: could not find `body.theme-wallstreet .ticker-track .line .sep`.")

if m_bg and m_sep:
    bg = hex_to_rgb(m_bg.group(1))
    fg_hex = m_sep.group(1)
    alpha_hex = m_sep.group(2)
    fg = hex_to_rgb(fg_hex)
    alpha = (int(alpha_hex, 16) / 255) if alpha_hex else 1.0
    effective = composite(fg, alpha, bg) if alpha < 1.0 else fg
    ratio = contrast(effective, bg)
    check(
        ratio >= 4.5,
        f"body.theme-wallstreet .ticker-track .line .sep measures {ratio:.2f}:1 "
        f"against --office-ticker-bg {m_bg.group(1)} — below WCAG AA's 4.5:1 floor "
        f"for text. (color: {fg_hex}{alpha_hex or ''}, alpha={alpha:.3f})",
    )

if failures:
    print("FAIL:")
    for f in failures:
        print(f" - {f}")
    raise SystemExit(1)

print("ALL PASS")
