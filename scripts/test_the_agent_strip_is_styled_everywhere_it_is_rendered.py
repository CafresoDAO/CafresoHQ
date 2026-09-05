#!/usr/bin/env python3
"""#361. The strip of coworker faces was drawn, but never dressed.

`ui/office.jsx ~417` decides the office is on a phone at `innerWidth <=
768` and renders `.mobile-agent-strip` — the sideways-scrolling row of
tappable coworker faces that stands in for the desktop rail once the rail
is gone. Every rule that gives that strip its shape lived in `@media
(max-width: 640px)`. Between those two numbers the strip was in the DOM
with NOTHING on it.

WHAT WAS MEASURED, before this fix:

  640x900  position sticky · padding 6px 0 · background paper
           .mas-scroll display flex · overflow-x auto
           .mas-item 56.0px wide · sprite-wrap 40px x 40px, radius 50%
           name font-size 7px · strip 65.1px tall

  660x900  position static · padding 0px · background transparent
           .mas-scroll display block · overflow-x visible
           .mas-item 656.0px wide · sprite-wrap 656px x 24px, radius 0px
           name font-size 15px · strip 67.5px tall
  700x500  the same, .mas-item 696.0px wide, sprite-wrap 696px x 24px
  767x600  the same, .mas-item 763.0px wide, sprite-wrap 763px x 24px
  667x375  the same, .mas-item 663.0px wide, sprite-wrap 663px x 24px

Twenty pixels of viewport width apart, and the same strip goes from a row
of round 40px portraits that scrolls sideways to a full-width vertical
stack whose portraits are letterboxed to 24px tall — a coworker's face
squashed flat across the whole column. It does not stick to the top of
the scrolling floor either, because `position: sticky` was in the block
that did not apply.

That band is where a landscape phone sits — 667x375 is inside it, and it
is the exact size #354 was reported at — and where small tablets and
half-width split-screen windows sit.

THE FIX aligns the CSS to the render gate, not the render gate to the
CSS. Those are NOT the same change: one shows the strip, properly dressed,
to everyone office.jsx already renders it for; the other stops rendering
it between 641 and 768. At those widths the app is already fully in its
mobile shell — the desktop rail is hidden and the bottom tab bar is up,
both decided on the same 768px test — so the strip is the ONLY surface
offering the coworker faces there. Taking it away would have removed the
feature from precisely the phones with nowhere else to get it.

SECOND FAULT, the one #354 wrote down and left. A big phone in landscape
(926x428, 932x430) is WIDER than 768, so it gets the desktop office, where
`.pxhq` keeps its desktop `min-height: 480px`.

  926x428  .pxhq 174.3 -> 654.3  (h 480.0, min-height 480px)
           inside .office.pxhq-root 108.8 -> 374.0, overflow: hidden
           280.3px of office hanging below its own container

An `overflow: hidden` box does not scroll to a wheel or a finger, so that
280px was not merely off-screen, it was unreachable. `.px-scene` inside it
scrolled 390px, but only within a 480px box whose bottom 215px were
already being clipped, so the tail of that scroll range moved the building
into a region nothing paints. This is the same shape of bug as #354 and
the opposite arithmetic: there the column had 136px of box for 153px of
furniture, here the column has 265px of box and a rule insisting on 480.

The fix drops the floor — `min-height: 0` at `(min-width: 769px) and
(max-height: 460px)` — and nothing else. `.pxhq` is `flex: 1 1 0%` in a
column already sized to the viewport, so with no floor it takes the 265px
that exist and `.px-scene` scrolls inside it: one scroller, nothing
clipped, no new pixel constant to be wrong about at the next screen size.

Measured on the fix, 2026-09-05:

  660x900  position sticky · .mas-item 56.0 · sprite 40x40 · name 7px
  926x428  .pxhq 174.8 -> 372.0 (h 197.2) inside a root ending 374.0
           one scroller, .px-scene, with 673px of room
           the lobby door 245.8 -> 279.8, inside the column's own box

NOTHING BELOW 641px MOVED and nothing above 768px did either. 375x812,
375x667, 320x568, 667x375 and 568x320 — the five sizes #338, #345, #352
and #357 guard — are all 768px wide or narrower, and 1024x768 / 1280x800
still report `min-height: 480px`. Both are asserted here, and both older
suites are run unchanged.

NO NEW DEPENDENCY. Like #354's suite, this one imports the CDP harness
from #352's rather than copying it. If no browser is on the machine it
says so and skips.

Run: python3 scripts/test_the_agent_strip_is_styled_everywhere_it_is_rendered.py
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

# Widths where office.jsx renders the strip. 640 and 375 are inside the old
# 640px CSS block and are the control: they must not move. 660, 700 and 767
# are the band that had no styling. 667x375 is the landscape phone from #354,
# which is in that band and is why this matters on a real device today.
STRIP_VIEWPORTS = [(375, 812), (640, 900), (660, 900), (700, 500),
                   (767, 600), (667, 375)]

# Wider than the strip's gate, so no strip — but short, which is the second
# fault. 1280x800 is the desktop control: its 480px floor must survive.
WIDE_VIEWPORTS = [(926, 428), (932, 430), (1280, 800)]


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def px(value):
    """'40px' -> 40.0, and None / 'auto' -> None rather than an exception."""
    if not value:
        return None
    hit = re.match(r'^(-?[\d.]+)px$', str(value).strip())
    return float(hit.group(1)) if hit else None


STRIP_JS = r"""(() => {
  const q = s => document.querySelector(s);
  const cs = e => e ? getComputedStyle(e) : null;
  const box = e => e ? (r => ({top: r.top, bottom: r.bottom,
                               width: r.width, height: r.height}))
                       (e.getBoundingClientRect()) : null;
  const strip = q('.mobile-agent-strip');
  const scroll = q('.mas-scroll');
  const item = q('.mas-item');
  const wrap = q('.mas-item .sprite-wrap');
  const name = q('.mas-item .mas-name');
  const s = cs(strip), sc = cs(scroll), w = cs(wrap), n = cs(name);
  return {
    innerWidth: window.innerWidth, innerHeight: window.innerHeight,
    present: !!strip,
    strip: box(strip), item: box(item),
    position: s && s.position,
    background: s && s.backgroundColor,
    paddingTop: s && s.paddingTop,
    borderBottom: s && s.borderBottomWidth,
    zIndex: s && s.zIndex,
    scrollDisplay: sc && sc.display,
    scrollOverflowX: sc && sc.overflowX,
    wrapWidth: w && w.width, wrapHeight: w && w.height,
    wrapRadius: w && w.borderRadius,
    nameFontSize: n && n.fontSize,
    itemCount: document.querySelectorAll('.mas-item').length,
    openBackdrops: document.querySelectorAll('.backdrop').length,
  };
})()"""

WIDE_JS = r"""(() => {
  const q = s => document.querySelector(s);
  const box = e => e ? (r => ({top: r.top, bottom: r.bottom, height: r.height}))
                       (e.getBoundingClientRect()) : null;
  const tag = e => e ? (e.tagName + (e.className ? '.' + String(e.className) : '')) : null;
  const door = q('.px-meetdoor');
  /* The RESTING layout, read before anything is scrolled. Scrolling first
     and measuring after is how an overhang hides from a test: pushing the
     column to its own scrollTop pulls `.pxhq`'s bottom back inside the
     container and the box that was 215px too tall reads as if it fit. It
     did not fit; it was dragged. So both boxes are taken here, at the
     position a person actually finds the office in. */
  const restingHq = box(q('.pxhq'));
  const restingRoot = box(q('.office.pxhq-root'));
  const rootEl = q('.office.pxhq-root');
  const rootClipsUnreachably = !!rootEl
    && rootEl.scrollHeight - rootEl.clientHeight > 1
    && ['hidden', 'clip'].includes(getComputedStyle(rootEl).overflowY);
  const scrollers = [];
  for (let e = door; e && e !== document.body; e = e.parentElement) {
    if (e.scrollHeight - e.clientHeight > 1) {
      e.scrollTop = e.scrollHeight - e.clientHeight;
      scrollers.push({tag: tag(e), max: e.scrollHeight - e.clientHeight,
                      overflowY: getComputedStyle(e).overflowY});
    }
  }
  return new Promise(res => requestAnimationFrame(() => requestAnimationFrame(() => {
    const hq = q('.pxhq'), root = q('.office.pxhq-root');
    res({
      innerWidth: window.innerWidth, innerHeight: window.innerHeight,
      stripPresent: !!q('.mobile-agent-strip'),
      restingHq, restingRoot, rootClipsUnreachably,
      pxhq: box(hq), root: box(root), door: box(door),
      ticker: box(q('.ticker')),
      minHeight: hq ? getComputedStyle(hq).minHeight : null,
      rootOverflow: root ? getComputedStyle(root).overflowY : null,
      scrollers,
      openBackdrops: document.querySelectorAll('.backdrop').length,
    });
  })));
})()"""


def boot(ws, url, width, height, js):
    """The same boot sequence #354's suite uses, through #352's helpers, so
    a change to how the app mounts lands in one place for all three."""
    ws.call('Emulation.setDeviceMetricsOverride', {
        'width': width, 'height': height, 'deviceScaleFactor': 2,
        'mobile': width <= 768})
    ws.call('Page.navigate', {'url': url})
    H.wait_for(ws, "!!document.querySelector('.app')", 45, 'the app to mount')
    H.wait_for(ws, "!document.getElementById('cafreso-boot')", 20,
               'the boot splash to clear')
    # The Office tab is reached through the phone tab bar below 768px and
    # through the desktop rail above it. Ask for both rather than assuming
    # which shell this width gets — which shell it gets is under test.
    H.evaluate(ws, """(() => {
      const b = [...document.querySelectorAll('.mtab, .rail nav a, .rail a, nav a')]
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
    return H.evaluate(ws, js)


def assert_strip(m, width, height):
    tag = f'{width}x{height}'
    n = lambda v: 'null' if v is None else round(v, 1)  # noqa: E731

    check(f'[{tag}] the phone viewport is the one we asked for',
          m['innerWidth'] == width and m['innerHeight'] == height,
          f"{m['innerWidth']}x{m['innerHeight']}")
    check(f'[{tag}] no dialog is covering the floor', m['openBackdrops'] == 0,
          f"{m['openBackdrops']} .backdrop still open")

    # office.jsx renders it at innerWidth <= 768. Every size in this list is
    # inside that, so if it is missing the render gate moved and the rest of
    # these assertions would be measuring nothing.
    check(f'[{tag}] the agent strip is rendered', m['present'],
          'ui/office.jsx ~417 renders .mobile-agent-strip at innerWidth <= 768')
    if not m['present']:
        return

    # ---- THE BUG. Every one of these came from the 640px block. ----
    check(f'[{tag}] the strip sticks to the top of the scrolling floor',
          m['position'] == 'sticky',
          f"position: {m['position']} — the faces scroll away with the floor "
          'instead of staying reachable')
    check(f'[{tag}] the strip has its own background',
          m['background'] not in (None, 'rgba(0, 0, 0, 0)', 'transparent'),
          f"background-color: {m['background']} — a sticky strip with no "
          'background has the office scrolling through it')
    check(f'[{tag}] the strip has its padding and its bottom rule',
          (px(m['paddingTop']) or 0) > 0 and (px(m['borderBottom']) or 0) > 0,
          f"padding-top {m['paddingTop']}, border-bottom {m['borderBottom']}")
    check(f'[{tag}] the faces lay out in a sideways-scrolling row',
          m['scrollDisplay'] == 'flex' and m['scrollOverflowX'] in ('auto', 'scroll'),
          f".mas-scroll display: {m['scrollDisplay']}, overflow-x: "
          f"{m['scrollOverflowX']} — as a block it stacks the faces down the "
          'column instead of scrolling them across it')

    # A face is a 56px column, not the width of the whole office. This is the
    # assertion that catches an unstyled strip even if someone later gives it
    # a background by another route.
    it = m['item']
    check(f'[{tag}] a face is a face-sized column, not the whole width',
          it is not None and it['width'] <= 120,
          f"a .mas-item is {n(it['width']) if it else '?'}px wide in a "
          f"{width}px viewport")
    wrap_w, wrap_h = px(m['wrapWidth']), px(m['wrapHeight'])
    check(f'[{tag}] the portrait is round and 40px, not a letterbox',
          wrap_w is not None and abs(wrap_w - 40) <= 1
          and wrap_h is not None and abs(wrap_h - 40) <= 1
          and '%' in str(m['wrapRadius']),
          f".sprite-wrap is {m['wrapWidth']} x {m['wrapHeight']} with radius "
          f"{m['wrapRadius']} — unstyled it stretches to the column width and "
          'squashes the coworker flat')
    fs = px(m['nameFontSize'])
    check(f'[{tag}] the name is the pixel label, not browser default text',
          fs is not None and fs <= 9,
          f"font-size: {m['nameFontSize']} — 15px is the UA default, which "
          'means no rule reached it')
    print(f'        strip h {n(m["strip"]["height"]) if m["strip"] else "?"} · '
          f'{m["position"]} · item {n(it["width"]) if it else "?"} · '
          f'portrait {m["wrapWidth"]}x{m["wrapHeight"]} · name {m["nameFontSize"]}')


def assert_wide(m, width, height):
    tag = f'{width}x{height}'
    n = lambda v: 'null' if v is None else round(v, 1)  # noqa: E731
    short = height <= 460

    check(f'[{tag}] the viewport is the one we asked for',
          m['innerWidth'] == width and m['innerHeight'] == height,
          f"{m['innerWidth']}x{m['innerHeight']}")
    check(f'[{tag}] no dialog is covering the floor', m['openBackdrops'] == 0,
          f"{m['openBackdrops']} .backdrop still open")
    # Above 768 the strip is not rendered at all, so the CSS move must not
    # have leaked upward into a layout it was never measured on.
    check(f'[{tag}] the agent strip is NOT rendered above its gate',
          not m['stripPresent'],
          'office.jsx renders it at innerWidth <= 768; seeing it here means '
          'the render gate moved, not the stylesheet')

    hq, root = m['pxhq'], m['root']
    check(f'[{tag}] the office building box is in the DOM',
          hq is not None and root is not None, '.pxhq / .office.pxhq-root')
    if not (hq and root):
        return

    if not short:
        # The desktop control. A tall desktop keeps its 480px floor — this
        # fix must be invisible there or it is a different change.
        check(f'[{tag}] a tall desktop keeps its 480px office floor',
              px(m['minHeight']) == 480,
              f"min-height: {m['minHeight']} — the short-viewport rule has "
              'leaked onto the desktop layout')
        print(f'        .pxhq {n(hq["top"])} -> {n(hq["bottom"])} · '
              f'min-height {m["minHeight"]}')
        return

    # ---- THE SECOND BUG. 480px of floor inside a 265px container that
    # clips with overflow: hidden. Measured at REST — see the note in the
    # measuring script about why scrolling first hides exactly this. ----
    rhq, rroot = m['restingHq'], m['restingRoot']
    over = rhq['bottom'] - rroot['bottom']
    check(f'[{tag}] the office does not hang past its own container',
          over <= 0.5,
          f".pxhq ends {n(rhq['bottom'])} inside a column ending "
          f"{n(rroot['bottom'])} — {n(over)}px hanging below an "
          f"overflow: {m['rootOverflow']} box")
    check(f'[{tag}] the office floor is not taller than the column that '
          'clips it',
          rhq['height'] <= rroot['height'] + 0.5,
          f".pxhq is {n(rhq['height'])}px inside a {n(rroot['height'])}px "
          'column — a floor bigger than its own container, which is what a '
          'desktop min-height does on a landscape phone')
    check(f'[{tag}] the column is not hiding office behind an unscrollable '
          'clip',
          not m['rootClipsUnreachably'],
          f"the office column has scroll room it will not give up: "
          f"overflow-y: {m['rootOverflow']} does not respond to a wheel or a "
          'finger, so everything past its bottom edge is unreachable rather '
          'than merely off-screen')
    check(f'[{tag}] the office is tall enough to hold its own lobby',
          rhq['height'] >= 70,
          f".pxhq is {n(rhq['height'])}px against a 70px lobby")
    print(f'        at rest .pxhq {n(rhq["top"])} -> {n(rhq["bottom"])} '
          f'(h {n(rhq["height"])}) · column {n(rroot["top"])} -> '
          f'{n(rroot["bottom"])} (h {n(rroot["height"])}) · min-height '
          f'{m["minHeight"]}')

    # One scroller with real room, the same shape #354 asserts: the floor is
    # reachable, and it is reachable through ONE box rather than a starved
    # flex line feeding a nested one.
    room = max([s['max'] for s in m['scrollers']] or [0])
    check(f'[{tag}] the office floor scrolls somewhere', room > 100,
          f'the most scroll room any ancestor of the lobby door has is '
          f'{round(room, 1)}px')
    for s in m['scrollers']:
        print(f'        scrolls {s["tag"]}  {round(s["max"], 1)}px of room')

    dr, tk = m['door'], m['ticker']
    check(f'[{tag}] the lobby door is drawn', dr is not None,
          'ui/office.jsx — the control that seats the team')
    if dr:
        inside = (dr['bottom'] <= root['bottom'] + 0.5
                  and dr['top'] >= root['top'] - 0.5)
        check(f'[{tag}] the door is inside the office column at max scroll',
              inside,
              f"door {n(dr['top'])} -> {n(dr['bottom'])} against a column "
              f"{n(root['top'])} -> {n(root['bottom'])}")
        print(f'        door {n(dr["top"])} -> {n(dr["bottom"])}')
    if tk:
        check(f'[{tag}] the office column ends above the ticker',
              root['bottom'] <= tk['top'] + 0.5,
              f"the column ends {n(root['bottom'])} against a ticker starting "
              f"{n(tk['top'])}")


def main():
    print('The agent strip, and the office on a big phone turned sideways')

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

    profile = tempfile.mkdtemp(prefix='cafresohq-cdp-agentstrip-')
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

        for width, height in STRIP_VIEWPORTS:
            try:
                m = boot(ws, url, width, height, STRIP_JS)
            except Exception as exc:
                check(f'[{width}x{height}] the app rendered so it could be '
                      'measured', False, f'{type(exc).__name__}: {exc}')
                continue
            assert_strip(m, width, height)

        for width, height in WIDE_VIEWPORTS:
            try:
                m = boot(ws, url, width, height, WIDE_JS)
            except Exception as exc:
                check(f'[{width}x{height}] the app rendered so it could be '
                      'measured', False, f'{type(exc).__name__}: {exc}')
                continue
            assert_wide(m, width, height)
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
