#!/usr/bin/env python3
"""The ✕ on Getting Started, driven in a real browser (`## 412.`).

The source-level companion to this file
(`test_the_x_on_getting_started_was_a_one_way_door.py`) asserts the WIRING.
This one asserts the BEHAVIOUR, because a safety verdict that cites a
mechanism rather than a measurement is a hypothesis. It boots the real
bundle in headless Chrome over CDP — same harness as the five layout suites
beside it — on a fresh profile and a fresh port, so localStorage starts
genuinely empty, and then:

  1. waits for the Getting Started checklist to exist at all;
  2. clicks its ✕ — the real button, by the class the app gives it;
  3. asserts the card is gone AND that the flag behind it is persisted, so
     the click outlives the tab;
  4. asserts a reload does NOT bring it back (the one-way half);
  5. fires `cafresohq:showGettingStarted` — what the palette's "Show getting
     started checklist" command dispatches — and asserts the card returns
     and the stored flag went back to false.

Step 5 is the whole fix. Before it existed, step 4 was the end of the road:
nothing in the repo wrote that flag false, and `coachMark` returns null
while it is true, so the same click also silenced every just-in-time nudge.

Skips cleanly (exit 0) when no headless browser is on the machine — same
contract as its neighbours; it installs nothing.

Run: python3 scripts/test_the_x_on_getting_started_comes_back.py
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


VIEWPORT = (1280, 900)


def storage_flag(ws):
    """The persisted value of the getting-started flag, whatever key the app
    scoped it to. Derived by scanning localStorage rather than pinned, so a
    change to `ks()`'s prefix fails the app, not this test."""
    return evaluate(ws, """(() => {
      const out = {};
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (/gettingStartedDone/.test(k)) out[k] = localStorage.getItem(k);
      }
      return JSON.stringify(out);
    })()""")


def boot(ws, url, first=True):
    w, h = VIEWPORT
    ws.call('Emulation.setDeviceMetricsOverride', {
        'width': w, 'height': h, 'deviceScaleFactor': 1, 'mobile': False})
    ws.call('Page.navigate', {'url': url})
    wait_for(ws, "!!document.querySelector('.app')", 45, 'the app to mount')
    wait_for(ws, "!document.getElementById('cafreso-boot')", 20,
             'the boot splash to clear')
    # The first run opens the candidate deck on a timer; dismiss whatever
    # modal is up so the checklist is clickable.
    for _ in range(12):
        if not evaluate(ws, "document.querySelectorAll('.backdrop').length"):
            break
        press_escape(ws)
        time.sleep(0.4)


def main():
    print('The ✕ on Getting Started comes back  (`## 412.`)')

    if not (ROOT / 'dist-ui' / 'manifest.json').exists():
        print('  FAIL  the HQ UI is built  — dist-ui/manifest.json is missing; '
              'run `npm install && npm run build` first')
        print('\n1 FAILED — the HQ UI is built')
        return 1

    chrome = find_chrome()
    if chrome is None:
        print('  SKIPPED — no headless browser on this machine.')
        print('  This suite drives the rendered app, so it needs one. It '
              'installs nothing.')
        print('\nnothing measured')
        return 0
    print(f'  using  {chrome}')

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{srv.server_address[1]}/hq.html'

    profile = tempfile.mkdtemp(prefix='cafresohq-cdp-gs-')
    proc = subprocess.Popen(
        [str(chrome), '--headless=new', '--remote-debugging-port=0',
         f'--user-data-dir={profile}', '--no-sandbox', '--disable-gpu',
         '--hide-scrollbars', '--mute-audio', '--no-first-run',
         '--no-default-browser-check', '--disable-extensions',
         '--disable-background-timer-throttling',
         '--disable-renderer-backgrounding', 'about:blank'],
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
            print('  FAIL  the browser announced a DevTools endpoint')
            print('\n1 FAILED — the browser announced a DevTools endpoint')
            return 1

        host = re.match(r'ws://([^/]+)/', endpoint).group(1)
        with urllib.request.urlopen(f'http://{host}/json/list', timeout=15) as fh:
            targets = json.load(fh)
        page = next(t for t in targets if t['type'] == 'page')
        ws = WS(page['webSocketDebuggerUrl'])
        ws.call('Page.enable')
        ws.call('Runtime.enable')

        try:
            boot(ws, url)
            wait_for(ws, "!!document.querySelector('.gs-coach')", 30,
                     'the Getting Started checklist to appear on a fresh office')
            check('a brand-new office shows the Getting Started checklist', True)

            before = storage_flag(ws)
            check('...and nothing has written the dismiss flag yet',
                  'true' not in before, before)

            clicked = evaluate(ws, """(() => {
              const x = document.querySelector('.gs-coach button.gs-dismiss');
              if (!x) return 'no ✕ found';
              x.click();
              return 'clicked';
            })()""")
            check('the ✕ is present and clickable', clicked == 'clicked', clicked)
            wait_for(ws, "!document.querySelector('.gs-coach')", 15,
                     'the checklist to go away after the ✕')
            check('one click removes the checklist', True)

            # `useStored` debounces its write by 300ms (app/storage.jsx), so
            # reading straight after the click reads the MOUNT write and
            # reports a false pass. Measured the hard way: the first run of
            # this test saw `"false"` here and a checklist that came back on
            # reload, which looks exactly like "the trap was never real".
            # Wait for the value, don't sample it.
            wait_for(ws, "(() => { for (let i=0;i<localStorage.length;i++) {"
                         " const k = localStorage.key(i);"
                         " if (/gettingStartedDone/.test(k) &&"
                         " localStorage.getItem(k) === 'true') return true; }"
                         " return false; })()", 10,
                     'the dismiss to reach localStorage (300ms debounce)')
            after = storage_flag(ws)
            check('...and the click is PERSISTED, so it outlives the tab',
                  'true' in after, after)

            # The one-way half: a reload does not undo it.
            boot(ws, url, first=False)
            time.sleep(2.0)
            back = evaluate(ws, "!!document.querySelector('.gs-coach')")
            check('a reload does NOT bring it back (this is the trap)',
                  back is False or back == False, back)

            # The fix: the palette's command, fired as the palette fires it.
            evaluate(ws, "window.dispatchEvent(new CustomEvent("
                         "'cafresohq:showGettingStarted')), 'sent'")
            # Its OWN try, so that a missing door back fails as ITSELF rather
            # than as a generic "could not be driven" — and so that the two
            # checks after it still run. `## 404.`: a check that raises
            # reports nothing about the checks behind it.
            try:
                wait_for(ws, "!!document.querySelector('.gs-coach')", 15,
                         'the checklist to come back from the palette command')
                came_back = True
            except TimeoutError as exc:
                came_back = False
                detail = str(exc)
            check('the palette command brings the checklist back', came_back,
                  '' if came_back else detail)

            # Same debounce on the way back — and here the pre-state is the
            # value we are hoping to see leave, so a bare sleep would be the
            # weaker check. Wait for it to actually flip.
            try:
                wait_for(ws, "(() => { for (let i=0;i<localStorage.length;i++) {"
                             " const k = localStorage.key(i);"
                             " if (/gettingStartedDone/.test(k) &&"
                             " localStorage.getItem(k) === 'true') return false; }"
                             " return true; })()", 10,
                         'the restore to reach localStorage')
            except TimeoutError:
                pass          # the check below is the one that reports it
            restored = storage_flag(ws)
            check('...and clears the persisted flag, so it stays back',
                  'true' not in restored, restored)
        except Exception as exc:
            check('the office could be driven end to end', False,
                  f'{type(exc).__name__}: {exc}')
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
