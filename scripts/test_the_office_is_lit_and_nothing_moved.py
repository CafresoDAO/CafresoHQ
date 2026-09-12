#!/usr/bin/env python3
"""The office is lit, and nothing moved (#431).

The pixel scene's rooms were one tile fill each: no light source, no
ceiling, no floor under the desks, the building flat against the sky.
#431 adds light and depth as pure overlay — pseudo-elements and gradients
on layers that already exist — under two promises this suite measures in
a real headless browser rather than reads off the stylesheet:

  * every overlay takes no clicks (pointer-events: none) and sits on the
    plane below the desk set, so a coworker, a plate, a desk is exactly as
    clickable as before — asserted with elementFromPoint through the
    building's edge shade onto a desk sign;
  * nothing moved: with every overlay display:none'd, the floors, the
    interiors, the lobby, the street and the scene's scroll height are the
    same to the pixel — the phone suites measure those, and this layer
    must never be the reason one drifts.

Plus what the light IS: a daytime gradient stack in every room, a lamp
pool only where somebody sits (a vacant unit gets the moon and no lamp),
the lobby's spill at night, the sun's and moon's glow, and the star
twinkle behind prefers-reduced-motion: no-preference — the one animation
added, gated like every other ambient motion in the scene.

Run: python3 scripts/test_the_office_is_lit_and_nothing_moved.py
"""
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    'office_phone_harness',
    ROOT / 'scripts' / 'test_the_office_ticker_and_the_lobby_door_are_measured_on_a_real_phone.py')
H = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(H)
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + ((' — ' + str(detail)[:400]) if not cond else ''))
    if not cond:
        FAILS.append(name)
    return bool(cond)


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def boot_server(state_dir):
    port = free_port()
    env = dict(os.environ, PORT=str(port), CAFRESOHQ_HQ_STATE_DIR=state_dir,
               GAP_CRON='0', NEWS_CRON='0', TOPICS_CRON='0')
    for k in ('OCI_VAULT_NAMESPACE', 'OCI_VAULT_BUCKET', 'CAFRESOHQ_API_KEY'):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = f'http://127.0.0.1:{port}'
    for _ in range(80):
        try:
            with urllib.request.urlopen(base + '/health', timeout=2) as r:
                if r.status == 200:
                    return base, proc
        except Exception:      # noqa: BLE001
            pass
        time.sleep(0.25)
    proc.terminate()
    return None, proc


def dismiss(ws):
    for _ in range(8):
        n = H.evaluate(ws, "document.querySelectorAll('.backdrop').length")
        if not n:
            break
        H.evaluate(ws, "(() => { const b = document.querySelector('.backdrop'); if (b) b.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); return 1; })()")
        H.press_escape(ws)
        time.sleep(0.4)
    H.evaluate(ws, "(() => { const x = document.querySelector('.gs-coach button.gs-dismiss'); if (x) x.click(); return !!x; })()")


MEASURE = r"""(() => {
  const q = (s) => document.querySelector(s);
  const ps = (el, p) => getComputedStyle(el, p);
  /* Measure the mode, do not assume it: a runner in the evening (or a boss
     who left night on) starts dark, and the day layer is what this half
     reads. Remembered so the night half can put the office back. */
  if (typeof window.__litWasNight !== 'boolean') window.__litWasNight = document.body.classList.contains('night');
  document.body.classList.remove('night');
  const ints = [...document.querySelectorAll('.px-int')];
  const rooms = [...document.querySelectorAll('.px-room')];
  const day = ints.map(i => { const b = ps(i, '::before'); const r = i.getBoundingClientRect();
    return { pe: b.pointerEvents, z: b.zIndex, pos: b.position, bg: b.backgroundImage.slice(0, 30),
             w: Math.round(parseFloat(b.width)), h: Math.round(parseFloat(b.height)), iw: Math.round(r.width), ih: Math.round(r.height) }; });
  const bld = ps(q('.px-building'), '::after'), sky = ps(q('.px-sky'), '::after'), sun = ps(q('.px-sun'), '::before');
  const heights = () => ({
    floors: [...document.querySelectorAll('.px-floor')].map(f => f.getBoundingClientRect().height),
    ints: ints.map(i => i.getBoundingClientRect().height),
    lobby: q('.px-lobby') && q('.px-lobby').getBoundingClientRect().height,
    street: q('.px-street') && q('.px-street').getBoundingClientRect().height,
    scroll: q('.px-scene') && q('.px-scene').scrollHeight,
  });
  const before = heights();
  const st = document.createElement('style');
  st.textContent = '.px-int::before,.px-building::after,.px-sky::after,.px-sun::before,.px-moon::before,.px-lobby::after{display:none!important}';
  document.head.appendChild(st);
  const after = heights();
  st.remove();
  const plate = q('.px-room .px-plate'); const pr = plate.getBoundingClientRect();
  const hit = document.elementFromPoint(pr.left + 6, pr.top + pr.height / 2);
  const hitOk = !!hit && plate.contains(hit);
  const desk = q('.px-deskset .px-desk'); const dr = desk ? desk.getBoundingClientRect() : null;
  const dhit = dr ? document.elementFromPoint(dr.left + dr.width / 2, dr.top + dr.height / 2) : null;
  const deskOk = !!dhit && !!dhit.closest('.px-deskset');
  document.body.classList.add('night');
  return { count: ints.length, day, bld: { pe: bld.pointerEvents, z: bld.zIndex, bg: bld.backgroundImage.slice(0, 30) },
           sky: sky.backgroundImage.slice(0, 30), sun: sun.backgroundImage.slice(0, 30), sunZ: getComputedStyle(q('.px-sun')).zIndex,
           before, after, hitOk, hitTag: hit && hit.className, deskOk, hasDesk: !!desk };
})()"""

MEASURE_LIFE = r"""(() => {
  const q = (s) => document.querySelector(s);
  const quiet = [...document.querySelectorAll('.px-bubble.quiet')];
  const loud = [...document.querySelectorAll('.px-bubble:not(.quiet)')];
  const sun = q('.px-sun'); const moon = q('.px-moon');
  const d = new Date(); const h = d.getHours() + d.getMinutes() / 60;
  const arc = (hour, start, end) => { const f = Math.min(1, Math.max(0, (hour - start) / (end - start))); return { left: (8 + f * 84).toFixed(1) + '%', top: Math.round(112 - Math.sin(f * Math.PI) * 92) + 'px' }; };
  const want = arc(h, 6, 20), wantMoon = arc(h < 12 ? h + 24 : h, 19, 31);
  /* A fresh office has no bubble yet ("standing by" is written after a
     first run), so the quiet style is measured on a bubble placed for the
     purpose, inside a real desk set, and removed again. */
  const host = q('.px-deskset') || q('.px-int');
  const probe = document.createElement('div'); probe.className = 'px-bubble quiet'; probe.textContent = 'standing by';
  host.appendChild(probe);
  const quietOpacity = parseFloat(getComputedStyle(probe).opacity);
  const loudProbe = document.createElement('div'); loudProbe.className = 'px-bubble'; loudProbe.textContent = 'x';
  host.appendChild(loudProbe);
  const loudOpacity = parseFloat(getComputedStyle(loudProbe).opacity);
  probe.remove(); loudProbe.remove();
  const num = (v) => parseFloat(v);
  return { quiet: quiet.length, loud: loud.length, quietOpacity, loudOpacity,
           sunLeft: num(sun && sun.style.left), sunTop: num(sun && sun.style.top), sunRight: sun && sun.style.right,
           moonLeft: num(moon && moon.style.left), moonTop: num(moon && moon.style.top),
           wantSun: { left: num(want.left), top: num(want.top) }, wantMoon: { left: num(wantMoon.left), top: num(wantMoon.top) }, hour: h };
})()"""

MEASURE_NIGHT = r"""(() => {
  const q = (s) => document.querySelector(s);
  const ps = (el, p) => getComputedStyle(el, p);
  const rooms = [...document.querySelectorAll('.px-room')];
  const occ = rooms.find(r => !r.classList.contains('vacant') && !r.classList.contains('is-away') && r.querySelector('.px-int'));
  const vac = rooms.find(r => r.classList.contains('vacant') && r.querySelector('.px-int'));
  const nOcc = occ ? ps(occ.querySelector('.px-int'), '::before').backgroundImage : '';
  const nVac = vac ? ps(vac.querySelector('.px-int'), '::before').backgroundImage : '';
  const lobby = q('.px-lobby') ? ps(q('.px-lobby'), '::after') : null;
  const stars = q('.px-stars') ? getComputedStyle(q('.px-stars')) : null;
  const moon = ps(q('.px-moon'), '::before');
  const out = { night: document.body.classList.contains('night'),
           nOccRadial: /radial-gradient/.test(nOcc), nVacRadial: /radial-gradient/.test(nVac), hasVacant: !!vac, hasOcc: !!occ,
           lobbyPe: lobby && lobby.pointerEvents, lobbyRadial: !!lobby && /radial-gradient/.test(lobby.backgroundImage),
           lobbyContent: lobby && lobby.content,
           starsAnim: stars && stars.animationName, moonRadial: /radial-gradient/.test(moon.backgroundImage),
           reduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
           noPref: matchMedia('(prefers-reduced-motion: no-preference)').matches };
  document.body.classList.toggle('night', !!window.__litWasNight);
  return out;
})()"""


def source_pins():
    css = (ROOT / 'styles.css').read_text(encoding='utf-8')
    sec = css[css.index('#431 · the office, lit'):]
    check('the section exists in styles.css', '#431 · the office, lit' in css)
    rules = re.findall(r"([^{}]+)\{([^{}]*content:\s*''[^{}]*)\}", sec)
    check('every overlay in the section takes no clicks (pointer-events: none)',
          rules and all('pointer-events: none' in body for _, body in rules), [sel.strip()[:40] for sel, body in rules if 'pointer-events: none' not in body])
    gate = re.search(r"@media \(prefers-reduced-motion: no-preference\) \{[^}]*px-twinkle[^}]*\}\s*\}", sec)
    check('the one new animation is gated behind prefers-reduced-motion: no-preference', bool(gate))
    check('no other animation was added to the scene by this section', sec[:sec.index('#432 · the office, alive')].count('animation:') == 1 if '#432 · the office, alive' in sec else sec.count('animation:') == 1)
    # ── #432: alive ─────────────────────────────────────────────────────
    alive = css[css.index('#432 · the office, alive'):]
    check('the thinking glow is gated behind prefers-reduced-motion: no-preference',
          re.search(r"@media \(prefers-reduced-motion: no-preference\) \{[^}]*px-think[^}]*\}\s*\}", alive) and alive.count('animation:') == 2)
    jsx = (ROOT / 'ui' / 'office.jsx').read_text(encoding='utf-8')
    check('a busy coworker lights the monitor while thinking, a tool run keeps the flicker',
          "a.status === 'busy') && !away && <span className={`px-glow${(screen || liveTool) ? '' : ' thinking'}`}" in jsx)
    check('the idle bubble is marked quiet from the coworker\'s status, text untouched',
          "className={`px-bubble${(a.status || 'idle') === 'idle' ? ' quiet' : ''}`}>{a.task}" in jsx)
    check('the clock is a tick a minute, not an animation loop', 'setInterval(() => { const d = new Date(); setClockHour' in jsx and '60000' in jsx)


def main():
    print('the office is lit, and nothing moved')
    source_pins()
    if not (ROOT / 'dist-ui' / 'manifest.json').exists():
        check('the HQ UI is built (dist-ui/manifest.json)', False, 'run `npm run build` first')
        return finish()
    chrome = H.find_chrome()
    if chrome is None:
        print('  SKIPPED the browser half — no headless browser on this machine.')
        return finish()
    state_dir = tempfile.mkdtemp(prefix='cafresohq-lit-state-')
    base, server = boot_server(state_dir)
    if not check('serve.py boots on a scratch port', base is not None):
        return finish()
    profile = tempfile.mkdtemp(prefix='cafresohq-cdp-lit-')
    proc = subprocess.Popen(
        [str(chrome), '--headless=new', '--remote-debugging-port=0', f'--user-data-dir={profile}', '--no-sandbox',
         '--disable-gpu', '--hide-scrollbars', '--mute-audio', '--no-first-run', '--no-default-browser-check',
         '--disable-extensions', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', 'about:blank'],
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
        if not check('the browser announced a DevTools endpoint', bool(endpoint)):
            return finish()
        host = re.match(r'ws://([^/]+)/', endpoint).group(1)
        with urllib.request.urlopen(f'http://{host}/json/list', timeout=15) as fh:
            targets = json.load(fh)
        page = next(t for t in targets if t['type'] == 'page')
        ws = H.WS(page['webSocketDebuggerUrl'])
        ws.call('Page.enable')
        ws.call('Runtime.enable')
        ws.call('Emulation.setDeviceMetricsOverride', {'width': 1280, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
        ws.call('Page.navigate', {'url': base + '/hq.html'})
        H.wait_for(ws, "!!document.querySelector('button[title^=\"Office\"]')", 45, 'the rail to draw its Office item')
        H.wait_for(ws, "!document.getElementById('cafreso-boot')", 20, 'the boot splash to clear')
        dismiss(ws)
        H.evaluate(ws, "(() => { const b = document.querySelector('button[title^=\"Office\"]'); b.click(); return !!b; })()")
        H.wait_for(ws, "document.querySelectorAll('.px-int').length >= 2", 20, 'the pixel scene to draw its rooms')
        time.sleep(0.8)
        H.evaluate(ws, "(() => { window.__litWasNight = document.body.classList.contains('night'); document.body.classList.remove('night'); return 1; })()")
        time.sleep(0.5)
        m = H.evaluate(ws, MEASURE)
        life = H.evaluate(ws, MEASURE_LIFE)
        time.sleep(0.5)
        m.update(H.evaluate(ws, MEASURE_NIGHT))
        check('the scene drew rooms to measure', m['count'] >= 2, m['count'])
        check('every room carries the daylight layer: absolute, z1, no clicks, a gradient stack',
              all(d['pe'] == 'none' and d['z'] == '1' and d['pos'] == 'absolute' and d['bg'].startswith('linear-gradient') for d in m['day']), m['day'][:2])
        check('the layer covers exactly the room (inset 0), never spilling into layout',
              all(abs(d['w'] - d['iw']) <= 1 and abs(d['h'] - d['ih']) <= 1 for d in m['day']), m['day'][:2])
        check("the building's edge shade takes no clicks and sits above the floors (z5)", m['bld']['pe'] == 'none' and m['bld']['z'] == '5' and m['bld']['bg'].startswith('linear-gradient'), m['bld'])
        check('the horizon haze and the sun glow are there by day', m['sky'].startswith('linear-gradient') and m['sun'].startswith('radial-gradient') and m['sunZ'] == '1', (m['sky'], m['sun'], m['sunZ']))
        check('NOTHING MOVED: floors, interiors, lobby, street and scroll height are identical with the whole layer switched off',
              m['before'] == m['after'], (m['before'], m['after']))
        check('a desk sign is still the thing under the pointer, through the edge shade', m['hitOk'], m['hitTag'])
        check('a desk is still the thing under the pointer, through the daylight layer', (not m['hasDesk']) or m['deskOk'], m['deskOk'])
        check('by night an occupied room gets a lamp pool (radial), a vacant unit gets none',
              m['hasOcc'] and m['nOccRadial'] and ((not m['hasVacant']) or not m['nVacRadial']), (m['hasOcc'], m['nOccRadial'], m['hasVacant'], m['nVacRadial']))
        check('by night the lobby spills light and takes no clicks', m['lobbyPe'] == 'none' and m['lobbyRadial'], (m['lobbyPe'], m['lobbyRadial'], m['lobbyContent'], m['night']))
        check('the moon has its glow', m['moonRadial'])
        # Headless Chrome answers neither `reduce` nor `no-preference` on some
        # builds; only a browser that says motion is welcome must twinkle.
        # ── #432: alive ───────────────────────────────────────────────────
        check('an idle "standing by" bubble is quiet — three-fifths the presence of a working one',
              0.4 < life['quietOpacity'] < 0.8 and life['loudOpacity'] == 1, life)
        check('the sun sits where the local hour puts it on the arc (inline left/top, right released)',
              abs(life['sunLeft'] - life['wantSun']['left']) < 0.2 and abs(life['sunTop'] - life['wantSun']['top']) < 1.5 and life['sunRight'] == 'auto', life)
        check('the moon keeps its own hours on the same arc',
              abs(life['moonLeft'] - life['wantMoon']['left']) < 0.2 and abs(life['moonTop'] - life['wantMoon']['top']) < 1.5, life)
        check('the stars twinkle only when motion is welcome',
              (m['starsAnim'] == 'px-twinkle') if m['noPref'] else (m['starsAnim'] == 'none'), (m['reduced'], m['noPref'], m['starsAnim']))
    finally:
        try:
            if ws:
                ws.close()
        except Exception:      # noqa: BLE001
            pass
        proc.kill()
        server.terminate()
    return finish()


def finish():
    print()
    if FAILS:
        print(f'lit office: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('lit office: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
