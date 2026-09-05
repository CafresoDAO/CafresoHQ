#!/usr/bin/env python3
"""#356 found a fixed button parked on the meeting door by measuring it. This
is the same shape, one floor up: the TOPBAR paints part of itself outside its
own box, at z-index 350, over the top of every view.

`.main` gives the topbar a hard 52px grid row. At ≤768px `.topbar` is told
`flex-wrap: wrap` and `.topbar .status` is given `flex-basis: 100%`, so the
bar becomes two or three flex lines — and the lines that do not fit in 52px
are not clipped (`overflow` is `visible` there on purpose, for the Apps
dropdown). They are painted below the bar, on top of whatever view is
underneath, and because the topbar carries `z-index: var(--z-dropdown)` they
win every hit test.

Measured before the fix, on a cold first run:

  375x812  .status-pinned  [10, 38.5, 297.7, 82.5]   30.5px below the bar
  375x667  .status-pinned  [10, 38.5, 297.7, 82.5]   30.5px below the bar
  320x568  .status-pinned  [10, 38.5, 297.7, 82.5]   30.5px below the bar
  667x375  .status         [10, 56.0, 657.0, 100.0]  48.0px below the bar

and what that cost a person:

  375x667  the Projects workspace mode toggle, box [13, 59, 95.8, 103],
           centre (54.4, 81) -> hit-tests as BUTTON.chip.chip-warn
  320x568  the same toggle, same centre -> BUTTON.chip.chip-warn
  667x375  the same toggle -> DIV.chip.mobile-hidden, AND the offline
           banner's Retry (centre 572.7, 90.3) and Hide (631, 90.3) ->
           DIV.status, on ALL FOUR content tabs (Office, Team, Library,
           Projects). Tapping Retry on a phone held sideways did nothing.

The landscape half of that has a name. `.mobile-hidden` — the class that
takes the desktop chips out of the bar — is declared at ≤640px, while every
other piece of the mobile shell switches on at ≤768px. Between those two
numbers the app wears the mobile shell and keeps the desktop chips, and 667
is exactly where an iPhone SE lands when you turn it. The comment beside the
⌗ ROOMS pill in app.jsx ~7250 already says this happened once and was fixed
"on ≤768px"; the class it reached for only ever hid at 640.

After the fix, at all four sizes, nothing inside `.topbar` extends below
`.topbar`'s own bottom edge, and no control anywhere in the app hit-tests as
something belonging to the topbar. The bar costs 95.5px in portrait (it was
always painting that much, it just did not admit it) and 63px in landscape —
not the 107px that growing the row alone would have cost, which is why the
two rules are a pair: at 107px the Team tab's "Hire a new coworker" and the
Projects CTA went under the mobile tab bar, trading one covered control for
two.

WHAT THIS ASSERTS, EXACTLY. Two things, per viewport:

  1. No descendant of `.topbar` has a bounding box that extends below
     `.topbar`'s own bottom. This is the structural invariant and it is what
     fails the moment someone puts the row back to a constant.
  2. Walking every on-screen control on each mobile tab, no control's own
     centre belongs to an element inside `.topbar`. This is the question a
     person tapping Retry actually asks.

Check 2 skips a control whose centre is clipped away by a scrolling or
overflow-hidden ancestor — the thing under such a point is whatever the clip
revealed, not a cover — and it skips `.toast`, for the reason the office
suite already documents: toasts are `position: fixed` app furniture that
float over the column for a few seconds, this harness serves the repo
statically so the office's autosave fails on a cold start and raises one, and
waiting them out makes it worse because they re-fire.

NO NEW DEPENDENCY. Same as the office suite: Chrome over the DevTools
Protocol with the standard library only, against a browser already on the
machine. If none is found this skips loudly rather than passing quietly.

Run: python3 scripts/test_the_topbar_does_not_paint_outside_itself_on_a_phone.py
"""
from __future__ import annotations

import http.server
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

# The office suite owns the harness — the CDP client, the repo server that
# assembles hq.html through ui_manifest, and the browser discovery. Importing
# it is deliberate: two copies of a websocket client is one too many, and the
# traps it learned (boot splash, first-run dialogs, toasts) are learned once.
import test_the_office_ticker_and_the_lobby_door_are_measured_on_a_real_phone as office  # noqa: E402

FAILS = []

# Portrait phones plus one landscape. 667x375 is not decoration: it is the
# only one of the four that lands in the 641–768px gap where `.mobile-hidden`
# stopped hiding, and it is where the worst of this measured.
VIEWPORTS = [(375, 812), (375, 667), (320, 568), (667, 375)]

# Every primary mobile tab. The Tools drawer is left out on purpose: it is a
# legitimately modal overlay, and everything it covers is covered by design.
TABS = [('chat', 'Chat'), ('visual', 'Office'), ('team', 'Team'),
        ('vault', 'Library'), ('projects', 'Projects')]


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ---------------------------------------------------------------- in-page JS
# Check 1: anything inside the topbar whose box ends below the topbar's.
SPILL_JS = r"""(() => {
  const tag = e => !e ? null : (e.tagName + (e.className && typeof e.className === 'string'
      ? '.' + e.className.trim().split(/\s+/).join('.') : '')).slice(0, 70);
  const bx = e => { const r = e.getBoundingClientRect();
    return [+r.left.toFixed(1), +r.top.toFixed(1), +r.right.toFixed(1), +r.bottom.toFixed(1)]; };
  const bar = document.querySelector('.topbar');
  if (!bar) return null;
  const br = bar.getBoundingClientRect();
  const spill = [];
  for (const e of bar.querySelectorAll('*')) {
    const r = e.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;      /* display:none, collapsed */
    if (r.bottom <= br.bottom + 0.5) continue;
    spill.push({t: tag(e), box: bx(e), over: +(r.bottom - br.bottom).toFixed(1)});
  }
  return {box: bx(bar), zIndex: getComputedStyle(bar).zIndex, spill};
})()"""

# Check 2: every on-screen control, is its own centre its own?
COVER_JS = r"""(() => {
  const tag = e => !e ? null : (e.tagName + (e.className && typeof e.className === 'string'
      ? '.' + e.className.trim().split(/\s+/).join('.') : '')).slice(0, 70);
  const bx = e => { const r = e.getBoundingClientRect();
    return [+r.left.toFixed(1), +r.top.toFixed(1), +r.right.toFixed(1), +r.bottom.toFixed(1)]; };
  const bar = document.querySelector('.topbar');
  const vw = innerWidth, vh = innerHeight;
  const out = [], seen = [];
  for (const el of document.querySelectorAll(
        'button, a, input, select, [role=button], .clickable')) {
    if (bar && bar.contains(el)) continue;          /* the bar's own controls */
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue;
    if (r.bottom <= 0 || r.top >= vh || r.right <= 0 || r.left >= vw) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity < 0.05) continue;
    if (el.disabled || el.closest('[aria-hidden=true]')) continue;
    /* A control can sit inside the window and still be invisible because a
       scrolling or overflow-hidden ancestor clipped it away. Intersect with
       every clipping ancestor and require the centre to survive; otherwise
       the "cover" reported would just be whatever the clip revealed. */
    let l = 0, t = 0, rr = vw, b = vh;
    for (let p = el.parentElement; p; p = p.parentElement) {
      const pcs = getComputedStyle(p);
      if (pcs.overflow === 'visible' && pcs.overflowX === 'visible'
          && pcs.overflowY === 'visible') continue;
      const pr = p.getBoundingClientRect();
      l = Math.max(l, pr.left); t = Math.max(t, pr.top);
      rr = Math.min(rr, pr.right); b = Math.min(b, pr.bottom);
    }
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    if (cx < l || cx > rr || cy < t || cy > b) continue;
    seen.push(1);
    /* elementsFromPoint, not elementFromPoint: skip toasts. See the docstring. */
    const stack = (document.elementsFromPoint(cx, cy) || []).filter(e => !e.closest('.toast'));
    const top = stack[0] || null;
    if (!top || !bar || !bar.contains(top)) continue;
    out.push({t: (el.getAttribute('aria-label') || el.getAttribute('title')
                  || el.textContent || '').trim().slice(0, 44),
              tag: tag(el), box: bx(el), c: [+cx.toFixed(1), +cy.toFixed(1)],
              top: tag(top), topBox: bx(top)});
  }
  return {scanned: seen.length, covered: out};
})()"""


def boot(ws, url, width, height):
    """Load the app at a phone size and get it to a state a person would see:
    no boot splash, no first-run dialog, no getting-started coach."""
    ws.call('Emulation.setDeviceMetricsOverride', {
        'width': width, 'height': height, 'deviceScaleFactor': 2, 'mobile': True})
    ws.call('Page.navigate', {'url': url})
    office.wait_for(ws, "!!document.querySelector('.mobile-tabbar')", 45,
                    'the app to mount')
    office.wait_for(ws, "!document.getElementById('cafreso-boot')", 20,
                    'the boot splash to clear')
    dismiss_first_run(ws)
    office.evaluate(ws, """(() => {
      const x = document.querySelector('.gs-coach button[title="Dismiss"]');
      if (x) x.click();
      return !!x;
    })()""")
    time.sleep(0.6)


def dismiss_first_run(ws):
    """A cold run with an empty team auto-opens the hire dialog. Close it the
    way a person would (Esc — modals/base.jsx ~202) rather than measuring
    underneath a backdrop."""
    for _ in range(8):
        if not office.evaluate(ws, "document.querySelectorAll('.backdrop').length"):
            return True
        office.press_escape(ws)
        time.sleep(0.4)
    return False


def open_tab(ws, label):
    return office.evaluate(ws, """(() => {
      const b = [...document.querySelectorAll('.mtab')].find(
        x => ((x.querySelector('.mtab-label') || {}).textContent || '').trim() === %r);
      if (b) b.click();
      return !!b;
    })()""" % label)


def run_viewport(ws, url, width, height):
    tag = f'{width}x{height}'
    boot(ws, url, width, height)

    # ---- check 1: the bar's box contains everything the bar paints ----
    m = office.evaluate(ws, SPILL_JS)
    check(f'[{tag}] the topbar is on screen', m is not None, '.topbar is not in the DOM')
    if m is None:
        return
    spill = m['spill']
    worst = max((s['over'] for s in spill), default=0.0)
    check(f'[{tag}] the topbar paints nothing below its own box',
          not spill,
          f"{[(s['t'], s['box']) for s in spill[:3]]} extend up to {worst}px below a "
          f"topbar whose box is {m['box']} — and the bar sits at z-index "
          f"{m['zIndex']}, so every one of those pixels wins the hit test "
          'against the view underneath. `overflow` is visible here on purpose; '
          'the grid row is what has to admit the height.')
    print(f'        topbar {m["box"]} · z-index {m["zIndex"]} · '
          f'{len(spill)} element(s) below it')

    # ---- check 2: nothing anywhere hit-tests as part of the topbar ----
    for key, label in TABS:
        if not open_tab(ws, label):
            check(f'[{tag}] the {label} tab has a bookmark in the tab bar', False,
                  'no .mtab with that label — MobileTabBar TAB_BOOKMARKS changed')
            continue
        time.sleep(1.2)
        dismiss_first_run(ws)
        r = office.evaluate(ws, COVER_JS)
        cov = r['covered']
        check(f'[{tag}] no control on the {label} tab is covered by the topbar',
              not cov,
              '; '.join(f"{c['t']!r} {c['tag']} centre {c['c']} hit-tests as "
                        f"{c['top']} {c['topBox']}" for c in cov[:3])
              + '. A tap there runs whatever the topbar spilled, not the control.')
        print(f'        {label}: {r["scanned"]} control(s) on screen, '
              f'{len(cov)} covered by the topbar')


def main():
    print('The topbar does not paint outside itself on a phone')

    if not (ROOT / 'dist-ui' / 'manifest.json').exists():
        print('  FAIL  the HQ UI is built  — dist-ui/manifest.json is missing; '
              'run `npm install && npm run build` first')
        print('\n1 FAILED — the HQ UI is built')
        return 1

    chrome = office.find_chrome()
    if chrome is None:
        print('  SKIPPED — no headless browser on this machine.')
        print('  This suite measures the rendered app, so it needs one. It does '
              'not install anything: it looks for $CHROME_PATH, a playwright '
              'browser cache, or a Chrome/Chromium in the usual places.')
        print('\nnothing measured')
        return 0
    print(f'  using  {chrome}')

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), office.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{srv.server_address[1]}/hq.html'

    profile = tempfile.mkdtemp(prefix='cafresohq-topbar-')
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
        ws = office.WS(page['webSocketDebuggerUrl'])
        ws.call('Page.enable')
        ws.call('Runtime.enable')

        for width, height in VIEWPORTS:
            try:
                run_viewport(ws, url, width, height)
            except Exception as exc:
                check(f'[{width}x{height}] the app rendered so it could be '
                      'measured', False, f'{type(exc).__name__}: {exc}')
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
