"""Generate build/icon.png — a 256x256 CafresoHQ icon (pure Python stdlib, no PIL)."""
import struct, zlib, os, math

W = H = 256
BG   = (255, 248, 238)   # #fff8ee warm paper
DARK = ( 59,  46,  42)   # #3b2e2a ink
GOLD = (218, 165,  32)   # goldenrod accent
RUST = (190,  80,  40)   # warm rust for claw detail

def in_rounded_rect(x, y, w, h, r):
    dx = max(0, r - x, x - (w - 1 - r))
    dy = max(0, r - y, y - (h - 1 - r))
    return dx * dx + dy * dy <= r * r

pixels = []
for y in range(H):
    for x in range(W):
        if not in_rounded_rect(x, y, W, H, 52):
            pixels.append(BG)
            continue
        # 6-pixel dark border following the rounded rect
        on_border = not in_rounded_rect(x, y, W, H, 46)
        if on_border:
            pixels.append(DARK)
            continue
        # Gold background fill
        cx, cy = W / 2, H / 2
        # Stylised claw shape — three arcs radiating from centre-bottom
        px, py = (x - cx) / (W * 0.38), (y - cy) / (H * 0.38)
        # Outer gold circle
        r2 = px * px + py * py
        if r2 > 1.0:
            pixels.append(BG)
            continue
        # Dark ring
        if r2 > 0.82:
            pixels.append(DARK)
            continue
        # Three claw prongs (ellipses rotated 0°, ±40°)
        def prong(rx, ry, angle, px, py):
            c, s = math.cos(angle), math.sin(angle)
            lx = c * px + s * py
            ly = -s * px + c * py
            return (lx / rx) ** 2 + ((ly - 0.35) / ry) ** 2 < 1.0
        ang = math.radians(42)
        in_prong = (prong(0.18, 0.55, 0, px, py) or
                    prong(0.18, 0.55,  ang, px, py) or
                    prong(0.18, 0.55, -ang, px, py))
        # Central body ellipse
        in_body = (px / 0.38) ** 2 + ((py + 0.18) / 0.28) ** 2 < 1.0
        if in_prong or in_body:
            pixels.append(RUST)
        else:
            pixels.append(GOLD)

def make_png(w, h, pixels):
    def chunk(name, data):
        c = name + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)
    raw = b''
    for row in range(h):
        raw += b'\x00'
        for r, g, b in pixels[row * w:(row + 1) * w]:
            raw += bytes([r, g, b])
    sig  = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
    idat = chunk(b'IDAT', zlib.compress(raw, 6))
    iend = chunk(b'IEND', b'')
    return sig + ihdr + idat + iend

os.makedirs('build', exist_ok=True)

# Write PNG
png_data = make_png(W, H, pixels)
with open('build/icon.png', 'wb') as f:
    f.write(png_data)
print(f'OK  build/icon.png written ({W}x{H})')

# Wrap PNG in ICO container (Vista+ PNG-in-ICO, required by NSIS)
ico_offset = 6 + 16
ico_header = struct.pack('<HHH', 0, 1, 1)
ico_entry  = struct.pack('<BBBBHHII', 0, 0, 0, 0, 1, 32, len(png_data), ico_offset)
with open('build/icon.ico', 'wb') as f:
    f.write(ico_header + ico_entry + png_data)
print(f'OK  build/icon.ico written (PNG-in-ICO, Vista+)')
