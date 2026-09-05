#!/usr/bin/env python3
"""#338 and #345 were both found with real geometry and both guarded with
grep.

The two suites that stand behind those tickets —
`test_the_office_floor_can_be_scrolled_all_the_way_to_the_lobby_door.py`
and `test_the_office_ticker_is_not_hidden_behind_the_mobile_tab_bar.py` —
read styles.css and assert that particular declarations are present in
particular selector lists. That is worth keeping: it says WHY each line
is there, and it fails loudly when someone deletes one. But it is a text
test standing in for a measurement. Both bugs were collisions between
boxes, and neither suite has a box in it. Stretch a SIBLING of the
ticker, give `.mobile-tabbar` more height, change `--z-*`, or put a new
element in the office column, and the ticker goes back under the tab bar
with every string those tests look for still exactly where it was.

This suite measures instead. It boots the REAL app — real
`dist-ui/bundle` (the same manifest injection serve.py does), real
styles.css, real `hq.html` — in headless Chrome, emulates a phone, opens
the Office tab, and reads `getBoundingClientRect()` and
`document.elementsFromPoint` off the live layout.

Two phone sizes, because the two faults bind at different ones. 375x812
is where #338's clipped scroll viewport showed up. 375x667 (iPhone SE)
is where `.pxhq`'s sizing binds hardest — that is where the old
`min-height: 420px` overhung its parent by 92px, and it is the size at
which the office has the least room to give.

Measured on the fix, 2026-09-05, on a cold first run:

  375x812  ticker 706.0 -> 740.0, tab bar top 742.0  (2.0px clear)
           .pxhq 285.1 -> 692.0 inside a root ending 694.0
           .px-scene 331.7 -> 692.0, scrolled to max (377.5 of 378)
           door 643.7 -> 677.7, entirely inside the scene
           elementsFromPoint at the door's centre: the door is the
           topmost thing on the floor
           fab 638.0 -> 682.0 x 10.0 -> 54.0, clear of the door

  375x667  ticker 561.0 -> 595.0, tab bar top 597.0  (2.0px clear)
           .pxhq 285.1 -> 547.0 inside a root ending 549.0
           .px-scene 331.7 -> 547.0, scrolled to max (522.5 of 523)
           door 498.7 -> 532.7, entirely inside the scene
           elementsFromPoint at the door's centre: the door is the
           topmost thing on the floor
           fab 493.0 -> 537.0 x 10.0 -> 54.0, clear of the door

The exact figures move a fraction of a pixel between runs and will move
further as the office column gains or loses content; every assertion
below is an inequality between two boxes measured in the same frame, not
a comparison against a number written here.

WHAT THE DOOR CHECK ASSERTS, EXACTLY. It walks
`document.elementsFromPoint` at the door's own centre and requires that
the first element belonging to `.px-scene`'s subtree IS the door — that
is the thing #338 broke, where the door was clipped out of the scene's
painted box and appeared nowhere in the stack at any scroll position —
and, separately, that nothing above the door in that stack belongs to
`.mobile-tabbar`, which is what the stack actually returned back then.

It now ALSO asserts that the door is the topmost element on the whole
page, and that `.palette-fab` does not touch the door's box at all.

That pair of checks is #353, and it replaces an exclusion this suite
shipped with. When these measurements were first written the door was
NOT topmost on the page at either size: `.palette-fab`
(ui/feedback.jsx ~523) is a fixed 40px command-palette button that was
pinned at `right: 10px; bottom: calc(130px + safe-area)` on every phone,
and the lobby door came to rest under it — measured 638.0 -> 682.0 x
321.0 -> 365.0 at 375x812 against a door at 644.2 -> 678.2 x 309.0 ->
341.0, and 493.0 -> 537.0 against a door at 499.2 -> 533.2 at 375x667,
and 394.0 -> 438.0 against a door at 400.2 -> 434.2 at 320x568. The FAB
covered the door's CENTRE every time; only the door's left ~12px was
still its own, so a person tapping the meeting room opened the command
palette instead.

That overlap was measured here and then excluded on purpose, with the
weaker "topmost ON THE FLOOR" wording standing in for the real
requirement, because asserting it would have meant a red suite for a bug
that change was not fixing. The exclusion is gone: the FAB now sits at
the lobby's other end (`left: 10px`, styles.css ~975, over the water
cooler, which has no handler), and the assertions below say what a
person tapping a door actually needs — that nothing whatsoever is
painted over it.

NO NEW DEPENDENCY. There is no puppeteer, playwright, jsdom or
happy-dom in node_modules and this suite does not add one. It drives
Chrome over the DevTools Protocol with the standard library only — a
~60-line RFC 6455 client over `socket` — against a browser binary that
is already on the machine. If none is found the suite says so and
skips; it does not silently pass.

Run: python3 scripts/test_the_office_ticker_and_the_lobby_door_are_measured_on_a_real_phone.py
"""
from __future__ import annotations

import base64
import http.server
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import ui_manifest  # noqa: E402  (repo helper, same one serve.py uses)

FAILS = []
VIEWPORTS = [(375, 812), (375, 667)]

# Browser binaries this machine might already have. Nothing here is
# installed by this suite; the first one that exists wins.
CHROME_CANDIDATES = [
    Path.home() / 'Library/Caches/ms-playwright/chromium_headless_shell-1228'
    / 'chrome-headless-shell-mac-arm64/chrome-headless-shell',
    Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
    Path('/Applications/Chromium.app/Contents/MacOS/Chromium'),
    Path('/usr/bin/google-chrome'),
    Path('/usr/bin/chromium'),
    Path('/usr/bin/chromium-browser'),
]


def find_chrome():
    env = os.environ.get('CHROME_PATH')
    if env and Path(env).exists():
        return Path(env)
    for p in CHROME_CANDIDATES:
        if p.exists():
            return p
    # Any playwright chromium revision, not just the pinned one above.
    cache = Path.home() / 'Library/Caches/ms-playwright'
    if cache.is_dir():
        for pat in ('chromium_headless_shell-*/*/chrome-headless-shell',
                    'chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium'):
            for hit in sorted(cache.glob(pat)):
                return hit
    return None


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ------------------------------------------------------------------ server
class Handler(http.server.SimpleHTTPRequestHandler):
    """The repo, served the way serve.py serves it: hq.html with its
    `<!--HQ_SCRIPTS-->` placeholder substituted from dist-ui/manifest.json,
    and the manifest's root-relative `bundle/...` URLs pointed at
    dist-ui/bundle. Using the repo's own `ui_manifest` helper is what keeps
    this from becoming a fixture — the page under test is assembled by the
    same code the real server uses."""

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def translate_path(self, path):
        if path.split('?')[0].startswith('/bundle/'):
            path = '/dist-ui' + path
        return super().translate_path(path)

    def do_GET(self):
        if self.path.split('?')[0] in ('/', '/hq.html'):
            html = (ROOT / 'hq.html').read_text(encoding='utf-8')
            man = ui_manifest.load_manifest(str(ROOT / 'dist-ui'))
            body = ui_manifest.inject(html, man).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def log_message(self, *a):
        pass


# ------------------------------------------------------------- ws + cdp
class WS:
    """Minimal RFC 6455 client — enough to speak CDP, nothing more."""

    def __init__(self, url, timeout=30):
        m = re.match(r'ws://([^:/]+):(\d+)(/.*)', url)
        host, port, path = m.group(1), int(m.group(2)), m.group(3)
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            f'GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n'
            'Upgrade: websocket\r\nConnection: Upgrade\r\n'
            f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n'
        ).encode())
        buf = b''
        while b'\r\n\r\n' not in buf:
            chunk = self.sock.recv(1)
            if not chunk:
                raise IOError('handshake closed')
            buf += chunk
        self.buf = buf.split(b'\r\n\r\n', 1)[1]
        self._id = 0

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise IOError('websocket closed')
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, text):
        data = text.encode('utf-8')
        n = len(data)
        hdr = bytes([0x81])
        if n < 126:
            hdr += bytes([0x80 | n])
        elif n < 65536:
            hdr += bytes([0x80 | 126]) + struct.pack('>H', n)
        else:
            hdr += bytes([0x80 | 127]) + struct.pack('>Q', n)
        mask = os.urandom(4)
        self.sock.sendall(hdr + mask
                          + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self):
        while True:
            b0, b1 = self._read(2)
            opcode, n = b0 & 0x0F, b1 & 0x7F
            if n == 126:
                n = struct.unpack('>H', self._read(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', self._read(8))[0]
            payload = self._read(n)
            if opcode == 0x9:                       # ping -> pong
                self.sock.sendall(bytes([0x8A, 0x80]) + b'\x00' * 4)
                continue
            if opcode in (0x1, 0x2):
                return payload.decode('utf-8')
            if opcode == 0x8:
                raise IOError('websocket closed by peer')

    def call(self, method, params=None, timeout=30):
        self._id += 1
        mid = self._id
        self.send(json.dumps({'id': mid, 'method': method,
                              'params': params or {}}))
        end = time.time() + timeout
        while time.time() < end:
            msg = json.loads(self.recv())
            if msg.get('id') == mid:
                if 'error' in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get('result', {})
        raise TimeoutError(method)

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def evaluate(ws, expr, timeout=30):
    r = ws.call('Runtime.evaluate', {'expression': expr,
                                     'returnByValue': True,
                                     'awaitPromise': True}, timeout=timeout)
    if r.get('exceptionDetails'):
        raise RuntimeError(json.dumps(r['exceptionDetails'])[:600])
    return r['result'].get('value')


def wait_for(ws, expr, seconds, what):
    end = time.time() + seconds
    while time.time() < end:
        try:
            if evaluate(ws, expr):
                return True
        except Exception:
            pass
        time.sleep(0.25)
    raise TimeoutError(f'timed out waiting for {what}')


def press_escape(ws):
    for typ in ('keyDown', 'keyUp'):
        ws.call('Input.dispatchKeyEvent', {
            'type': typ, 'key': 'Escape', 'code': 'Escape',
            'windowsVirtualKeyCode': 27, 'nativeVirtualKeyCode': 27})


# --------------------------------------------------------- the measurement
# Runs in the page. Scrolls the office floor to the bottom, waits two
# frames so layout and paint have settled, then reads every box this
# suite asserts on in ONE pass so nothing can shift between reads.
MEASURE_JS = r"""(() => {
  const box = e => e ? (r => ({top: r.top, bottom: r.bottom, left: r.left,
                               right: r.right, width: r.width, height: r.height}))
                       (e.getBoundingClientRect()) : null;
  const q = s => document.querySelector(s);
  const scene = q('.px-scene');
  if (scene) scene.scrollTop = scene.scrollHeight - scene.clientHeight;
  const tag = e => e ? (e.tagName + (e.className ? '.' + String(e.className) : '')) : null;
  return new Promise(res => requestAnimationFrame(() => requestAnimationFrame(() => {
    const door = q('.px-meetdoor');
    const dr = door && door.getBoundingClientRect();
    const tabbar = q('.mobile-tabbar');
    const ticker = q('.ticker');
    let stack = [], firstInScene = null, tabbarAbove = null, doorIndex = -1;
    let cx = null, cy = null, above = [];
    if (dr) {
      cx = dr.left + dr.width / 2;
      cy = dr.top + dr.height / 2;
      const els = document.elementsFromPoint(cx, cy) || [];
      stack = els.map(tag);
      for (let i = 0; i < els.length; i++) {
        const e = els[i];
        if (e === door) doorIndex = i;
        /* Everything painted STRICTLY above the door at its own centre. The
           door's own sprite children count as the door, not as cover. */
        if (doorIndex === -1 && !door.contains(e)) above.push(tag(e));
        if (firstInScene === null && scene && scene.contains(e)) firstInScene = i;
        if (tabbarAbove === null && tabbar && (e === tabbar || tabbar.contains(e))
            && (doorIndex === -1 || i < doorIndex)) tabbarAbove = tag(e);
      }
    }
    let tickerHit = null, tickerOwn = false;
    if (ticker) {
      const tr = ticker.getBoundingClientRect();
      /* elementsFromPoint, not elementFromPoint, so a toast in flight does
         not decide a LAYOUT question. A toast is `position: fixed` app
         furniture that legitimately floats over the whole column for a few
         seconds; this harness serves the repo statically with nothing behind
         /fs, so the office's own autosave fails on a cold start and raises
         `⚠ Office file save failed` over the ticker in about half of runs at
         375x812. Waiting it out is not the answer either — they re-fire, and
         a long wait gives the first-run dialogs time to come back. So skip
         toasts and ask what is under them: the tab bar covering the ticker
         is the fault #345 was about, and that still fails this check. */
      const stack = document.elementsFromPoint(tr.left + tr.width / 2,
                                               tr.top + tr.height / 2);
      const el = stack.find(e => !e.closest('.toast')) || null;
      tickerHit = tag(el);
      tickerOwn = !!el && (el === ticker || ticker.contains(el));
    }
    res({
      innerHeight: window.innerHeight,
      wrap: box(q('.office-wrap')),
      ticker: box(ticker), tickerHit, tickerOwn,
      tabbar: box(tabbar),
      tabbarFixed: tabbar ? getComputedStyle(tabbar).position : null,
      pxhq: box(q('.pxhq')), pxhqRoot: box(q('.office.pxhq-root')),
      scene: box(scene),
      scrollTop: scene ? scene.scrollTop : null,
      scrollMax: scene ? (scene.scrollHeight - scene.clientHeight) : null,
      door: box(door), doorIndex, firstInScene, tabbarAbove, above, stack,
      cx, cy, fab: box(q('.palette-fab')),
      openBackdrops: document.querySelectorAll('.backdrop').length,
    });
  })));
})()"""


def measure(ws, url, width, height):
    ws.call('Emulation.setDeviceMetricsOverride', {
        'width': width, 'height': height, 'deviceScaleFactor': 2,
        'mobile': True})
    ws.call('Page.navigate', {'url': url})
    # The app signals its own mount; the boot splash then fades. Wait on the
    # DOM, not on a sleep, so a slow machine measures the same layout.
    wait_for(ws, "!!document.querySelector('.mobile-tabbar')", 45, 'the app to mount')
    # hq.html's boot splash is a full-screen overlay with a canvas in it. It
    # removes itself once the app signals `cafresohq:ready` (and always by an
    # 8s safety net), but it is still on top for the first moment after the
    # tab bar exists — and it is opaque to elementFromPoint. Measuring
    # through it would report the splash as the thing covering the ticker.
    wait_for(ws, "!document.getElementById('cafreso-boot')", 20,
             'the boot splash to clear')
    evaluate(ws, """(() => {
      const b = [...document.querySelectorAll('.mtab')]
        .find(x => /Office/i.test(x.textContent || ''));
      if (b) b.click();
      return !!b;
    })()""")
    wait_for(ws, "!!document.querySelector('.office-wrap .px-scene')", 30,
             'the Office tab to render its floor')
    # A first run with an empty team auto-opens the hire dialog over the
    # floor. Dismiss it the way a person would (Esc — modals/base.jsx ~202)
    # rather than measuring underneath a backdrop.
    for _ in range(8):
        if not evaluate(ws, "document.querySelectorAll('.backdrop').length"):
            break
        press_escape(ws)
        time.sleep(0.4)
    # Same for the getting-started coach (ui/onboarding.jsx ~549): a fixed
    # first-run panel that legitimately floats over the column. Close it by
    # its own ✕ so the boxes underneath are the office's, not onboarding's.
    evaluate(ws, """(() => {
      const x = document.querySelector('.gs-coach button[title="Dismiss"]');
      if (x) x.click();
      return !!x;
    })()""")
    wait_for(ws, "!document.querySelector('.gs-coach')", 15,
             'the getting-started coach to be dismissed')
    wait_for(ws, "!!document.querySelector('.px-meetdoor')", 30,
             'the lobby to draw its meeting door')
    return evaluate(ws, MEASURE_JS)


def assert_viewport(m, width, height):
    tag = f'{width}x{height}'
    n = lambda v: 'null' if v is None else round(v, 1)  # noqa: E731

    check(f'[{tag}] the phone viewport is the one we asked for',
          m['innerHeight'] == height, f"innerHeight {m['innerHeight']}")
    check(f'[{tag}] no dialog is covering the floor',
          m['openBackdrops'] == 0,
          f"{m['openBackdrops']} .backdrop still open — the measurement "
          'below would be of the dialog, not the office')
    check(f'[{tag}] the Office tab rendered its column',
          m['wrap'] is not None, '.office-wrap is not in the DOM')
    check(f'[{tag}] the mobile tab bar is on screen and fixed',
          m['tabbar'] is not None and m['tabbarFixed'] == 'fixed',
          f"position: {m['tabbarFixed']}")

    # ---- #345: the ticker clears the tab bar, by measurement ----
    tk, tb = m['ticker'], m['tabbar']
    check(f'[{tag}] the office ticker is on screen', tk is not None,
          'ui/office.jsx ~1805 — the last thing in the office column')
    if tk and tb:
        gap = tb['top'] - tk['bottom']
        check(f'[{tag}] the ticker ends above the tab bar',
              tk['bottom'] <= tb['top'] + 0.5,
              f"ticker {n(tk['top'])} -> {n(tk['bottom'])} against a tab bar "
              f"at {n(tb['top'])} — overlap {n(-gap)}px. The clearance "
              'padding on .office-wrap is what holds this apart.')
        check(f'[{tag}] the ticker is inside the viewport',
              tk['bottom'] <= m['innerHeight'] + 0.5,
              f"ticker bottom {n(tk['bottom'])} past {m['innerHeight']}")
        print(f'        ticker {n(tk["top"])} -> {n(tk["bottom"])} · '
              f'tab bar top {n(tb["top"])} · clearance {n(gap)}px')
    check(f'[{tag}] the ticker hit-tests as itself',
          m['tickerOwn'],
          f"document.elementFromPoint at the ticker's own centre returned "
          f"{m['tickerHit']} — something is painted over it")

    # ---- #345 fault 2: .pxhq does not overhang its own container ----
    hq, root = m['pxhq'], m['pxhqRoot']
    check(f'[{tag}] the office building is on screen', hq is not None)
    if hq and root:
        over = hq['bottom'] - root['bottom']
        check(f'[{tag}] the building does not hang past its container',
              over <= 0.5,
              f".pxhq ends {n(hq['bottom'])} inside a container ending "
              f"{n(root['bottom'])} — {n(over)}px of overhang. A pixel floor "
              'on a flex:1 box is an overflow, not a floor.')
        print(f'        .pxhq {n(hq["top"])} -> {n(hq["bottom"])} · '
              f'root ends {n(root["bottom"])}')

    # ---- #338: the scene clips nothing away, and the door is reachable ----
    sc, dr = m['scene'], m['door']
    check(f'[{tag}] the office floor has its scroll container', sc is not None)
    if sc and hq:
        check(f'[{tag}] the scroll viewport ends where .pxhq ends',
              sc['bottom'] <= hq['bottom'] + 0.5,
              f"scene {n(sc['top'])} -> {n(sc['bottom'])} inside a .pxhq "
              f"ending {n(hq['bottom'])} — the overhanging part of a scroll "
              'viewport is never painted and never hit-tested')
    check(f'[{tag}] the floor scrolled all the way down',
          m['scrollTop'] is not None and m['scrollMax'] is not None
          and abs(m['scrollTop'] - m['scrollMax']) <= 1,
          f"scrollTop {m['scrollTop']} of {m['scrollMax']}")
    check(f'[{tag}] the lobby door is drawn', dr is not None,
          'ui/office.jsx ~1655 — the control that seats the team')
    if dr and sc:
        check(f'[{tag}] the door is inside the scroll viewport at max scroll',
              dr['bottom'] <= sc['bottom'] + 0.5 and dr['top'] >= sc['top'] - 0.5,
              f"door {n(dr['top'])} -> {n(dr['bottom'])} against a viewport "
              f"{n(sc['top'])} -> {n(sc['bottom'])} — outside it the door is "
              'clipped away and cannot be tapped at any scroll position')
        print(f'        door {n(dr["top"])} -> {n(dr["bottom"])} · '
              f'scene {n(sc["top"])} -> {n(sc["bottom"])} · '
              f'scroll {m["scrollTop"]}/{m["scrollMax"]}')

    # The hit test itself. See the module docstring: this asks for topmost on
    # the WHOLE PAGE, which is what "a person tapping the meeting door opens
    # the meeting room" actually requires. Until #353 it could only ask for
    # topmost on the floor, because `.palette-fab` sat on the door's centre.
    check(f'[{tag}] the door hit-tests at its own centre',
          m['doorIndex'] >= 0,
          f"document.elementsFromPoint({n(m['cx'])}, {n(m['cy'])}) returned "
          f"{m['stack'][:4]} — the door is not in the stack at all, which is "
          'what a clipped scroll viewport looks like')
    check(f'[{tag}] the door is the topmost thing on the office floor',
          m['doorIndex'] >= 0 and m['firstInScene'] == m['doorIndex'],
          f"the first element of .px-scene under that point is "
          f"{m['stack'][m['firstInScene']] if m['firstInScene'] is not None else None}, "
          f"not the door")
    check(f'[{tag}] the mobile tab bar is not over the door',
          m['tabbarAbove'] is None,
          f"{m['tabbarAbove']} is painted above the door at its own centre — "
          'this is exactly the stack #338 measured')
    fb = m['fab']
    check(f'[{tag}] nothing at all is painted over the door',
          m['doorIndex'] == 0,
          f"{m['above']} sits above the door at its own centre. A tap there "
          'runs whatever is on top, not the meeting room'
          + (f" — .palette-fab is at {n(fb['top'])} -> {n(fb['bottom'])} "
             f"x {n(fb['left'])} -> {n(fb['right'])}" if fb else ''))
    if dr and fb:
        clear = (fb['right'] <= dr['left'] + 0.5 or fb['left'] >= dr['right'] - 0.5
                 or fb['bottom'] <= dr['top'] + 0.5 or fb['top'] >= dr['bottom'] - 0.5)
        check(f'[{tag}] the command-palette button does not touch the door',
              clear,
              f"fab {n(fb['top'])} -> {n(fb['bottom'])} x {n(fb['left'])} -> "
              f"{n(fb['right'])} overlaps door {n(dr['top'])} -> {n(dr['bottom'])} "
              f"x {n(dr['left'])} -> {n(dr['right'])}. Both are bottom-anchored, "
              'so they collide by construction, not by accident.')
        print(f'        fab {n(fb["top"])} -> {n(fb["bottom"])} · '
              f'x {n(fb["left"])} -> {n(fb["right"])}')


def main():
    print('The office ticker and the lobby door, measured on a real phone')

    if not (ROOT / 'dist-ui' / 'manifest.json').exists():
        print('  FAIL  the HQ UI is built  — dist-ui/manifest.json is missing; '
              'run `npm install && npm run build` first')
        print('\n1 FAILED — the HQ UI is built')
        return 1

    chrome = find_chrome()
    if chrome is None:
        print('  SKIPPED — no headless browser on this machine.')
        print('  This suite measures the rendered app, so it needs one. It '
              'does not install anything: it looks for $CHROME_PATH, a '
              'playwright browser cache, or a Chrome/Chromium in the usual '
              'places, and drives whichever it finds over CDP with the '
              'standard library only.')
        print('\nnothing measured')
        return 0
    print(f'  using  {chrome}')

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{srv.server_address[1]}/hq.html'

    profile = tempfile.mkdtemp(prefix='cafresohq-cdp-')
    proc = subprocess.Popen(
        [str(chrome), '--headless=new', '--remote-debugging-port=0',
         f'--user-data-dir={profile}', '--no-sandbox', '--disable-gpu',
         '--hide-scrollbars', '--mute-audio', '--no-first-run',
         '--no-default-browser-check', '--disable-extensions',
         '--disable-background-timer-throttling',
         '--disable-renderer-backgrounding', '--force-device-scale-factor=2',
         'about:blank'],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    ws = None
    try:
        endpoint = None
        deadline = time.time() + 30
        while time.time() < deadline:
            line = proc.stderr.readline().decode('utf-8', 'replace')
            if not line:
                break
            hit = re.search(r'ws://\S+', line)
            if hit:
                endpoint = hit.group(0)
                break
        if not endpoint:
            print('  FAIL  the browser announced a DevTools endpoint  — '
                  f'{chrome} started but never printed one')
            print('\n1 FAILED — the browser announced a DevTools endpoint')
            return 1

        host = re.match(r'ws://([^/]+)/', endpoint).group(1)
        with urllib.request.urlopen(f'http://{host}/json/list', timeout=15) as fh:
            targets = json.load(fh)
        page = next(t for t in targets if t['type'] == 'page')
        ws = WS(page['webSocketDebuggerUrl'])
        ws.call('Page.enable')
        ws.call('Runtime.enable')

        for width, height in VIEWPORTS:
            try:
                m = measure(ws, url, width, height)
            except Exception as exc:
                check(f'[{width}x{height}] the app rendered so it could be '
                      'measured', False, f'{type(exc).__name__}: {exc}')
                continue
            assert_viewport(m, width, height)
    finally:
        if ws:
            ws.close()
        proc.kill()
        proc.wait(timeout=10)
        srv.shutdown()
        shutil.rmtree(profile, ignore_errors=True)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
