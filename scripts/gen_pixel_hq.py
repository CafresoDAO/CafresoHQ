#!/usr/bin/env python3
"""Generate the Pixel HQ asset pack (assets/px/*.png).

The office floor renders as a GBA-era pixel-art building cutaway (see
docs/OFFICE_AS_INTERFACE.md §1 — this is the same office, drawn honestly
in tiles). Every asset ships as a tiny 1x-scale PNG; the CSS scales by
integer factors with image-rendering:pixelated.

Pure stdlib (zlib + struct): no Pillow, no sips — runs the same on the
Windows entry points as on macOS. Deterministic: a fixed-seed LCG drives
the skyline variety, so re-running the script is byte-stable.

Art pipeline: sprites are authored as ASCII pixel specs in this file
(one char = one pixel), which doubles as a per-pixel authorship trail —
everything here is original work in the era's *grammar*, no Nintendo /
Game Freak assets or trade dress.

Run:  python3 scripts/gen_pixel_hq.py
Then: npm run build (the JSX references the files by name)
"""
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'assets', 'px')
ASSETS = os.path.join(ROOT, 'assets')

# ── PNG reader (for tracing the real wordmark into the rooftop sign) ───────

def read_png(path):
    """Decode an 8-bit RGB/RGBA PNG. Returns (w, h, channels, rows) where
    each row is a bytearray of interleaved channel bytes. Same pure-stdlib
    approach as write_png — no Pillow, so this stays a source-controlled
    asset the generator can re-derive deterministically, not a runtime dep."""
    data = open(path, 'rb').read()
    pos = 8
    w = h = bitdepth = colortype = None
    idat = b''
    while pos < len(data):
        ln = struct.unpack('>I', data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if tag == b'IHDR':
            w, h, bitdepth, colortype = struct.unpack('>IIBB', body[:10])
        elif tag == b'IDAT':
            idat += body
        pos += 12 + ln
    assert bitdepth == 8, 'only 8-bit PNGs supported: %s' % path
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colortype]
    raw = zlib.decompress(idat)
    stride = w * channels
    prev = bytearray(stride)
    rows = []
    p = 0
    for _y in range(h):
        f = raw[p]; p += 1
        line = bytearray(raw[p:p + stride]); p += stride
        if f == 1:
            for i in range(channels, stride): line[i] = (line[i] + line[i - channels]) & 255
        elif f == 2:
            for i in range(stride): line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                pp = a + b - c
                pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        prev = line
        rows.append(line)
    return w, h, channels, rows


# ── PNG writer ────────────────────────────────────────────────────────────

def write_png(path, w, h, pixels):
    """pixels: list of rows, each row a list of (r,g,b,a) tuples."""
    raw = b''.join(
        b'\x00' + b''.join(struct.pack('4B', *px) for px in row)
        for row in pixels)
    def chunk(tag, data):
        c = tag + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(raw, 9))
           + chunk(b'IEND', b''))
    with open(path, 'wb') as fh:
        fh.write(png)


class Canvas:
    def __init__(self, w, h, fill=None):
        self.w, self.h = w, h
        f = fill if fill else (0, 0, 0, 0)
        if len(f) == 3:
            f = f + (255,)
        self.px = [[f for _ in range(w)] for _ in range(h)]

    def set(self, x, y, c):
        if c is None or x < 0 or y < 0 or x >= self.w or y >= self.h:
            return
        if len(c) == 3:
            c = c + (255,)
        self.px[y][x] = c

    def rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.set(xx, yy, c)

    def blit_ascii(self, rows, pal, ox=0, oy=0):
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                c = pal.get(ch)
                if c is not None:
                    self.set(ox + x, oy + y, c)

    def blit(self, other, ox, oy):
        for y in range(other.h):
            for x in range(other.w):
                r, g, b, a = other.px[y][x]
                if a > 0:
                    self.set(ox + x, oy + y, (r, g, b, a))

    def save(self, name):
        write_png(os.path.join(OUT, name), self.w, self.h, self.px)


def hx(s):
    s = s.lstrip('#')
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)


def art(rows, w):
    """Validate an ASCII sprite: rows may run short (padded with transparent)
    but never long — a long row means the art is genuinely misdrawn."""
    out = []
    for i, r in enumerate(rows):
        assert len(r) <= w, 'row %d is %d chars, want <=%d: %r' % (i, len(r), w, r)
        out.append(r.ljust(w, '.'))
    return out


class LCG:
    """Tiny deterministic PRNG so skylines are byte-stable across runs."""
    def __init__(self, seed=0xCAFE50):
        self.s = seed

    def next(self):
        self.s = (self.s * 1103515245 + 12345) & 0x7fffffff
        return self.s

    def rint(self, lo, hi):
        return lo + self.next() % (hi - lo + 1)

    def pick(self, xs):
        return xs[self.next() % len(xs)]


# ── Shared palette (furniture / scenery) ────────────────────────────────────
K = hx('1a1c2c')          # blue-black outline (era-authentic, not pure black)
PAL = {
    '.': None,
    'K': K,
    'w': hx('c8945c'), 'W': hx('a06a3c'), 'x': hx('7a4a28'),   # wood
    'c': hx('f0e0c0'), 'C': hx('d8c8a0'),                       # cream wall
    'g': hx('a8d8e8'), 'G': hx('78b0cc'),                       # glass
    'f': hx('4a5568'),                                          # frame
    'm': hx('9aa4b8'), 'M': hx('6a7488'),                       # metal
    'r': hx('d84848'), 'R': hx('962830'),                       # red
    'b': hx('4878c8'), 'B': hx('28488c'),                       # blue
    'l': hx('58a858'), 'L': hx('3a7a3c'),                       # leaf
    'p': hx('b06a3c'),                                          # pot / trunk
    'y': hx('f8c840'), 'Y': hx('8a6a20'),                       # gold
    'd': hx('3a2c20'), 'D': hx('241a12'),                       # dark board
    'e': hx('f4ecd8'), 'E': hx('d8ccb0'),                       # paper
    'n': hx('2a3048'), 'o': hx('f8e8a0'),                       # night / lit
    's': hx('5a6e8c'), 'S': hx('46587a'),                       # slate
    'q': hx('ffffff'),
    'v': hx('7a5a9c'), 'V': hx('684a88'),                       # violet (CEO)
    'h': hx('d8a868'), 'H': hx('c99a5e'),                       # floor wood
    'a': hx('58c8d8'),                                          # screen aqua
    'i': hx('e86a8a'),                                          # pink accent
    't': hx('c8b490'),                                          # facade shade
}


# ── Characters — 16×24 GBA-proportioned, 7 poses ────────────────────────────
# Legend matches sprites.jsx: K outline · h/H hair · S/s skin · k pupil ·
# m mouth · c/C shirt · p/P pants · z shoe. Poses (sheet order):
#   0 back (at the desk, working) · 1 front idle A · 2 front idle B (blink)
#   3 side walk A · 4 side walk B · 5 stretch (done) · 6 stuck (snag)
CHAR_W, CHAR_H = 16, 24

FRONT_A = art([
    '................',
    '................',
    '.....KKKKKK.....',
    '...KKhhhhhhKK...',
    '..KhhhhhhhhhhK..',
    '..KhhhhhhhhhhK..',
    '.KhHhhhhhhhhHhK.',
    '.KhhSSSSSSSShhK.',
    '.KhSSkSSSSkSShK.',
    '.KhSSSSSSSSSShK.',
    '..KSSsSSSSsSSK..',
    '..KSSSSmmSSSSK..',
    '...KSSSSSSSSK...',
    '....KKKKKKKK....',
    '...KccccccccK...',
    '..KcCccccccCcK..',
    '.KsKccccccccKsK.',
    '.KKKcCccccCcKKK.',
    '...KccccccccK...',
    '...KppppppppK...',
    '...KpPppppPppK..',
    '...KppKKKKppK...',
    '...KzzK..KzzK...',
    '...KKKK..KKKK...',
], CHAR_W)

FRONT_B = art([
    '................',
    '................',
    '................',
    '.....KKKKKK.....',
    '...KKhhhhhhKK...',
    '..KhhhhhhhhhhK..',
    '..KhhhhhhhhhhK..',
    '.KhHhhhhhhhhHhK.',
    '.KhhSSSSSSSShhK.',
    '.KhSSsSSSSsSShK.',
    '.KhSSSSSSSSSShK.',
    '..KSSSSmmSSSSK..',
    '...KSSSSSSSSK...',
    '....KKKKKKKK....',
    '...KccccccccK...',
    '..KcCccccccCcK..',
    '.KsKccccccccKsK.',
    '.KKKcCccccCcKKK.',
    '...KccccccccK...',
    '...KppppppppK...',
    '...KpPppppPppK..',
    '...KppKKKKppK...',
    '...KzzK..KzzK...',
    '...KKKK..KKKK...',
], CHAR_W)

BACK = art([
    '................',
    '................',
    '.....KKKKKK.....',
    '...KKhhhhhhKK...',
    '..KhhhhhhhhhhK..',
    '..KhhhhhhhhhhK..',
    '.KhhhhhhhhhhhhK.',
    '.KhHhhhhhhhhHhK.',
    '.KhhhhhhhhhhhhK.',
    '.KhhhhhhhhhhhhK.',
    '..KhHhhhhhhHhK..',
    '..KhhhhhhhhhhK..',
    '...KhhhhhhhhK...',
    '....KKKKKKKK....',
    '...KccccccccK...',
    '..KcCccccccCcK..',
    '..KccccccccccK..',
    '..KcCccccccCcK..',
    '...KccccccccK...',
    '...KppppppppK...',
    '...KpPppppPppK..',
    '...KppKKKKppK...',
    '...KzzK..KzzK...',
    '...KKKK..KKKK...',
], CHAR_W)

# Side profile, facing RIGHT (CSS scaleX(-1) turns them left).
SIDE_A = art([
    '................',
    '................',
    '.....KKKKKK.....',
    '....KhhhhhhK....',
    '...KhhhhhhhhK...',
    '..KhhhhhhhhhhK..',
    '..KhHhhhhhhhhK..',
    '..KhhhhhSSSSSK..',
    '..KhhhhSSkSSSK..',
    '..KhhhhSSSSSSK..',
    '..KhHhhSSSsSK...',
    '...KhhhSSSSK....',
    '....KKKKKKK.....',
    '....KccccccK....',
    '...KcCcccccK....',
    '...KccccccsK....',
    '...KcCccccKK....',
    '....KccccccK....',
    '....KppppppK....',
    '...KppPpppK.....',
    '...KppKKppK.....',
    '..KppK..KppK....',
    '..KzzK...KzzK...',
    '..KKKK...KKKK...',
], CHAR_W)

SIDE_B = art([
    '................',
    '................',
    '................',
    '.....KKKKKK.....',
    '....KhhhhhhK....',
    '...KhhhhhhhhK...',
    '..KhhhhhhhhhhK..',
    '..KhHhhhhhhhhK..',
    '..KhhhhhSSSSSK..',
    '..KhhhhSSkSSSK..',
    '..KhhhhSSSSSSK..',
    '..KhHhhSSSsSK...',
    '...KhhhSSSSK....',
    '....KKKKKKK.....',
    '....KccccccK....',
    '...KcCcccccK....',
    '...KsccccccK....',
    '...KKcCccccK....',
    '....KccccccK....',
    '....KppppppK....',
    '.....KpPppK.....',
    '.....KppppK.....',
    '.....KppppK.....',
    '.....KzzzzK.....',
], CHAR_W)

STRETCH = art([
    '................',
    '................',
    '.....KKKKKK.....',
    '..KKKhhhhhhKKK..',
    '.KssKhhhhhhKssK.',
    '.KssKhhhhhhKssK.',
    '..KKhHhhhhHhKK..',
    '..KchSSSSSShcK..',
    '..KcKSkSSkSKcK..',
    '..KcKSSSSSSKcK..',
    '...KKSsmmsSKK...',
    '....KSSSSSSK....',
    '....KKKKKKKK....',
    '...KccccccccK...',
    '..KcCccccccCcK..',
    '..KccccccccccK..',
    '..KcCccccccCcK..',
    '...KccccccccK...',
    '...KppppppppK...',
    '...KpPppppPppK..',
    '...KppKKKKppK...',
    '...KzzK..KzzK...',
    '...KKKK..KKKK...',
    '................',
], CHAR_W)

STUCK = art([
    '................',
    '................',
    '................',
    '................',
    '.....KKKKKK...U.',
    '...KKhhhhhhKK.U.',
    '..KhhhhhhhhhhK..',
    '..KhhhhhhhhhhK..',
    '.KhHhhhhhhhhHhK.',
    '.KhhhhhhhhhhhhK.',
    '.KhSShhhhhhSShK.',
    '.KhSSSSSSSSSShK.',
    '..KSSsSSSSsSSK..',
    '...KSSSmmSSSK...',
    '....KKKKKKKK....',
    '...KccccccccK...',
    '..KcCccccccCcK..',
    '.KscccccccccsK..',
    '.KKcCccccccCKK..',
    '...KccccccccK...',
    '...KppppppppK...',
    '...KpPppppPppK..',
    '...KzzK..KzzK...',
    '...KKKK..KKKK...',
], CHAR_W)

POSES = [BACK, FRONT_A, FRONT_B, SIDE_A, SIDE_B, STRETCH, STUCK]

# Mirrors sprites.jsx HUMANS — same hair/shirt hexes so every coworker keeps
# their exact identity across the migration.
CHAR_BASE = {
    'K': hx('2b1f22'), 'S': hx('f3cfa9'), 's': hx('d9a97e'),
    'k': hx('3b2e2a'), 'm': hx('7a4a36'),
    'p': hx('4a3a5e'), 'P': hx('2e2340'), 'z': hx('2b1f22'),
    'U': hx('58c8d8'),   # sweat drop (stuck pose)
    '.': None,
}
HUMANS = {
    'cafresohq': ('4b2e1f', '2a1510', '8a5a9b', '5e3e6c'),
    'rose':      ('3a2420', '1e1410', 'e8a9a9', 'b36b6b'),
    'teal':      ('2e1c14', '15100a', '7db5b5', '4d8a8a'),
    'sun':       ('c48a3e', '7a5120', 'f0c674', 'b38a44'),
    'leaf':      ('1c1410', '0c0806', '8bb98a', '567a56'),
    'sky':       ('5a3a28', '331e12', '89c8e0', '5a98b0'),
    'mint':      ('2c1a10', '120804', 'b6e0c8', '6fa890'),
    'blush':     ('6a3a28', '3a1c12', 'f3c1b2', 'b87866'),
    'lavender':  ('3a2c20', '1e140c', 'b6a8e0', '7d6bb0'),
}


def gen_chars():
    for name, (h, H, c, C) in HUMANS.items():
        pal = dict(CHAR_BASE)
        pal.update({'h': hx(h), 'H': hx(H), 'c': hx(c), 'C': hx(C)})
        sheet = Canvas(CHAR_W * len(POSES), CHAR_H)
        for i, pose in enumerate(POSES):
            sheet.blit_ascii(pose, pal, ox=i * CHAR_W)
        sheet.save('char_%s.png' % name)


# ── Maximus — shiba-style pixel dog, side view, 2 walk frames + sit ─────────
DOG_A = art([
    '................',
    '....KK.....KK...',
    '...KffK...KffK..',
    '...KfffKKKfffK..',
    '..KfffffffffffK.',
    '..KfWfffffWffK..',
    '..KfffffffffqKK.',
    '..KffffffffqqqK.',
    '..KKffffffKqKK..',
    'KK.KffffffKK....',
    'KfKKffffffK.....',
    'KffffffffffK....',
    '.KKffffffffK....',
    '..KffKKKKffK....',
    '..KzzK..KzzK....',
    '..KKK...KKK.....',
], 16)
DOG_B = art([
    '................',
    '....KK.....KK...',
    '...KffK...KffK..',
    '...KfffKKKfffK..',
    '..KfffffffffffK.',
    '..KfWfffffWffK..',
    '..KfffffffffqKK.',
    '..KffffffffqqqK.',
    '..KKffffffKqKK..',
    '.K.KffffffKK....',
    'KfKKffffffK.....',
    '.KffffffffffK...',
    '..KKffffffffK...',
    '..KffKK.KKffK...',
    '.KzzK....KzzK...',
    '.KKK.....KKK....',
], 16)


def gen_dog():
    pal = {'.': None, 'K': hx('2b1f22'), 'f': hx('d4903a'),
           'W': hx('fffaf0'), 'q': hx('f4ecd8'), 'z': hx('7a4a28')}
    sheet = Canvas(32, 16)
    sheet.blit_ascii(DOG_A, pal, 0, 0)
    sheet.blit_ascii(DOG_B, pal, 16, 0)
    sheet.save('char_maximus.png')


# ── Furniture ────────────────────────────────────────────────────────────────
def sprite(name, w, rows, extra=None):
    pal = dict(PAL)
    if extra:
        pal.update({k: hx(v) for k, v in extra.items()})
    cv = Canvas(w, len(rows))
    cv.blit_ascii(art(rows, w), pal)
    cv.save(name + '.png')
    return cv


def gen_furniture():
    # Agent desk — front-facing, monitor + keyboard. Monitor screen pixels are
    # the 'a' block: the CSS live-glow overlay sits exactly there (x=9..18,y=2..8).
    sprite('desk_agent', 28, [
        '........KKKKKKKKKKKK........',
        '........KffffffffffK........',
        '........KfaaaaaaaafK........',
        '........KfaaaaaaaafK........',
        '........KfaaaaaaaafK........',
        '........KfaaaaaaaafK........',
        '........KffffffffffK........',
        '........KKKKKKKKKKKK........',
        '.............KK.............',
        '...........KKmmKK...........',
        'KKKKKKKKKKKKKKKKKKKKKKKKKKKK',
        'KwwwwwwwwwwwwwwwwwwwwwwwwwwK',
        'KWWWWWWWWWWWWWWWWWWWWWWWWWWK',
        'KWmmmmmmWWWWWWWWWWWWeeWWWWWK',
        'KWmKmKmmWWWWWWWWWWWWeEWWWWWK',
        'KWWWWWWWWWWWWWWWWWWWWWWWWWWK',
        'KxxKKKKKKKKKKKKKKKKKKKKKKxxK',
        'KxxK....................KxxK',
        'KxxK....................KxxK',
        'KKKK....................KKKK',
    ])
    # CEO desk — wide, dark wood, twin monitor + banker's lamp.
    sprite('desk_ceo', 36, [
        '......KKKKKKKKKKKK......KKKK........',
        '......KffffffffffK......KyyK........',
        '......KfaaaaaaaafK......KyyK........',
        '......KfaaaaaaaafK.......KK.........',
        '......KfaaaaaaaafK.......KK.........',
        '......KffffffffffK......KKKK........',
        '......KKKKKKKKKKKK......KYYK........',
        '...........KK...........KKKK........',
        '.........KKmmKK.....................',
        'KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK',
        'KxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxK',
        'KxWxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxWxK',
        'KxWmmmmmmxxxxxxxxxxxxxxxxxxeeexxxWxK',
        'KxWmKmKmmxxxxxxxxxxxxxxxxxxeEexxxWxK',
        'KxWxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxWxK',
        'KxxKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKxxK',
        'KxxK............................KxxK',
        'KxxK............................KxxK',
        'KKKK............................KKKK',
    ])
    sprite('bookshelf', 20, [
        'KKKKKKKKKKKKKKKKKKKK',
        'KwwwwwwwwwwwwwwwwwwK',
        'KwKKKKKKKKKKKKKKKKwK',
        'KwKrrKbbKyyKllKiiKwK',
        'KwKrRKbBKyYKlLKiiKwK',
        'KwKrRKbBKyYKlLKiiKwK',
        'KwKKKKKKKKKKKKKKKKwK',
        'KwwwwwwwwwwwwwwwwwwK',
        'KwKKKKKKKKKKKKKKKKwK',
        'KwKbbKiiKllKrrKyyKwK',
        'KwKbBKiiKlLKrRKyYKwK',
        'KwKbBKiiKlLKrRKyYKwK',
        'KwKKKKKKKKKKKKKKKKwK',
        'KwwwwwwwwwwwwwwwwwwK',
        'KwKKKKKKKKKK......wK',
        'KwKllKyyKrrK......wK',
        'KwKlLKyYKrRK......wK',
        'KwKKKKKKKKKK......wK',
        'KWWWWWWWWWWWWWWWWWWK',
        'KKKKKKKKKKKKKKKKKKKK',
    ])
    sprite('cabinet', 16, [
        'KKKKKKKKKKKKKKKK',
        'KmmmmmmmmmmmmmmK',
        'KmKKKKKKKKKKKKmK',
        'KmKMMMMMMMMMMKmK',
        'KmKMMKKKKMMMMKmK',
        'KmKMMMMMMMMMMKmK',
        'KmKKKKKKKKKKKKmK',
        'KmKMMMMMMMMMMKmK',
        'KmKMMKKKKMMMMKmK',
        'KmKMMMMMMMMMMKmK',
        'KmKKKKKKKKKKKKmK',
        'KmKMMMMMMMMMMKmK',
        'KmKMMKKKKMMMMKmK',
        'KmKMMMMMMMMMMKmK',
        'KmKKKKKKKKKKKKmK',
        'KMMMMMMMMMMMMMMK',
        'KKKKKKKKKKKKKKKK',
    ])
    sprite('plant', 12, [
        '....KKKK....',
        '..KKllllKK..',
        '.KlllLllllK.',
        'KllLlllllLlK',
        'KlllllLllllK',
        'KLlllllllLlK',
        '.KllLlllllK.',
        '..KKllllKK..',
        '...KKllKK...',
        '....KKKK....',
        '...KppppK...',
        '...KppppK...',
        '..KpppppKK..',
        '..KKKKKKKK..',
    ])
    sprite('cooler', 12, [
        '..KKKKKKKK..',
        '.KggggggggK.',
        '.KgGggggGgK.',
        '.KggggggggK.',
        '.KgGggggggK.',
        '.KKKKKKKKKK.',
        '.KmmmmmmmmK.',
        '.KmKKKKKKmK.',
        '.KmKggggKmK.',
        '.KmKKKKKKmK.',
        '.KmmmmmmmmK.',
        '.KmmmmmmmmK.',
        '.KMMMMMMMMK.',
        '..KK....KK..',
        '..KK....KK..',
    ])
    sprite('couch', 28, [
        '.KKKKKKKKKKKKKKKKKKKKKKKKKK',
        'KbbbbbbbbbbbbbbbbbbbbbbbbbbK',
        'KbBbbbbbbbBbbbbbbbbBbbbbbbbK',
        'KbbbbbbbbbbbbbbbbbbbbbbbbbbK',
        'KKKKKKKKKKKKKKKKKKKKKKKKKKKK',
        'KbbBbbbbbbbbBbbbbbbbbBbbbbbK',
        'KbbbbbbbbbbbbbbbbbbbbbbbbbbK',
        'KKKKKKKKKKKKKKKKKKKKKKKKKKKK',
        '.KxxK...................KxxK'[:28],
        '.KKKK...................KKKK'[:28],
    ])
    sprite('corkboard', 26, [
        'KKKKKKKKKKKKKKKKKKKKKKKKKK',
        'KwwwwwwwwwwwwwwwwwwwwwwwwK',
        'KwttttttttttttttttttttttwK',
        'KwtteetttteEttttrrttttttwK',
        'KwtteetttteEttttrRttttttwK',
        'KwttttttttttttttttttttttwK',
        'KwttEettttbbttttteetttttwK',
        'KwttEettttbBttttteetttttwK',
        'KwttttttttttttttttttttttwK',
        'KwwwwwwwwwwwwwwwwwwwwwwwwK',
        'KKKKKKKKKKKKKKKKKKKKKKKKKK',
    ])
    # Night Shift bulletin — dark board, moon pixel.
    sprite('nightboard', 24, [
        'KKKKKKKKKKKKKKKKKKKKKKKK',
        'KxxxxxxxxxxxxxxxxxxxxxxK',
        'KxnnnnnnnnnnnnnnnnnnnnxK',
        'KxnnooonnnnnnnnnnnnnnnxK',
        'KxnoonnnnnnneeeeeennnnxK',
        'KxnoonnnnnnnnnnnnnnnnnxK',
        'KxnnooonnnneeeeeeeennnxK',
        'KxnnnnnnnnnnnnnnnnnnnnxK',
        'KxnnnnnnnnneeeennnnnnnxK',
        'KxnnnnnnnnnnnnnnnnnnnnxK',
        'KxxxxxxxxxxxxxxxxxxxxxxK',
        'KKKKKKKKKKKKKKKKKKKKKKKK',
    ])
    sprite('vaultdoor', 26, [
        '.KKKKKKKKKKKKKKKKKKKKKKK.',
        'KmmmmmmmmmmmmmmmmmmmmmmmK',
        'KmMMMMMMMMMMMMMMMMMMMMmmK',
        'KmMKKKKKKKKKKKKKKKKKKMmmK',
        'KmMKmmmmmmmmmmmmmmmmKMmmK',
        'KmMKmmKKKKKKKKKKmmmmKMmmK',
        'KmMKmmKmmmmmmmmKmmmmKMmmK',
        'KmMKmmKmmKKKKmmKmmmmKMmmK',
        'KmMKmmKmmKyyKmmKmmmmKMmmK',
        'KmMKmmKmmKyyKmmKmmmmKMmmK',
        'KmMKmmKmmKKKKmmKmmmmKMmmK',
        'KmMKmmKmmmmmmmmKmmmmKMmmK',
        'KmMKmmKKKKKKKKKKmmmmKMmmK',
        'KmMKmmmmmmmmmmmmmmmmKMmmK',
        'KmMKKKKKKKKKKKKKKKKKKMmmK',
        'KmMMMMMMMMMMMMMMMMMMMMmmK',
        'KmmmmmmmmmmmmmmmmmmmmmmmK',
        '.KKKKKKKKKKKKKKKKKKKKKKK.',
    ])
    sprite('goldbar', 10, [
        '.KKKKKKKK.',
        'KyyyyyyyyK',
        'KyYyyyyYyK',
        'KyyyyyyyyK',
        'KYYYYYYYYK',
        '.KKKKKKKK.',
    ])
    sprite('arcade', 18, [
        '.KKKKKKKKKKKKKKK..',
        'KrrrrrrrrrrrrrrrK.',
        'KrRyyRRyyRRyyRrrK.',
        'KrrrrrrrrrrrrrrrK.',
        'KKKKKKKKKKKKKKKKK.',
        'KMKnnnnnnnnnnnKMK.',
        'KMKnannnnnnannKMK.',
        'KMKnnnnaannnnnKMK.',
        'KMKnannnnnnannKMK.',
        'KMKnnnnnnnnnnnKMK.',
        'KMKKKKKKKKKKKKKMK.',
        'KMMMMMMMMMMMMMMMK.',
        'KMKmmKMMMMKrKKrKK.',
        'KMKmKKMMMMKKKKKKK.',
        'KMMMMMMMMMMMMMMMK.',
        'KRRRRRRRRRRRRRRRK.',
        'KRRRRRRRRRRRRRRRK.',
        'KKKKKKKKKKKKKKKKK.',
    ])
    # Interior window — day glass w/ crossbar; night version is lamplit.
    sprite('window_day', 18, [
        'KKKKKKKKKKKKKKKKKK',
        'KffffffffffffffffK',
        'KfggggggggGgggggfK',
        'KfgggggggGggggggfK',
        'KfggqgggGgggggggfK',
        'KffffffffffffffffK',
        'KfggggGgggggggggfK',
        'KfgggGgggggqggggfK',
        'KfggGgggggggggggfK',
        'KfggggggggggggggfK',
        'KffffffffffffffffK',
        'KKKKKKKKKKKKKKKKKK',
    ])
    sprite('window_night', 18, [
        'KKKKKKKKKKKKKKKKKK',
        'KffffffffffffffffK',
        'KfnnnnnnnnnnnnnnfK',
        'KfnnonnnnnnnnnnnfK',
        'KfnnnnnnnnonnnnnfK',
        'KffffffffffffffffK',
        'KfnnnnnonnnnnnnnfK',
        'KfnnnnnnnnnnonnnfK',
        'KfnnonnnnnnnnnnnfK',
        'KfnnnnnnnnnnnnnnfK',
        'KffffffffffffffffK',
        'KKKKKKKKKKKKKKKKKK',
    ])
    sprite('clock', 10, [
        '..KKKKKK..',
        '.KeeeeeeK.',
        'KeeeKeeeeK',
        'KeeeKeeeeK',
        'KeeeKKKeeK',
        'KeeeeeeeeK',
        'KeeeeeeeeK',
        '.KeeeeeeK.',
        '..KKKKKK..',
        '..........',
    ])
    sprite('mug', 6, [
        '.KKK..',
        'KrrrKK',
        'KrrrK.',
        'KrRrKK',
        '.KKK..',
        '......',
    ])
    sprite('papers', 10, [
        '.KKKKKKK..',
        'KeeeeeeeK.',
        'KeEEEeeeK.',
        'KeeeeeeeKK',
        'KeEEeeeeeK',
        'KeeeeeeeeK',
        '.KKKKKKKK.',
    ])
    sprite('tray', 12, [
        'K..........K',
        'KKKKKKKKKKKK',
        'KmeeeeeeeemK',
        'KmeEEEeeeemK',
        'KmmmmmmmmmmK',
        'KKKKKKKKKKKK',
    ])
    sprite('meetdoor', 16, [
        'KKKKKKKKKKKKKKKK',
        'KwwwwwwwwwwwwwwK',
        'KwWWWWWWWWWWWWwK',
        'KwWggggggggggWwK',
        'KwWgGggggggGgWwK',
        'KwWggggggggggWwK',
        'KwWWWWWWWWWWWWwK',
        'KwWWWWWWWWWWWWwK',
        'KwWWWWWWWyyWWWwK',
        'KwWWWWWWWyyWWWwK',
        'KwWWWWWWWWWWWWwK',
        'KwWWWWWWWWWWWWwK',
        'KwWWWWWWWWWWWWwK',
        'KwWWWWWWWWWWWWwK',
        'KwWWWWWWWWWWWWwK',
        'KwwwwwwwwwwwwwwK',
        'KKKKKKKKKKKKKKKK',
    ])
    # Street furniture — the Japan-town flavor.
    sprite('lamp', 10, [
        '.KKKKKK...',
        'KooooooK..',
        'KooooooK..',
        'KooooooK..',
        '.KKKKKK...',
        '...KK.....',
        '...KK.....',
        '...KK.....',
        '...KK.....',
        '...KK.....',
        '...KK.....',
        '...KK.....',
        '...KK.....',
        '...KK.....',
        '...KK.....',
        '...KK.....',
        '..KKKK....',
        '.KKKKKK...',
    ], extra={'o': 'f8e8a0'})
    sprite('tree', 20, [
        '......KKKKKK........',
        '....KKllllllKK......',
        '...KlllLllllllK.....',
        '..KllllllllLlllK....',
        '.KlLllllllllllllK...',
        '.KlllllLlllLllllK...',
        'KllllLlllllllllllK..',
        'KlLlllllllLllllllK..',
        'KllllllLllllllLllK..',
        '.KlllllllllllllK....',
        '..KKllLlllllKKK.....',
        '....KKllllKK........',
        '......KppK..........',
        '......KppK..........',
        '......KppK..........',
        '.....KppppK.........',
        '....KKKKKKKK........',
    ])
    sprite('vending', 14, [
        'KKKKKKKKKKKKKK',
        'KrrrrrrrrrrrrK',
        'KrKKKKKKKKKKrK',
        'KrKooooooooKrK',
        'KrKoKoKoKooKrK',
        'KrKooooooooKrK',
        'KrKKKKKKKKKKrK',
        'KrrrrrrrrrrrrK',
        'KrKKKKKrKKKKrK',
        'KrKgggKrKnnKrK',
        'KrKKKKKrKKKKrK',
        'KrrrrrrrrrrrrK',
        'KRRRRRRRRRRRRK',
        'KKKKKKKKKKKKKK',
    ])
    sprite('bush', 14, [
        '...KKKKKKK....',
        '.KKlllllllKK..',
        'KlllLllllLllK.',
        'KllllllLllllK.',
        'KlLllllllllLK.',
        '.KKKKKKKKKKK..',
    ])
    sprite('doors', 24, [
        'KKKKKKKKKKKKKKKKKKKKKKKK',
        'KffffffffffKKffffffffffK',
        'KfggggggggfKKfggggggggfK',
        'KfgGgggggGfKKfGgggggGgfK',
        'KfggggggggfKKfggggggggfK',
        'KfggggggggfKKfggggggggfK',
        'KfgGggggggfKKfggggggGgfK',
        'KffffffffffKKffffffffffK',
        'KfggggggggfKKfggggggggfK',
        'KfggggggyyfKKfyyggggggfK',
        'KfgGgggggGfKKfGgggggGgfK',
        'KfggggggggfKKfggggggggfK',
        'KfggggggggfKKfggggggggfK',
        'KfggggggggfKKfggggggggfK',
        'KffffffffffKKffffffffffK',
        'KKKKKKKKKKKKKKKKKKKKKKKK',
    ])


# ── Rooftop sign — "CAFRESO HQ" in a 5×7 pixel font, gold on coffee ─────────
FONT = {
    'A': ['01110', '10001', '10001', '11111', '10001', '10001', '10001'],
    'C': ['01110', '10001', '10000', '10000', '10000', '10001', '01110'],
    'E': ['11111', '10000', '11110', '10000', '10000', '10000', '11111'],
    'F': ['11111', '10000', '11110', '10000', '10000', '10000', '10000'],
    'H': ['10001', '10001', '11111', '10001', '10001', '10001', '10001'],
    'O': ['01110', '10001', '10001', '10001', '10001', '10001', '01110'],
    'Q': ['01110', '10001', '10001', '10001', '10101', '10010', '01101'],
    'R': ['11110', '10001', '11110', '10100', '10010', '10001', '10001'],
    'S': ['01111', '10000', '01110', '00001', '00001', '10001', '01110'],
    ' ': ['00000', '00000', '00000', '00000', '00000', '00000', '00000'],
}


def trace_wordmark(target_w, threshold_core=0.55, threshold_rim=0.15):
    """Downsample the real brand wordmark (assets/cafreso-wordmark-alpha.png)
    into a small pixel-art coverage grid, area-averaging alpha per target
    cell. This traces the ACTUAL script logo — not a font approximation —
    so the rooftop sign is genuinely "the same style" rather than a lookalike.
    Returns (grid, target_h) where grid[y][x] is 0..1 coverage."""
    w, h, ch, rows = read_png(os.path.join(ASSETS, 'cafreso-wordmark-alpha.png'))
    a_off = ch - 1  # alpha is the last channel in RGBA

    def alpha_at(x, y):
        return rows[y][x * ch + a_off]

    # The source PNG carries a second, smaller subtitle lockup ("A BLOCKCHAIN
    # DAO") below the script wordmark, separated by a clean zero-ink gap —
    # find it and only trace above it, or the sign would drag in a faint
    # ghost of that second lockup.
    row_ink = [sum(1 for x in range(0, w, 2) if alpha_at(x, y) > 40) for y in range(h)]
    wordmark_bottom = h
    for y in range(1, h):
        if row_ink[y] == 0 and row_ink[y - 1] > 0:
            wordmark_bottom = y
            break

    # Crop to the glyph's own bounding box so the sign isn't mostly padding.
    bx0, by0, bx1, by1 = w, h, 0, 0
    for y in range(0, wordmark_bottom, 2):   # every-2nd-row scan is plenty for a bbox
        for x in range(0, w, 2):
            if alpha_at(x, y) > 20:
                bx0, by0 = min(bx0, x), min(by0, y)
                bx1, by1 = max(bx1, x), max(by1, y)
    cw, chh = bx1 - bx0, by1 - by0
    target_h = max(1, round(target_w * chh / cw))
    grid = [[0.0] * target_w for _ in range(target_h)]
    for ty in range(target_h):
        sy0 = by0 + (ty * chh) // target_h
        sy1 = max(sy0 + 1, by0 + ((ty + 1) * chh) // target_h)
        for tx in range(target_w):
            sx0 = bx0 + (tx * cw) // target_w
            sx1 = max(sx0 + 1, bx0 + ((tx + 1) * cw) // target_w)
            tot = cnt = 0
            for yy in range(sy0, sy1):
                for xx in range(sx0, sx1):
                    tot += alpha_at(xx, yy)
                    cnt += 1
            grid[ty][tx] = tot / cnt / 255.0
    return grid, target_h


def draw_block_text(cv, text, ox, oy, scale, core, shade):
    """Blocky bitmap text (the FONT dict, 5x7 glyphs) at an arbitrary integer
    scale, with a 1px drop-shadow regardless of scale — used for the "HQ"
    suffix badge beside the traced neon wordmark."""
    x = ox
    for ch in text:
        glyph = FONT[ch]
        for gy, grow in enumerate(glyph):
            for gx, bit in enumerate(grow):
                if bit != '1':
                    continue
                cv.rect(x + gx * scale + 1, oy + gy * scale + 1, scale, scale, shade)
        for gy, grow in enumerate(glyph):
            for gx, bit in enumerate(grow):
                if bit != '1':
                    continue
                cv.rect(x + gx * scale, oy + gy * scale, scale, scale, core)
        x += 6 * scale
    return x - ox


def gen_sign():
    """Rooftop sign: the real 'Cafreso' script wordmark traced into neon-tube
    pixel art, plus a small blocky 'HQ' badge beside it — same composition
    as a real shopfront sign pairing a cursive wordmark with a plain suffix."""
    WORDMARK_W = 96
    HQ_SCALE = 3
    NEON_HOT = hx('fff6d8')   # near-white — the lit tube itself
    NEON_GLOW = hx('f8c840')  # gold — the anti-aliased edge glow (brand gold)

    grid, gh = trace_wordmark(WORDMARK_W)
    hq_cols = 5 + 1 + 5   # "H" + 1-col gap + "Q"
    hq_w, hq_h = hq_cols * HQ_SCALE, 7 * HQ_SCALE
    gap = 7
    content_w = WORDMARK_W + gap + hq_w
    content_h = max(gh, hq_h)

    pad, rim = 4, 1
    w = content_w + 2 * (pad + rim)
    h = content_h + 2 * (pad + rim)
    cv = Canvas(w, h)
    cv.rect(0, 0, w, h, K)
    cv.rect(rim, rim, w - 2 * rim, h - 2 * rim, PAL['d'])
    cv.rect(rim, rim, w - 2 * rim, 1, hx('50402e'))          # top bevel
    cv.rect(rim, h - rim - 1, w - 2 * rim, 1, PAL['D'])       # bottom shade

    wx, wy = pad + rim, pad + rim + (content_h - gh) // 2
    for y in range(gh):
        for x in range(WORDMARK_W):
            v = grid[y][x]
            if v > 0.55:
                cv.set(wx + x, wy + y, NEON_HOT)
            elif v > 0.15:
                cv.set(wx + x, wy + y, NEON_GLOW)

    hx_, hy_ = pad + rim + WORDMARK_W + gap, pad + rim + (content_h - hq_h) // 2
    draw_block_text(cv, 'HQ', hx_, hy_, HQ_SCALE, PAL['y'], PAL['Y'])

    cv.save('sign_hq.png')


# ── Sky, clouds, skylines ────────────────────────────────────────────────────
def _grad_strip(name, stops, h=280, w=4):
    """Vertical banded gradient with 2-row checker dither at band joins."""
    cv = Canvas(w, h)
    n = len(stops)
    band = h // n
    for i in range(n):
        c = hx(stops[i])
        y0 = i * band
        y1 = h if i == n - 1 else (i + 1) * band
        for y in range(y0, y1):
            for x in range(w):
                cv.set(x, y, c)
        if i + 1 < n:
            nxt = hx(stops[i + 1])
            for x in range(w):
                if (x + y1) % 2 == 0:
                    cv.set(x, y1 - 1, nxt)
                if (x + y1) % 2 == 1 and y1 < h:
                    cv.set(x, y1, c)
    cv.save(name)


def gen_sky():
    _grad_strip('sky_day.png',
                ['5ab0dc', '6cbce4', '7ec8e8', '96d4ec', 'aee0f0',
                 'c6e8ee', 'dceee0', 'f0ecc8', 'f6e4b0'])
    _grad_strip('sky_night.png',
                ['10142e', '161a3a', '1a2048', '222a56', '2a3468',
                 '344076', '3e4680', '4a4a80', '564a78'])
    # Stars — sparse tile, night only.
    rng = LCG(7)
    st = Canvas(64, 64)
    for _ in range(26):
        x, y = rng.rint(0, 63), rng.rint(0, 47)
        st.set(x, y, hx('e8ecff'))
        if rng.rint(0, 3) == 0:
            st.set(x + 1, y, hx('8a92c8'))
    st.save('stars.png')
    # Clouds — two puffs on a transparent sheet.
    cl = Canvas(96, 32)
    puff = [
        '..........qqqq..................',
        '......qqqqqqqqqq................',
        '....qqqqqqqqqqqqqqqq............',
        '..qqqqqqqqqqqqqqqqqqqq..........',
        '.qqqqqqqqqqqqqqqqqqqqqq.........',
        'qqqqqqqqqqqqqqqqqqqqqqqq........',
        'DDDDDDDDDDDDDDDDDDDDDDDD........',
    ]
    pal = {'.': None, 'q': hx('ffffff'), 'D': hx('d8e8f0')}
    cl.blit_ascii(puff, pal, 2, 4)
    cl.blit_ascii(puff[1:], pal, 52, 14)
    cl.save('clouds.png')
    # Sun + moon
    sun = Canvas(20, 20)
    for y in range(20):
        for x in range(20):
            d2 = (x - 9.5) ** 2 + (y - 9.5) ** 2
            if d2 <= 49:
                sun.set(x, y, hx('ffe088') if d2 > 25 else hx('fff2c0'))
    sun.save('sun.png')
    moon = Canvas(16, 16)
    for y in range(16):
        for x in range(16):
            d2 = (x - 7.5) ** 2 + (y - 7.5) ** 2
            d2b = (x - 10.5) ** 2 + (y - 5.5) ** 2
            if d2 <= 36 and d2b > 20:
                moon.set(x, y, hx('f0eccc'))
    moon.save('moon.png')


def _skyline(name, w, h, night, near):
    rng = LCG(0xCAFE50 if near else 0xB0BA)
    cv = Canvas(w, h)
    x = 0
    day_walls = ['d8b090', 'c8b8a8', 'b8c8c0', 'd0c0a0', 'c0a898']
    signs = ['d84848', '4878c8', '58a858', 'e86a8a', 'f8c840']
    while x < w - 4:
        bw = rng.rint(16, 40) if near else rng.rint(12, 30)
        bh = rng.rint(int(h * 0.42), h - 6) if near else rng.rint(int(h * 0.35), h - 4)
        if near and rng.rint(0, 3) == 0:
            bh = rng.rint(int(h * 0.25), int(h * 0.45))   # low shopfront rows
        wall = (hx('202650') if night else hx(rng.pick(day_walls))) if near else \
               (hx('1a2044') if night else hx('a0c4dc'))
        cv.rect(x, h - bh, bw, bh, wall)
        # roof line / parapet
        cv.rect(x, h - bh, bw, 1, hx('12142e') if night else (hx('8a7864') if near else hx('8cb0cc')))
        if near:
            # shopfront awning on low buildings, window grid on tall ones
            for wy in range(h - bh + 3, h - 3, 5):
                for wx in range(x + 2, x + bw - 2, 4):
                    lit = rng.rint(0, 9) < 7
                    c = (hx('f8e8a0') if lit else hx('2a3048')) if night else \
                        (hx('78b0cc') if rng.rint(0, 1) else hx('5a90ac'))
                    cv.rect(wx, wy, 2, 3, c)
            if rng.rint(0, 2) == 0 and bh > int(h * 0.5):
                sc = hx(rng.pick(signs))
                sx = x + rng.rint(1, max(1, bw - 7))
                sh = rng.rint(10, min(20, bh - 8))
                cv.rect(sx, h - bh + 3, 6, sh, sc)
                cv.rect(sx, h - bh + 3, 6, 1, hx('12142e'))
                for gy in range(h - bh + 5, h - bh + 2 + sh - 1, 3):
                    cv.rect(sx + 2, gy, 2, 1, hx('fffaf0') if night else hx('f0ecd8'))
        else:
            if night:
                for _ in range(max(1, (bw * bh) // 60)):
                    cv.set(x + rng.rint(1, bw - 2), h - bh + rng.rint(2, bh - 2), hx('c8c890'))
            if rng.rint(0, 3) == 0:   # antenna
                ax = x + rng.rint(2, max(2, bw - 3))
                cv.rect(ax, h - bh - rng.rint(2, 5), 1, 5, hx('1a2044') if night else hx('8cb0cc'))
        x += bw + (0 if near and rng.rint(0, 2) else rng.rint(0, 2))
    cv.save(name)


def gen_skylines():
    _skyline('skyline_far_day.png', 320, 60, night=False, near=False)
    _skyline('skyline_far_night.png', 320, 60, night=True, near=False)
    _skyline('skyline_near_day.png', 320, 88, night=False, near=True)
    _skyline('skyline_near_night.png', 320, 88, night=True, near=True)


# ── Tiles — interior floor / CEO carpet / facade / sidewalk ─────────────────
def gen_tiles():
    fl = Canvas(24, 16)
    fl.rect(0, 0, 24, 16, PAL['h'])
    for y in (0, 8):
        fl.rect(0, y, 24, 1, PAL['H'])
    fl.rect(11, 1, 1, 7, PAL['H'])
    fl.rect(23, 9, 1, 7, PAL['H'])
    fl.rect(5, 9, 1, 7, PAL['H'])
    fl.save('floor_wood.png')

    cp = Canvas(16, 16)
    cp.rect(0, 0, 16, 16, PAL['v'])
    for y in range(16):
        for x in range(16):
            if (x // 4 + y // 4) % 2 == 0 and (x % 4 == 0 or y % 4 == 0):
                cp.set(x, y, PAL['V'])
    cp.save('floor_ceo.png')

    fa = Canvas(16, 16)
    fa.rect(0, 0, 16, 16, hx('e8d8b8'))
    for y in (3, 7, 11, 15):
        fa.rect(0, y, 16, 1, hx('c8b490'))
    for y, off in ((0, 4), (4, 10), (8, 2), (12, 8)):
        fa.rect(off, y, 1, 3, hx('c8b490'))
    fa.save('facade.png')

    sw = Canvas(16, 16)
    sw.rect(0, 0, 16, 16, hx('b8b4ac'))
    for y in (0, 8):
        sw.rect(0, y, 16, 1, hx('989488'))
    sw.rect(7, 1, 1, 7, hx('989488'))
    sw.rect(15, 9, 1, 7, hx('989488'))
    sw.save('sidewalk.png')

    wl = Canvas(16, 24)
    wl.rect(0, 0, 16, 24, PAL['c'])
    wl.rect(0, 17, 16, 1, hx('b09468'))       # picture rail…
    wl.rect(0, 18, 16, 6, hx('d8c09c'))       # …wainscot
    wl.rect(0, 23, 16, 1, hx('a08050'))
    wl.save('wall_int.png')
    return None


def main():
    os.makedirs(OUT, exist_ok=True)
    gen_chars()
    gen_dog()
    gen_furniture()
    gen_sign()
    gen_sky()
    gen_skylines()
    gen_tiles()
    # Contact sheet at ×3 for eyeballing (not shipped by the UI).
    files = sorted(f for f in os.listdir(OUT) if f.endswith('.png') and f != 'preview.png')
    # simple decode-free preview: re-render from canvases is complex; instead
    # upscale by re-reading our own PNGs is overkill — skip; per-file review works.
    print('wrote %d assets to %s' % (len(files), OUT))
    for f in files:
        print('  ', f)


if __name__ == '__main__':
    main()
