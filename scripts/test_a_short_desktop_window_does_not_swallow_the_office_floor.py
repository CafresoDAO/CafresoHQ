#!/usr/bin/env python3
"""#369. `#361`/`#362` fixed the office floor on a WIDE-but-SHORT viewport —
a big phone turned sideways (926x428) — by zeroing `.pxhq`'s desktop
`min-height: 480px` at `@media (min-width: 769px) and (max-height: 460px)`.
That media query's own height threshold was never checked against where the
defect actually stops, and it stops much later than 460px.

MEASURED, before this fix, at rest (`.pxhq` vs `.office.pxhq-root`, the
column that clips it with `overflow: hidden`):

    width   height   over
    1440    500      125.4px hanging below the column
    1440    600       90.9px hanging below the column
    1440    650       40.9px hanging below the column
    2560    600       94.9px hanging below the column
     769    690       18.3px hanging below the column
     769    710       -1.7px (fits)

The defect runs from the 460px the earlier fix drew all the way out to
roughly 690-710px, depending on width — every one of those is a completely
ordinary desktop BROWSER WINDOW, not an exotic device: a laptop with the
window not maximized, a window snapped to the top or bottom half of a
1080p display, a video call with a shared-screen strip taking room at the
top. `.office.pxhq-root` was `overflow: hidden` there with nothing offering
a scrollbar, so the bottom of the office — same as #361's 926x428 case —
was not off-screen, it was unreachable.

THE FIX does not add another height number to eventually be wrong about.
`.office.pxhq-root` now scrolls (`overflow-y: auto`) unconditionally, at
every width and every height, instead of only inside the one media query
band #361 measured. A tall desktop where `.pxhq` already fits shows no
scrollbar — nothing about that case changes, and `#362`'s suite (the
480px-floor control at 1280x800) is left running unchanged to prove it.
A short one gets a real scroll affordance instead of a silently clipped
floor. Reaching the very bottom of the office at these widths takes two
scroll gestures rather than one — the column, then `.px-scene`'s own
internal scroll inside `.pxhq` — which is a rougher affordance than the
single-scroller ideal #361 reached for on a phone, but nothing is clipped
away from a wheel or a trackpad any more, which is the property this suite
asserts.

NO NEW DEPENDENCY. Imports the CDP harness from #352's suite, same as
#361's and #356's suites do.

Run: python3 scripts/test_a_short_desktop_window_does_not_swallow_the_office_floor.py
"""
from __future__ import annotations

import http.server
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

_SPEC = importlib.util.spec_from_file_location(
    'office_phone_harness',
    ROOT / 'scripts'
    / 'test_the_office_ticker_and_the_lobby_door_are_measured_on_a_real_phone.py')
H = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(H)

FAILS = []

# The band the earlier fix's `max-height: 460px` missed. 769x690 is well
# inside the measured overhang for narrow desktop widths (18px hanging
# below the column at rest) — comfortably past the old 460px threshold and
# proof it was wrong. 1440x500 is the headline case: an entirely ordinary
# half-height window on a laptop. 2560x600 checks a wide monitor with a
# short window doesn't escape the fix by width. 1280x800 is #362's own
# control — a tall desktop that must keep its 480px floor and show no
# scrollbar at all.
SHORT_VIEWPORTS = [(769, 690), (1440, 500), (2560, 600)]
TALL_CONTROL = (1280, 800)

SCAN_JS = r"""(() => {
  const box = e => e ? (r => ({top: r.top, bottom: r.bottom, height: r.height}))
                       (e.getBoundingClientRect()) : null;
  const root = document.querySelector('.office.pxhq-root');
  const hq = document.querySelector('.pxhq');
  const scene = document.querySelector('.px-scene');
  const door = document.querySelector('.px-meetdoor');
  if (!root || !hq) return null;
  const rootCs = getComputedStyle(root);
  const before = {
    innerWidth: innerWidth, innerHeight: innerHeight,
    openBackdrops: document.querySelectorAll('.backdrop').length,
    rootOverflowY: rootCs.overflowY,
    rootScrollH: root.scrollHeight, rootClientH: root.clientHeight,
    minHeight: getComputedStyle(hq).minHeight,
    root: box(root), hq: box(hq), door: box(door),
  };
  // Scroll every scroller on the way from the door up to the root as far
  // as it will go — the same "walk every scroller to its max" #361's WIDE_JS
  // does — then ask whether the door ended up inside the root's own box.
  for (let e = door; e && e !== root.parentElement; e = e.parentElement) {
    if (e.scrollHeight - e.clientHeight > 1) e.scrollTop = e.scrollHeight - e.clientHeight;
  }
  return new Promise(res => requestAnimationFrame(() => requestAnimationFrame(() => {
    const rr = root.getBoundingClientRect();
    const dr = door ? door.getBoundingClientRect() : null;
    res({
      before,
      rootBoxAfter: box(root),
      doorBoxAfter: dr ? { top: dr.top, bottom: dr.bottom } : null,
      doorReachable: dr ? (dr.bottom <= rr.bottom + 0.5 && dr.top >= rr.top - 0.5) : null,
    });
  })));
})()"""


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def boot(ws, url, width, height):
    ws.call('Emulation.setDeviceMetricsOverride', {
        'width': width, 'height': height, 'deviceScaleFactor': 2, 'mobile': False})
    ws.call('Page.navigate', {'url': url})
    H.wait_for(ws, "!!document.querySelector('.app')", 45, 'the app to mount')
    H.wait_for(ws, "!document.getElementById('cafreso-boot')", 20,
               'the boot splash to clear')
    H.evaluate(ws, """(() => {
      const b = [...document.querySelectorAll('.rail nav a, .rail a, nav a')]
        .find(x => /Office/i.test(x.textContent || ''));
      if (b) b.click();
      return !!b;
    })()""")
    H.wait_for(ws, "!!document.querySelector('.office-wrap .px-scene')", 30,
               'the Office tab to render its floor')
    for _ in range(8):
        if not H.evaluate(ws, "document.querySelectorAll('.backdrop').length"):
            break
        H.press_escape(ws)
        time.sleep(0.4)
    H.evaluate(ws, """(() => {
      const x = document.querySelector('.gs-coach button[title="Dismiss"]');
      if (x) x.click();
      return !!x;
    })()""")
    H.wait_for(ws, "!document.querySelector('.gs-coach')", 15,
               'the getting-started coach to be dismissed')
    H.wait_for(ws, "!!document.querySelector('.px-meetdoor')", 30,
               'the lobby to draw its meeting door')
    return H.evaluate(ws, SCAN_JS)


def assert_short(m, width, height):
    tag = f'{width}x{height}'
    n = lambda v: 'null' if v is None else round(v, 1)  # noqa: E731

    check(f'[{tag}] the app rendered so it could be measured', m is not None,
          'no .office.pxhq-root / .pxhq in the DOM')
    if m is None:
        return
    b = m['before']
    check(f'[{tag}] the viewport is the one we asked for',
          b['innerWidth'] == width and b['innerHeight'] == height,
          f"{b['innerWidth']}x{b['innerHeight']}")
    check(f'[{tag}] no dialog is covering the floor', b['openBackdrops'] == 0,
          f"{b['openBackdrops']} .backdrop still open")

    # The bug: .pxhq keeps the desktop 480px floor here (this band is
    # deliberately outside the min-height:0 media query), so the column
    # WILL be shorter than its content. That is expected and not itself
    # the defect — the defect is the column offering no way to reach it.
    check(f'[{tag}] the office floor is still narrower than the column '
          '(this band keeps the 480px floor on purpose)',
          b['rootScrollH'] - b['rootClientH'] > 20,
          f"scrollHeight {b['rootScrollH']} vs clientHeight {b['rootClientH']} — "
          'if these are equal at this height the floor stopped needing a '
          'scrollbar here and the viewport list should move on')

    # ---- THE FIX ----
    check(f'[{tag}] the column offers a scrollbar instead of clipping',
          b['rootOverflowY'] in ('auto', 'scroll'),
          f"overflow-y: {b['rootOverflowY']} — hidden here is exactly the "
          'shape #361 found at 926x428: a box with scroll room and no way '
          'for a wheel or a trackpad to reach it')
    check(f'[{tag}] the lobby door is reachable by scrolling',
          m['doorReachable'] is True,
          f"door ended at {m['doorBoxAfter']} against a column at "
          f"{m['rootBoxAfter']} after scrolling every ancestor to its max — "
          'still outside the column means still unreachable, scrollbar or not')
    print(f'        root scrollH {b["rootScrollH"]} clientH {b["rootClientH"]} · '
          f'overflow-y {b["rootOverflowY"]} · door reachable {m["doorReachable"]}')


def assert_tall_control(m, width, height):
    tag = f'{width}x{height}'
    check(f'[{tag}] the app rendered so it could be measured', m is not None,
          'no .office.pxhq-root / .pxhq in the DOM')
    if m is None:
        return
    b = m['before']
    check(f'[{tag}] a tall desktop keeps its 480px office floor',
          b['minHeight'] == '480px', f"min-height: {b['minHeight']}")
    check(f'[{tag}] a tall desktop needs no scrollbar — the floor already fits',
          b['rootScrollH'] - b['rootClientH'] <= 1,
          f"scrollHeight {b['rootScrollH']} vs clientHeight {b['rootClientH']} — "
          'the unconditional overflow-y:auto must be invisible here, not just '
          'harmless: a control that silently regressed to a visible scrollbar '
          'on an ordinary desktop would be its own bug')
    print(f'        min-height {b["minHeight"]} · scrollH {b["rootScrollH"]} '
          f'clientH {b["rootClientH"]}')


def main():
    print('A short desktop window does not swallow the office floor')

    if not (ROOT / 'dist-ui' / 'manifest.json').exists():
        print('  FAIL  the HQ UI is built  — dist-ui/manifest.json is missing; '
              'run `npm install && npm run build` first')
        print('\n1 FAILED — the HQ UI is built')
        return 1

    chrome = H.find_chrome()
    if chrome is None:
        print('  SKIPPED — no headless browser on this machine.')
        print('\nnothing measured')
        return 0
    print(f'  using  {chrome}')

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{srv.server_address[1]}/hq.html'

    profile = tempfile.mkdtemp(prefix='cafresohq-shortdesk-')
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
        ws = H.WS(page['webSocketDebuggerUrl'])
        ws.call('Page.enable')
        ws.call('Runtime.enable')

        for width, height in SHORT_VIEWPORTS:
            try:
                m = boot(ws, url, width, height)
            except Exception as exc:
                check(f'[{width}x{height}] the app rendered so it could be '
                      'measured', False, f'{type(exc).__name__}: {exc}')
                continue
            assert_short(m, width, height)

        width, height = TALL_CONTROL
        try:
            m = boot(ws, url, width, height)
        except Exception as exc:
            check(f'[{width}x{height}] the app rendered so it could be '
                  'measured', False, f'{type(exc).__name__}: {exc}')
            m = None
        assert_tall_control(m, width, height)
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
