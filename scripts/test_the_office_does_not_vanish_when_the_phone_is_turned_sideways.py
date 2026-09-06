#!/usr/bin/env python3
"""#354. Turn the phone sideways and the office was GONE.

Every phone rule in styles.css was written against a portrait phone.
`test_the_office_ticker_and_the_lobby_door_are_measured_on_a_real_phone.py`
(#352) measures 375x812 and 375x667; #338 and #345 were both found and
fixed at portrait sizes. Landscape was never measured, and the office
column does not survive it.

WHAT WAS MEASURED, before this fix, at 667x375:

  .office-wrap        52.0 ->  375.0   (72px bottom padding for the tab bar)
    .section-title    52.0 ->   86.8   h  34.8
    .office.pxhq-root 108.8 ->  249.0  h 140.2   flex: 1 1 0%
      .office-task-rail   110.8 -> 180.8   h  70.0   flex: 0 1 auto
      .mobile-agent-strip 188.8 -> 256.3   h  67.5   flex: 0 1 auto
      .pxhq               256.3 -> 256.3   h   0.0   flex: 1 1 0%
    .ticker           261.0 ->  303.0  h  42.0
  .mobile-tabbar      305.0 ->  375.0

Read the root's line. The task rail and the agent strip are `flex: 0 1
auto` with `min-height: auto`, so their flex base size is their content
height and they cannot shrink below it: 70 + 67.5 plus 16px of gaps is
153.5px of furniture inside a container with 136.2px of content box.
`.pxhq` is `flex: 1 1 0%` — a zero flex base — so it is last in line for
space that ran out two items earlier, and #345's `min-height: 0` (which
is correct, and is what stops `.pxhq` overhanging the ticker at 375x667)
lets it resolve to exactly 0. `.pxhq` is `overflow: hidden`. The
building inside it is 698px tall and was drawn ENTIRELY outside a zero
height clip box: -355.2 -> 342.8 against a parent 256.3 -> 256.3. Not
small. Not clipped in half. Not on the screen at all.

`document.elementsFromPoint` at the lobby door's own centre returned
`['DIV.toast', 'NAV.mobile-tabbar', 'DIV.office-wrap', ...]` — the door
was not in its own stack, and neither was anything else belonging to
`.px-scene`. The one control that seats the team could not be tapped at
any scroll position, because there was no scroll position: `.px-scene`
had a 40px box and `scrollTop` was pinned at its 698px maximum.

This was NOT introduced by #345 out of nothing, and reverting #345 does
not fix it. Before #345 `.pxhq` had `min-height: 420px`, which at 375px
of viewport height would have drawn a 420px building over the ticker,
over the tab bar and off the bottom of the screen — the same fault #345
measured at 375x667, four times worse. The old rule and the new rule are
two answers to a question that has no answer at this size: the office
column is laid out to FIT the viewport, and at 375px of viewport height
its own fixed furniture does not fit.

THE FIX is to stop trying to fit it. On a short viewport the office
column scrolls instead: `.office.pxhq-root` becomes the scroller, and
`.pxhq` / `.px-scene` drop to their natural content height inside it, so
there is exactly ONE scroller on the landscape floor rather than a
starved flex line feeding a nested one. Nothing is hidden and no pixel
floor is invented — a floor is what broke this at both of its values.

Measured on the fix, 2026-09-05:

  667x375  .pxhq -537.7 -> 246.8  h 784.5, inside a root ending 249.0
           .office.pxhq-root scrolls 794 of 794
           door 198.8 -> 232.8, inside the root's own painted box
           the door is the topmost thing on the office floor
           ticker 261.0 -> 303.0 against a tab bar at 305.0 (2.0px)

  568x320  the same shape, measured live below.

The gate is `(max-width: 768px) and (max-height: 460px)`. The width half
keeps this strictly inside the mobile regime the rest of the office's
phone CSS already lives in (`@media (max-width: 768px)`, and `office.jsx
~417` renders the agent strip on the same 768px test), so this rule can
never fire against a layout it was not measured on. The height half is
below every portrait phone this repo has ever measured — 812, 667 and
568 — so all three are byte-for-byte untouched, and asserted so by the
#352 suite which is run unchanged.

DELIBERATELY NOT FIXED HERE. A large phone in landscape (926x428,
932x430) is WIDER than 768 and gets the desktop office layout, where
`.pxhq`'s un-overridden `min-height: 480px` overhangs a shorter root in
its own way. That is a different starvation with a different container
and it is not measured by this suite. Neither is `.mobile-agent-strip`'s
own gate mismatch: office.jsx renders it at `innerWidth <= 768` but its
styling (`position: sticky`, padding, background) lives in `@media
(max-width: 640px)`, so between 641px and 768px wide it draws unstyled
and static — which is exactly the band 667x375 sits in. Both are real
and both are separate tickets.

NO NEW DEPENDENCY. This suite imports the CDP harness from #352's suite
rather than copying it — same standard-library websocket client, same
static server, same first-run dialog dismissal, same browser discovery.
If no browser is on the machine it says so and skips.

Run: python3 scripts/test_the_office_does_not_vanish_when_the_phone_is_turned_sideways.py
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

# Two landscape phones. 667x375 is an iPhone SE / 8 turned sideways and is
# the size the fault was reported at. 568x320 is the smallest phone this
# repo measures anywhere, turned sideways — 55px shorter again, and the
# hardest case the rule has to hold at.
VIEWPORTS = [(667, 375), (568, 320)]


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# Scrolls EVERY scrollable ancestor of the lobby door to its bottom, rather
# than naming one element. Which layer owns the landscape floor's scrolling
# is precisely what this change moves, and a test that hardcodes the answer
# would go green on a layout where the door had quietly become unreachable
# through some other box. Then reads the boxes in one frame.
MEASURE_JS = r"""(() => {
  const box = e => e ? (r => ({top: r.top, bottom: r.bottom, left: r.left,
                               right: r.right, width: r.width, height: r.height}))
                       (e.getBoundingClientRect()) : null;
  const q = s => document.querySelector(s);
  const tag = e => e ? (e.tagName + (e.className ? '.' + String(e.className) : '')) : null;
  const door = q('.px-meetdoor');
  const scrollers = [];
  for (let e = door; e && e !== document.body; e = e.parentElement) {
    if (e.scrollHeight - e.clientHeight > 1) {
      e.scrollTop = e.scrollHeight - e.clientHeight;
      scrollers.push({tag: tag(e), top: e.scrollTop,
                      max: e.scrollHeight - e.clientHeight});
    }
  }
  return new Promise(res => requestAnimationFrame(() => requestAnimationFrame(() => {
    const scene = q('.px-scene');
    const hq = q('.pxhq');
    const root = q('.office.pxhq-root');
    const ticker = q('.ticker');
    const tabbar = q('.mobile-tabbar');
    const dr = door && door.getBoundingClientRect();
    let stack = [], doorIndex = -1, firstInScene = null, tabbarAbove = null;
    let cx = null, cy = null;
    if (dr) {
      cx = dr.left + dr.width / 2;
      cy = dr.top + dr.height / 2;
      const els = document.elementsFromPoint(cx, cy) || [];
      stack = els.map(tag);
      for (let i = 0; i < els.length; i++) {
        const e = els[i];
        if (e === door) doorIndex = i;
        if (firstInScene === null && scene && scene.contains(e)) firstInScene = i;
        if (tabbarAbove === null && tabbar && (e === tabbar || tabbar.contains(e))
            && (doorIndex === -1 || i < doorIndex)) tabbarAbove = tag(e);
      }
    }
    let tickerHit = null, tickerOwn = false;
    if (ticker) {
      const tr = ticker.getBoundingClientRect();
      /* Skip toasts, for the reason #352's suite writes out in full: this
         harness serves the repo statically, the office's autosave fails on
         a cold start, and a `position: fixed` toast legitimately floats over
         the column for a few seconds. The tab bar covering the ticker is
         the LAYOUT question, and it still fails this check. */
      const st = document.elementsFromPoint(tr.left + tr.width / 2,
                                            tr.top + tr.height / 2);
      const el = st.find(e => !e.closest('.toast')) || null;
      tickerHit = tag(el);
      tickerOwn = !!el && (el === ticker || ticker.contains(el));
    }
    res({
      innerHeight: window.innerHeight, innerWidth: window.innerWidth,
      wrap: box(q('.office-wrap')),
      root: box(root), pxhq: box(hq), scene: box(scene),
      building: box(q('.px-building')),
      rail: box(q('.office-task-rail')), strip: box(q('.mobile-agent-strip')),
      ticker: box(ticker), tickerHit, tickerOwn,
      tabbar: box(tabbar),
      tabbarFixed: tabbar ? getComputedStyle(tabbar).position : null,
      pxhqOverflow: hq ? getComputedStyle(hq).overflow : null,
      hasMore: !!(hq && hq.classList.contains('has-more')),
      scrollers,
      door: box(door), doorIndex, firstInScene, tabbarAbove, stack, cx, cy,
      openBackdrops: document.querySelectorAll('.backdrop').length,
    });
  })));
})()"""


def measure(ws, url, width, height):
    """Same boot sequence as #352's suite — its own helpers, so a change to
    how the app mounts or how the first-run dialogs are dismissed lands in
    one place and both suites follow it."""
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
    return H.evaluate(ws, MEASURE_JS)


def assert_viewport(m, width, height):
    tag = f'{width}x{height}'
    n = lambda v: 'null' if v is None else round(v, 1)  # noqa: E731

    check(f'[{tag}] the phone viewport is the one we asked for',
          m['innerHeight'] == height and m['innerWidth'] == width,
          f"{m['innerWidth']}x{m['innerHeight']}")
    check(f'[{tag}] no dialog is covering the floor',
          m['openBackdrops'] == 0,
          f"{m['openBackdrops']} .backdrop still open — everything below "
          'would be a measurement of the dialog')

    hq, root = m['pxhq'], m['root']
    check(f'[{tag}] the office building box is in the DOM', hq is not None
          and root is not None, '.pxhq / .office.pxhq-root missing')
    if not (hq and root):
        return

    # ---- THE BUG. `.pxhq` is `overflow: hidden`; at zero height that is
    # not a small office, it is no office. ----
    check(f'[{tag}] the office has a height at all', hq['height'] > 1,
          f".pxhq is {n(hq['height'])}px tall with overflow: "
          f"{m['pxhqOverflow']} — the {n(m['building']['height']) if m['building'] else '?'}"
          "px building inside it is drawn entirely outside its own clip box "
          'and the Office tab shows nothing')
    # A height alone is not enough: 20px of office with a 40px Situation
    # Wall in it is still an empty tab. The floor has to be able to hold
    # the lobby, which is where the door lives.
    lobby_min = 70
    check(f'[{tag}] the office is tall enough to hold its own lobby',
          hq['height'] >= lobby_min,
          f".pxhq is {n(hq['height'])}px against a {lobby_min}px lobby")
    print(f'        .pxhq {n(hq["top"])} -> {n(hq["bottom"])} '
          f'(h {n(hq["height"])}) · root {n(root["top"])} -> {n(root["bottom"])}')

    # ---- #345's fault, which must not come back at this size either ----
    over = hq['bottom'] - root['bottom']
    check(f'[{tag}] the building does not hang past its container',
          over <= 0.5,
          f".pxhq ends {n(hq['bottom'])} inside a container ending "
          f"{n(root['bottom'])} — {n(over)}px of overhang. Giving .pxhq a "
          'pixel floor to stop it collapsing is what causes this; the fix '
          'is a scroller, not a floor.')

    # ---- the column's own furniture does not sit on the ticker ----
    tk, tb = m['ticker'], m['tabbar']
    check(f'[{tag}] the office ticker is on screen', tk is not None)
    check(f'[{tag}] the mobile tab bar is on screen and fixed',
          tb is not None and m['tabbarFixed'] == 'fixed',
          f"position: {m['tabbarFixed']}")
    if tk and tb:
        gap = tb['top'] - tk['bottom']
        check(f'[{tag}] the ticker ends above the tab bar',
              tk['bottom'] <= tb['top'] + 0.5,
              f"ticker {n(tk['top'])} -> {n(tk['bottom'])} against a tab bar "
              f"at {n(tb['top'])} — overlap {n(-gap)}px")
        print(f'        ticker {n(tk["top"])} -> {n(tk["bottom"])} · '
              f'tab bar top {n(tb["top"])} · clearance {n(gap)}px')
    if tk:
        check(f'[{tag}] the office column ends above the ticker',
              root['bottom'] <= tk['top'] + 0.5,
              f"the office root ends {n(root['bottom'])} against a ticker "
              f"starting {n(tk['top'])} — the column is on top of it")
    check(f'[{tag}] the ticker hit-tests as itself', m['tickerOwn'],
          f"the ticker's own centre returned {m['tickerHit']}")

    # ---- the floor is reachable: SOMETHING scrolls, and the door lands
    # inside the office column's own painted box when it does ----
    # `> 100`, not `> 0`: the door and the lobby each report a dozen pixels
    # of scroll room of their own (`.pxhq .clickable::after { inset: -12px }`
    # is a touch target that overflows its box on purpose). Those are not a
    # way to reach the rest of a 698px building. One box has to carry it.
    room = max([s['max'] for s in m['scrollers']] or [0])
    check(f'[{tag}] the office floor scrolls somewhere',
          room > 100,
          f'the most scroll room any ancestor of the lobby door has is '
          f'{round(room, 1)}px — with a '
          f"{n(m['building']['height']) if m['building'] else '?'}px building "
          'in a container this short that means the rest of the office is '
          'unreachable, not that it fits')
    for s in m['scrollers']:
        print(f'        scrolls {s["tag"]}  {round(s["top"], 1)} of '
              f'{round(s["max"], 1)}')

    dr = m['door']
    check(f'[{tag}] the lobby door is drawn', dr is not None,
          'ui/office.jsx ~1655 — the control that seats the team')
    if dr:
        # Against the ROOT, not against `.px-scene`. On a short viewport
        # `.px-scene` is no longer the clipping box; the root is. Asserting
        # against whichever box actually clips is the whole point.
        inside = (dr['bottom'] <= root['bottom'] + 0.5
                  and dr['top'] >= root['top'] - 0.5)
        check(f'[{tag}] the door is inside the office column at max scroll',
              inside,
              f"door {n(dr['top'])} -> {n(dr['bottom'])} against a column "
              f"{n(root['top'])} -> {n(root['bottom'])} — outside it the door "
              'is clipped away and cannot be tapped at any scroll position')
        print(f'        door {n(dr["top"])} -> {n(dr["bottom"])}')

    # The hit test. "Topmost ON THE FLOOR", not topmost on the page, for
    # exactly the reason #352's suite documents: `.palette-fab` is a fixed
    # 40px button pinned near the bottom of every phone and it comes to
    # rest over the door's centre. That overlap is real, it is a separate
    # ticket, and asserting it away here would mean a red suite for a bug
    # this change is not fixing.
    check(f'[{tag}] the door hit-tests at its own centre',
          m['doorIndex'] >= 0,
          f"document.elementsFromPoint({n(m['cx'])}, {n(m['cy'])}) returned "
          f"{m['stack'][:4]} — the door is not in the stack at all, which is "
          'what a zero-height clip box looks like')
    check(f'[{tag}] the door is the topmost thing on the office floor',
          m['doorIndex'] >= 0 and m['firstInScene'] == m['doorIndex'],
          f"the first element of .px-scene under that point is "
          f"{m['stack'][m['firstInScene']] if m['firstInScene'] is not None else None}"
          ', not the door')
    check(f'[{tag}] the mobile tab bar is not over the door',
          m['tabbarAbove'] is None,
          f"{m['tabbarAbove']} is painted above the door at its own centre")

    # "There is more office below" is driven off `.px-scene`'s own scroll
    # room (office.jsx ~868). When the root takes over the scrolling that
    # room is zero, so the cue must be off — a hint pointing down at a
    # floor that does not scroll is the fault #338 left lit.
    if m['scene']:
        scene_scrolls = any('px-scene' in (s['tag'] or '') for s in m['scrollers'])
        check(f'[{tag}] the "more below" cue is not lit over a floor that '
              'does not scroll',
              scene_scrolls or not m['hasMore'],
              '.pxhq still carries .has-more while .px-scene has no scroll '
              'room — the cue claims depth the floor does not have')


def main():
    print('The office, on a phone turned sideways')

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

    profile = tempfile.mkdtemp(prefix='cafresohq-cdp-landscape-')
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
