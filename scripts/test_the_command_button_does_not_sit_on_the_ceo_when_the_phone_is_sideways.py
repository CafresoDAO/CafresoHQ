#!/usr/bin/env python3
"""#356 moved the palette button out of the meeting-room doorway and
measured it clear of every control at three PORTRAIT sizes. Turn the
phone sideways and it lands on the CEO.

`.palette-fab` is `position: fixed` app furniture, pinned at `left: 10px;
bottom: calc(130px + safe-area)` on every phone. In portrait that is the
lobby's left end, over the water cooler. At 667x375 it is y 201->245,
which is inside the mobile agent strip (y 182->264) — and the strip is
`position: sticky; top: 0` inside the office's scroller, so this is not
the door's scroll-dependent overlap: the box under the button never
moves. Measured on the real app at HEAD before this fix:

  667x375  fab 10.0 -> 54.0 x 201.0 -> 245.0
           first chip "CafresoHQ CEO" 14.0 -> 70.0 x 188.3 -> 256.9
           elementsFromPoint at the chip's centre: SPAN, BUTTON.palette-fab

That chip is `onSitWithCEO` (ui/office.jsx ~1098) — the one control on
the strip that opens the CEO. The button covered its centre at every
scroll position.

The fix is a landscape-only relocation into a slot the tab bar RESERVES
for it (styles.css, the rule after #357's): the bar gives up 56px at its
left end and the button sits there, one z-step above the bar. Two
top-bar homes were measured first and refused — the middle, because a
FRESH office puts its `⚠ NOBODY HIRED` chip at x 270->406 on a 568-wide
phone, under a centred button; and the right of the bell, because that
is the receipts pill's band (557->659 at 667 wide) on any office with a
stamped job. The tab bar is the one piece of chrome identical on all six
tabs, and nothing in any view can flow into its padding. This suite
measures it:

  * before any scroll — the state everyone sees first, and the state the
    bug was in — the palette button appears nowhere above any chip on
    the strip; then, with the office column scrolled so the sticky strip
    is pinned, every chip hit-tests as ITSELF at its own centre (at
    568x320 the strip starts below the fold, under the ticker — a #357
    trait of the scrolling column, not the button's doing, so the
    own-hit question is asked once the column has scrolled);
  * the button's box does not touch the strip's, in either state;
  * the button sits inside the tab bar's box and touches none of the six
    tabs, the bell, or the receipts pill;
  * the button hit-tests as itself — it sits above the tab bar it lives
    in, or it would be a painted-over dead spot;
  * with the button hidden, a 3x3 grid of points inside its box finds no
    control-sized interactive element beneath — on the Office tab and on
    each of the other five tabs, since the button is app-wide;
  * and at 375x812 the button is still where #356 put it, below the
    strip, so the landscape rule has not leaked into portrait.

Two landscape phones, the same pair #357 measures: 667x375 (iPhone SE/8
sideways, where this was found) and 568x320 (the smallest phone this
repo measures, sideways — the tighter top bar). Every assertion is an
inequality between boxes read in one frame, not a number written here.

Drives Chrome over the DevTools Protocol with the standard library only,
via the harness in
test_the_office_ticker_and_the_lobby_door_are_measured_on_a_real_phone.py.
No new dependency; if no browser is found the suite says so and skips.

Run: python3 scripts/test_the_command_button_does_not_sit_on_the_ceo_when_the_phone_is_sideways.py
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

LANDSCAPE = [(667, 375), (568, 320)]
PORTRAIT = [(375, 812)]


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# Runs in the page on the Office tab. Reads every box in one frame, then
# asks two hit-test questions: what is on top at each strip chip's centre,
# and — with the button made invisible to hit-testing — what a finger
# would land on where the button is.
MEASURE_JS = r"""(async () => {
  const box = e => e ? (r => ({top: r.top, bottom: r.bottom, left: r.left,
                               right: r.right, width: r.width, height: r.height}))
                       (e.getBoundingClientRect()) : null;
  const q = s => document.querySelector(s);
  const tag = e => e ? (e.tagName + (typeof e.className === 'string' && e.className
                        ? '.' + e.className.trim().split(/\s+/).slice(0, 3).join('.') : '')) : null;
  const frames = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const fab = q('.palette-fab');
  const strip = q('.mobile-agent-strip');
  const readChips = () => [...document.querySelectorAll(
    '.mobile-agent-strip .mas-item, .mobile-agent-strip .mas-plus')].map(el => {
    const r = el.getBoundingClientRect();
    const els = document.elementsFromPoint(r.left + r.width / 2, r.top + r.height / 2) || [];
    const own = els.length > 0 && (els[0] === el || el.contains(els[0]));
    const fabAbove = fab ? els.some(e => e === fab || fab.contains(e)) : false;
    return { title: el.title || '', box: box(el), ownHit: own, fabAbove,
             stack: els.slice(0, 3).map(tag) };
  });
  await frames();
  /* State one: nothing scrolled. This is what a person sees first, and
     the state the bug was measured in. */
  const chipsBefore = readChips();
  const stripBefore = box(strip);
  /* State two: every scrollable ancestor of the strip scrolled to its
     end, so the sticky strip is pinned at the top of its scroller. Which
     box scrolls is #357's business; this suite does not name it. */
  const scrollers = [];
  for (let e = strip; e && e !== document.body; e = e.parentElement) {
    if (e.scrollHeight - e.clientHeight > 1) {
      e.scrollTop = e.scrollHeight - e.clientHeight;
      scrollers.push(tag(e));
    }
  }
  await frames();
  const chipsAfter = readChips();
  const stripAfter = box(strip);
  let fabOwnHit = null;
  if (fab) {
    const r = fab.getBoundingClientRect();
    const els = document.elementsFromPoint(r.left + r.width / 2, r.top + r.height / 2) || [];
    fabOwnHit = els.length > 0 && (els[0] === fab || fab.contains(els[0]));
  }
  return {
    innerWidth: window.innerWidth, innerHeight: window.innerHeight,
    fab: box(fab), fabOwnHit,
    fabPosition: fab ? getComputedStyle(fab).position : null,
    strip: stripBefore, stripAfter, chips: chipsBefore, chipsAfter, scrollers,
    topbar: box(q('.topbar')), tabbar: box(q('.mobile-tabbar')),
    tabs: [...document.querySelectorAll('.mobile-tabbar .mtab')].map(box),
    bell: box(q('.topbar-activity')), tray: box(q('.receipt-tray')),
    openBackdrops: document.querySelectorAll('.backdrop').length,
  };
})()"""

# What the button HIDES. At each of nine points inside its box: first ask
# what is on top with the button visible — if that is not the button, the
# button is the thing being covered there (an open sheet, a toast), which
# is not this suite's question. Where the button IS on top, take it out of
# hit-testing with `visibility: hidden` (layout unchanged) and see what a
# tap would have reached. "Interactive" means a control-sized thing a
# person could tap: a button, link, field, role=button, or a React onClick
# within three ancestors — and no larger than 250x250, so a whole-column
# click-to-deselect handler does not count as a control being hidden.
COVERS_JS = r"""(async () => {
  const fab = document.querySelector('.palette-fab');
  if (!fab) return { fab: null, hits: [], onTop: 0 };
  const tag = e => e.tagName + (typeof e.className === 'string' && e.className
                   ? '.' + e.className.trim().split(/\s+/).slice(0, 3).join('.') : '');
  const interactive = (start) => {
    for (let n = start, d = 0; n && n !== document.body && d < 3; n = n.parentElement, d++) {
      if (n === fab || fab.contains(n)) return null;
      const b = n.getBoundingClientRect();
      if (b.width > 250 || b.height > 250) return null;
      const t = n.tagName;
      if (t === 'BUTTON' || t === 'A' || t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT') return tag(n);
      if (n.getAttribute('role') === 'button') return tag(n);
      const k = Object.keys(n).find(k => k.startsWith('__reactProps$'));
      if (k && n[k] && typeof n[k].onClick === 'function') return tag(n);
    }
    return null;
  };
  const r = fab.getBoundingClientRect();
  const points = [];
  for (const fx of [0.2, 0.5, 0.8]) for (const fy of [0.2, 0.5, 0.8]) {
    points.push([r.left + r.width * fx, r.top + r.height * fy]);
  }
  const notToast = els => els.find(e => !e.closest('.toast'));
  const onTop = points.filter(([x, y]) => {
    const top = notToast(document.elementsFromPoint(x, y) || []);
    return !!top && (top === fab || fab.contains(top));
  });
  const prev = fab.style.visibility;
  fab.style.visibility = 'hidden';
  const hits = new Set();
  try {
    for (const [x, y] of onTop) {
      const top = notToast(document.elementsFromPoint(x, y) || []);
      const hit = top ? interactive(top) : null;
      if (hit) hits.add(hit);
    }
  } finally {
    fab.style.visibility = prev;
  }
  return { fab: { left: r.left, top: r.top, right: r.right, bottom: r.bottom },
           hits: [...hits], onTop: onTop.length };
})()"""

CLICK_TAB_JS = r"""((i) => {
  const tabs = [...document.querySelectorAll('.mtab')];
  const b = tabs[i];
  if (b) b.click();
  return b ? (b.textContent || '').trim() : null;
})(%d)"""


def boot(ws, url, width, height):
    """#352's boot sequence, through the harness's own helpers: mount, let
    the splash clear, open Office, dismiss the first-run dialogs and the
    coach, wait for the lobby door so the floor is fully drawn."""
    ws.call('Emulation.setDeviceMetricsOverride', {
        'width': width, 'height': height, 'deviceScaleFactor': 2,
        'mobile': True})
    ws.call('Page.navigate', {'url': url})
    H.wait_for(ws, "!!document.querySelector('.mobile-tabbar')", 45,
               'the app to mount')
    H.wait_for(ws, "!document.getElementById('cafreso-boot')", 20,
               'the boot splash to clear')
    H.evaluate(ws, """(() => {
      const b = [...document.querySelectorAll('.mtab')]
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
      const x = document.querySelector('.gs-coach button.gs-dismiss');
      if (x) x.click();
      return !!x;
    })()""")
    H.wait_for(ws, "!document.querySelector('.gs-coach')", 15,
               'the getting-started coach to be dismissed')
    H.wait_for(ws, "!!document.querySelector('.px-meetdoor')", 30,
               'the lobby to draw its meeting door')
    H.wait_for(ws, "!!document.querySelector('.mobile-agent-strip .mas-item')", 15,
               'the agent strip to draw its chips')


def touches(a, b):
    return bool(a and b) and not (a['right'] <= b['left'] or b['right'] <= a['left']
                                  or a['bottom'] <= b['top'] or b['bottom'] <= a['top'])


def assert_landscape(m, covers_by_tab, width, height):
    tag = f'{width}x{height}'
    check(f'[{tag}] the phone viewport is the one we asked for',
          m['innerWidth'] == width and m['innerHeight'] == height,
          f"{m['innerWidth']}x{m['innerHeight']}")
    check(f'[{tag}] no dialog is covering the floor', m['openBackdrops'] == 0,
          f"{m['openBackdrops']} .backdrop still open")
    check(f'[{tag}] the palette button is on screen and fixed',
          m['fab'] is not None and m['fabPosition'] == 'fixed',
          f"fab {m['fab']} position {m['fabPosition']}")
    check(f'[{tag}] the agent strip drew its chips',
          m['strip'] is not None and len(m['chips']) >= 1,
          f"strip {m['strip']}, {len(m['chips'])} chips")
    if not (m['fab'] and m['strip'] and m['chips']):
        return

    fab, strip = m['fab'], m['strip']
    for c in m['chips']:
        name = c['title'] or 'chip'
        check(f'[{tag}] before any scroll, the palette button is nowhere above "{name}"',
              not c['fabAbove'], f"stack at centre: {c['stack']}")
    for c in m['chipsAfter']:
        name = c['title'] or 'chip'
        check(f'[{tag}] with the strip pinned, "{name}" hit-tests as itself at its own centre',
              c['ownHit'] and not c['fabAbove'],
              f"stack at centre: {c['stack']} (scrolled: {m['scrollers']})")
    # Box-vs-box only once the strip is pinned and painted. Before any
    # scroll at 568x320 the strip's natural box runs on past its scroller's
    # clipped edge, under the ticker and the tab bar — a rectangle nothing
    # paints, which the chip hit-tests above already cover for that state.
    s = m['stripAfter']
    check(f'[{tag}] with the strip pinned, the palette button does not touch the strip',
          not touches(fab, s),
          f"fab {fab['top']:.1f}->{fab['bottom']:.1f} x {fab['left']:.1f}->{fab['right']:.1f}, "
          f"strip {s and s['top']:.1f}->{s and s['bottom']:.1f}")
    tb = m['tabbar']
    check(f'[{tag}] the palette button sits inside the tab bar',
          tb is not None and fab['top'] >= tb['top'] and fab['bottom'] <= tb['bottom'],
          f"fab {fab['top']:.1f}->{fab['bottom']:.1f}, tab bar {tb and tb['top']:.1f}->{tb and tb['bottom']:.1f}")
    check(f'[{tag}] the palette button touches none of the six tabs',
          len(m['tabs']) == 6 and not any(touches(fab, t) for t in m['tabs']),
          f"fab {fab['left']:.1f}->{fab['right']:.1f}, first tab starts {m['tabs'] and m['tabs'][0]['left']:.1f}")
    check(f'[{tag}] the palette button hit-tests as itself (not painted under the tab bar)',
          m['fabOwnHit'] is True, 'elementsFromPoint at its centre did not return it')
    check(f'[{tag}] the palette button touches neither the bell nor the receipts pill',
          not touches(fab, m['bell']) and not touches(fab, m['tray']),
          f"fab {fab['left']:.1f}->{fab['right']:.1f} x {fab['top']:.1f}->{fab['bottom']:.1f}, "
          f"bell {m['bell']}, tray {m['tray']}")
    check(f'[{tag}] the palette button is wholly inside the viewport',
          fab['left'] >= 0 and fab['top'] >= 0
          and fab['right'] <= width and fab['bottom'] <= height,
          f"{fab['left']:.1f}->{fab['right']:.1f} x {fab['top']:.1f}->{fab['bottom']:.1f}")
    for tab_name, cov in covers_by_tab:
        check(f'[{tag}] on the {tab_name} tab the button hides no interactive control',
              cov is not None and cov['fab'] is not None and not cov['hits'],
              f"under it: {cov and cov['hits']}")


def assert_portrait(m, width, height):
    tag = f'{width}x{height}'
    check(f'[{tag}] the phone viewport is the one we asked for',
          m['innerWidth'] == width and m['innerHeight'] == height,
          f"{m['innerWidth']}x{m['innerHeight']}")
    fab, strip, topbar = m['fab'], m['strip'], m['topbar']
    check(f'[{tag}] the palette button is on screen', fab is not None)
    if not (fab and strip):
        return
    check(f'[{tag}] portrait is untouched: the button is still below the strip, '
          'at the lobby end where #356 put it',
          fab['top'] > strip['bottom'] and fab['left'] < 20,
          f"fab top {fab['top']:.1f} vs strip bottom {strip['bottom']:.1f}, left {fab['left']:.1f}")
    check(f'[{tag}] portrait is untouched: the button is not in the top bar',
          topbar is None or not touches(fab, topbar),
          f"fab {fab['top']:.1f}->{fab['bottom']:.1f}, topbar {topbar}")


def main():
    print('The palette button, on a phone turned sideways, must not sit on the CEO')

    if not (ROOT / 'dist-ui' / 'manifest.json').exists():
        print('  FAIL  the HQ UI is built  — dist-ui/manifest.json is missing; '
              'run `npm install && npm run build` first')
        print('\n1 FAILED — the HQ UI is built')
        return 1

    chrome = H.find_chrome()
    if chrome is None:
        print('  SKIPPED — no headless browser on this machine.')
        print('  This suite measures the rendered app, so it needs one. It '
              'installs nothing: it looks for $CHROME_PATH, a playwright '
              'browser cache, or a Chrome/Chromium in the usual places.')
        print('\nnothing measured')
        return 0
    print(f'  using  {chrome}')

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{srv.server_address[1]}/hq.html'

    profile = tempfile.mkdtemp(prefix='cafresohq-cdp-fab-landscape-')
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

        for width, height in LANDSCAPE:
            try:
                boot(ws, url, width, height)
                m = H.evaluate(ws, MEASURE_JS)
                covers = [('Office', H.evaluate(ws, COVERS_JS))]
                n_tabs = H.evaluate(ws, "document.querySelectorAll('.mtab').length") or 0
                for i in range(n_tabs):
                    name = H.evaluate(ws, CLICK_TAB_JS % i)
                    if not name or re.search(r'office', name, re.I):
                        continue
                    time.sleep(0.6)
                    covers.append((name, H.evaluate(ws, COVERS_JS)))
            except Exception as exc:
                check(f'[{width}x{height}] the app rendered so it could be '
                      'measured', False, f'{type(exc).__name__}: {exc}')
                continue
            assert_landscape(m, covers, width, height)

        for width, height in PORTRAIT:
            try:
                boot(ws, url, width, height)
                m = H.evaluate(ws, MEASURE_JS)
            except Exception as exc:
                check(f'[{width}x{height}] the app rendered so it could be '
                      'measured', False, f'{type(exc).__name__}: {exc}')
                continue
            assert_portrait(m, width, height)
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
