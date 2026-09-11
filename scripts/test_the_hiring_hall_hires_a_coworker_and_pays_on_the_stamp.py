#!/usr/bin/env python3
"""The boss's side of the hiring hall, driven end to end in a real browser:
read a résumé, hire for one job, fund the escrow, read the delivery, stamp
it, pay. The shell that holds Internet Identity is stood in for by
scripts/harness_fake_shell.html — same origin, same postMessage protocol,
an in-memory hall — so the test can read back exactly what the office asked
the shell to sign, and nothing real is signed.

Boots serve.py on a scratch port (it serves hq.html, the built bundle AND
the harness page, so the iframe is same-origin and its document is
reachable), then headless Chrome through the phone harness's own CDP client.

Measured:
  * the Network rail item opens the HIRING HALL, and with a shell present
    the three tabs are there;
  * Mira's card carries her name, role, brain, asking price "0.25 ICP",
    "AT THEIR DESK", and the résumé line built from the real counters:
    "12 jobs done · 5 bosses · 3 re-hires · ★ 4.8 (10) · 1 snag";
  * "Hire for a job" opens the form; an offer below the asking price is
    named and blocks the button; a good one enables it;
  * "Post and fund" asks the shell to post exactly (listing 7, kind, the
    deadline, 25000000 base units of ICP) and then to fund that job — the
    approval the real shell would show carries that price — and the office
    lands on Your jobs with the job WAITING FOR THE COWORKER;
  * when the (simulated) coworker delivers, the card reads DELIVERED — YOUR
    CALL with their one-line summary, "Read the whole thing" shows the body,
    a ★★★★ rating and "Accept and pay" send accept(rating 4) — the hall
    records the payment of exactly the price, the pill reads ACCEPTED · PAID;
  * declining the signature leaves the job WRITTEN DOWN — NOT FUNDED YET
    with a Fund it button, which funds it;
  * "Take it back" on a funded job asks for the refund;
  * Offer a coworker shows this office's real worker key (the one serve.py's
    /marketplace/worker/status reports), OFF DUTY, and will not list with
    no coworker chosen;
  * with no shell at all the room says the hall is behind the sign-in; with
    a shell whose hall is not deployed it says the hall is not open yet.

Run: python3 scripts/test_the_hiring_hall_hires_a_coworker_and_pays_on_the_stamp.py
"""
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
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
    print(('  ok    ' if cond else '  FAIL  ') + name + ((' — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ── serve.py on a scratch port ──────────────────────────────────────────────
def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def boot_server(state_dir):
    port = free_port()
    env = dict(os.environ, PORT=str(port), CAFRESOHQ_ALLOWED_DIRS=state_dir, CAFRESOHQ_HQ_STATE_DIR=state_dir,
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


# ── JS snippets (the iframe's document is D) ────────────────────────────────
D = "const D = document.getElementById('hq').contentDocument;"
SET = """const set = (el, v) => {
  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
  el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
};"""
BTN = "const btn = (t, root) => [...(root || D.querySelector('.view-market')).querySelectorAll('button')].find(b => b.textContent.trim() === t);"


def ev(ws, expr, timeout=30):
    return H.evaluate(ws, f'(() => {{ {D} {SET} {BTN} {expr} }})()', timeout=timeout)


def wait(ws, expr, seconds, what):
    return H.wait_for(ws, f'(() => {{ try {{ {D} {SET} {BTN} return !!({expr}); }} catch (e) {{ return false; }} }})()', seconds, what)


def dismiss(ws, doc_expr='document.getElementById("hq").contentDocument'):
    """Clear a fresh office's first-run dialogs and the getting-started coach."""
    for _ in range(8):
        n = H.evaluate(ws, f"{doc_expr}.querySelectorAll('.backdrop').length")
        if not n:
            break
        H.evaluate(ws, f"""(() => {{ const d = {doc_expr}; const b = d.querySelector('.backdrop'); if (b) b.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Escape', bubbles: true }})); return 1; }})()""")
        H.press_escape(ws)
        time.sleep(0.4)
    H.evaluate(ws, f"""(() => {{ const d = {doc_expr}; const x = d.querySelector('.gs-coach button.gs-dismiss'); if (x) x.click(); return !!x; }})()""")


def open_hall(ws, doc_expr='document.getElementById("hq").contentDocument'):
    H.wait_for(ws, f"!!{doc_expr}.querySelector('button[title^=\"Network\"]')", 45, 'the rail to draw its Network item')
    H.wait_for(ws, f"!{doc_expr}.getElementById('cafreso-boot')", 20, 'the boot splash to clear')
    dismiss(ws, doc_expr)
    H.evaluate(ws, f"""(() => {{ const d = {doc_expr}; const b = d.querySelector('button[title^="Network"]'); b.click(); return !!b; }})()""")
    H.wait_for(ws, f"!!{doc_expr}.querySelector('.view-market')", 20, 'the hiring hall to render')


def main():
    print('The hiring hall hires a coworker and pays on the stamp')
    if not (ROOT / 'dist-ui' / 'manifest.json').exists():
        print('  FAIL  the HQ UI is built  — dist-ui/manifest.json is missing; run `npm run build` first')
        print('\n1 FAILED — the HQ UI is built')
        return 1
    chrome = H.find_chrome()
    if chrome is None:
        print('  SKIPPED — no headless browser on this machine.')
        print('\nnothing measured')
        return 0
    print(f'  using  {chrome}')

    state_dir = tempfile.mkdtemp(prefix='cafresohq-hall-state-')
    base, server = boot_server(state_dir)
    check('serve.py boots on a scratch port', base is not None)
    if base is None:
        return 1
    with urllib.request.urlopen(base + '/marketplace/worker/status', timeout=10) as r:
        worker_principal = json.loads(r.read())['principal']
    check("serve.py's worker door names this office's key", bool(worker_principal))

    profile = tempfile.mkdtemp(prefix='cafresohq-cdp-hall-')
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
            check('the browser announced a DevTools endpoint', False)
            return 1
        host = re.match(r'ws://([^/]+)/', endpoint).group(1)
        with urllib.request.urlopen(f'http://{host}/json/list', timeout=15) as fh:
            targets = json.load(fh)
        page = next(t for t in targets if t['type'] == 'page')
        ws = H.WS(page['webSocketDebuggerUrl'])
        ws.call('Page.enable')
        ws.call('Runtime.enable')
        ws.call('Emulation.setDeviceMetricsOverride', {'width': 1280, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})

        # ── with a shell: the whole boss-side flow ────────────────────────
        ws.call('Page.navigate', {'url': base + '/scripts/harness_fake_shell.html'})
        H.wait_for(ws, "!!window.__fakeShell && !!document.getElementById('hq').contentDocument", 20, 'the fake shell to mount')
        open_hall(ws)
        wait(ws, "D.querySelectorAll('[data-market-tab]').length === 3", 20, 'the three tabs (the shell answered info)')
        title = ev(ws, "return D.querySelector('.view-market .section-title').textContent;")
        check('the room is signed HIRING HALL', 'HIRING HALL' in (title or ''), title)
        check('three tabs: hire, your jobs, offer',
              ev(ws, "return [...D.querySelectorAll('[data-market-tab]')].map(b => b.textContent.trim());") == ['Hire from the network', 'Your jobs', 'Offer a coworker'])

        wait(ws, "D.querySelector('[data-listing=\"7\"]')", 20, "Mira's card")
        card = ev(ws, """const c = D.querySelector('[data-listing="7"]');
          return { name: c.querySelector('.name').textContent, role: c.querySelector('.role').textContent,
                   pill: c.querySelector('.status-pill').textContent.trim(),
                   stats: [...c.querySelectorAll('.team-stats .val')].map(v => v.textContent),
                   notes: [...c.querySelectorAll('.market-note')].map(n => n.textContent) };""")
        check("Mira's card: name, role, at her desk", card['name'] == 'Mira' and card['role'] == 'Research Coworker' and card['pill'] == 'AT THEIR DESK', card)
        check('the card states brain, price "0.25 ICP", and what she takes', card['stats'] == ['Claude Sonnet 4', '0.25 ICP', 'brief, research'], card['stats'])
        check('the résumé line is built from the real counters',
              '12 jobs done · 5 bosses · 3 re-hires · ★ 4.8 (10) · 1 snag' in card['notes'], card['notes'])

        ev(ws, "btn('Hire for a job', D.querySelector('[data-listing=\"7\"]')).click();")
        wait(ws, "D.querySelector('[data-hire-form]')", 10, 'the hire form')
        form = ev(ws, """const f = D.querySelector('[data-hire-form]');
          return { price: f.querySelector('input[inputmode="decimal"]').value, disabled: btn('Post and fund', f).classList.contains('is-disabled') || btn('Post and fund', f).disabled };""")
        check('the form opens with the asking price filled in and the button dark until the brief is written', form['price'] == '0.25' and form['disabled'], form)
        ev(ws, """const f = D.querySelector('[data-hire-form]');
          set(f.querySelector('input[maxlength="200"]'), 'Competitor brief on three hardware wallets');
          set(f.querySelector('textarea'), 'Compare Ledger, Trezor and Coldcard on price, open-source firmware and recovery. Cite sources.');
          set(f.querySelector('input[inputmode="decimal"]'), '0.1');""")
        time.sleep(0.3)
        low = ev(ws, """const f = D.querySelector('[data-hire-form]');
          return { warn: [...f.querySelectorAll('.market-note')].some(n => /Below their asking price of 0.25 ICP/.test(n.textContent)), disabled: btn('Post and fund', f).disabled || btn('Post and fund', f).classList.contains('is-disabled') };""")
        check('an offer below the asking price is named and blocks the button', low['warn'] and low['disabled'], low)
        ev(ws, "set(D.querySelector('[data-hire-form] input[inputmode=\"decimal\"]'), '0.25');")
        time.sleep(0.3)
        check('at the asking price the button lights up', not ev(ws, "const b = btn('Post and fund', D.querySelector('[data-hire-form]')); return b.disabled || b.classList.contains('is-disabled');"))
        ev(ws, "btn('Post and fund', D.querySelector('[data-hire-form]')).click();")
        H.wait_for(ws, "window.__fakeShell.log.some(l => l.type === 'chain:market:fund')", 20, 'the fund request to reach the shell')
        post = H.evaluate(ws, "window.__fakeShell.log.find(l => l.type === 'chain:market:post').data")
        check('the post names listing 7, the kind, the deadline and the price in base units',
              post['listing'] == '7' and post['kind'] == 'brief' and post['deadlineSecs'] == 86400 and post['price'] == '25000000' and post['token'] == 'ICP', post)
        check('the brief travelled whole', 'Coldcard' in post['brief'])
        appr = H.evaluate(ws, "window.__fakeShell.approvals[0]")
        check('the approval the shell would show carries exactly that price', appr and appr['what'] == 'fund' and appr['price'] == '25000000' and appr['id'] == '1', appr)
        wait(ws, "D.querySelector('[data-job=\"1\"][data-status=\"funded\"]')", 20, 'Your jobs to show the funded job')
        pill = ev(ws, "return D.querySelector('[data-job=\"1\"] .status-pill').textContent.trim();")
        check('the office lands on Your jobs: WAITING FOR THE COWORKER', pill == 'WAITING FOR THE COWORKER', pill)
        check('the job names Mira and the price', ev(ws, "return D.querySelector('[data-job=\"1\"] .market-note').textContent;").startswith('Mira · 0.25 ICP'))

        # the coworker delivers (simulated), the boss reads and stamps
        H.evaluate(ws, "window.__fakeShell.deliver('1', 'Ledger wins on price, Coldcard on openness.\\n\\nLedger Nano S Plus: $79 …'); 1")
        ev(ws, "btn('Hire from the network').click();")
        time.sleep(0.2)
        ev(ws, "btn('Your jobs').click();")
        wait(ws, "D.querySelector('[data-job=\"1\"][data-status=\"delivered\"]')", 20, 'the delivered job')
        dl = ev(ws, """const c = D.querySelector('[data-job="1"]');
          return { pill: c.querySelector('.status-pill').textContent.trim(), notes: [...c.querySelectorAll('.market-note')].map(n => n.textContent), hasPre: !!c.querySelector('pre') };""")
        check('DELIVERED — YOUR CALL, with their summary and the body folded', dl['pill'] == 'DELIVERED — YOUR CALL' and any('Ledger wins on price' in n for n in dl['notes']) and not dl['hasPre'], dl)
        ev(ws, "btn('Read the whole thing', D.querySelector('[data-job=\"1\"]')).click();")
        wait(ws, "D.querySelector('[data-job=\"1\"] pre')", 5, 'the body')
        check('"Read the whole thing" shows the deliverable', 'Nano S Plus' in (ev(ws, "return D.querySelector('[data-job=\"1\"] pre').textContent;") or ''))
        ev(ws, "set(D.querySelector('[data-job=\"1\"] select'), '4'); btn('Accept and pay', D.querySelector('[data-job=\"1\"]')).click();")
        H.wait_for(ws, "window.__fakeShell.log.some(l => l.type === 'chain:market:accept')", 20, 'the accept to reach the shell')
        acc = H.evaluate(ws, "window.__fakeShell.log.find(l => l.type === 'chain:market:accept').data")
        check('Accept and pay sends the stamp with the ★★★★ rating', acc['id'] == '1' and acc['rating'] == 4, acc)
        paid = H.evaluate(ws, "window.__fakeShell.paid")
        check('the hall paid exactly the price, once', paid == [{'id': '1', 'amount': '25000000', 'rating': 4}], paid)
        wait(ws, "D.querySelector('[data-job=\"1\"][data-status=\"accepted\"]')", 20, 'the paid job')
        check('the pill reads ACCEPTED · PAID', ev(ws, "return D.querySelector('[data-job=\"1\"] .status-pill').textContent.trim();") == 'ACCEPTED · PAID')

        # declining the signature
        H.evaluate(ws, "window.__fakeShell.declineFunding = true; 1")
        ev(ws, "btn('Hire from the network').click();")
        wait(ws, "D.querySelector('[data-listing=\"7\"]')", 10, 'the card again')
        ev(ws, "btn('Hire for a job', D.querySelector('[data-listing=\"7\"]')).click();")
        wait(ws, "D.querySelector('[data-hire-form]')", 10, 'the form again')
        ev(ws, """const f = D.querySelector('[data-hire-form]');
          set(f.querySelector('input[maxlength="200"]'), 'Second job'); set(f.querySelector('textarea'), 'A second brief.');
          btn('Post and fund', f).click();""")
        wait(ws, "D.querySelector('[data-job=\"2\"][data-status=\"posted\"]')", 20, 'the unfunded job')
        check('a declined signature leaves the job WRITTEN DOWN — NOT FUNDED YET with a Fund it button',
              ev(ws, "const c = D.querySelector('[data-job=\"2\"]'); return c.querySelector('.status-pill').textContent.trim() === 'WRITTEN DOWN — NOT FUNDED YET' && !!btn('Fund it', c);"))
        H.evaluate(ws, "window.__fakeShell.declineFunding = false; 1")
        ev(ws, "btn('Fund it', D.querySelector('[data-job=\"2\"]')).click();")
        wait(ws, "D.querySelector('[data-job=\"2\"][data-status=\"funded\"]')", 20, 'job 2 funded')
        check('Fund it funds it later', True)
        ev(ws, "btn('Take it back (refund)', D.querySelector('[data-job=\"2\"]')).click();")
        H.wait_for(ws, "window.__fakeShell.log.some(l => l.type === 'chain:market:cancel' && l.data.id === '2')", 20, 'the refund request')
        wait(ws, "D.querySelector('[data-job=\"2\"][data-status=\"refunded\"]')", 20, 'job 2 refunded')
        check('Take it back asks the hall for the refund', True)

        # offer a coworker
        ev(ws, "btn('Offer a coworker').click();")
        wait(ws, "D.querySelector('[data-worker-card] code')", 20, 'the worker card')
        wc = ev(ws, """const c = D.querySelector('[data-worker-card]');
          return { key: c.querySelector('code').getAttribute('title'), pill: c.querySelector('.status-pill').textContent.trim() };""")
        check("Offer shows this office's real worker key, OFF DUTY", wc['key'] == worker_principal and wc['pill'] == 'OFF DUTY', (wc, worker_principal))
        check('with no coworker chosen the listing button stays dark',
              ev(ws, "const b = btn('List them and put this office on duty'); return b.disabled || b.classList.contains('is-disabled');"))

        # ── a shell whose hall is not deployed ────────────────────────────
        ws.call('Page.navigate', {'url': base + '/scripts/harness_fake_shell.html'})
        H.wait_for(ws, "!!window.__fakeShell", 20, 'the fake shell again')
        H.evaluate(ws, "window.__fakeShell.info.configured = false; window.__fakeShell.info.canister = ''; 1")
        open_hall(ws)
        wait(ws, "D.querySelector('.view-market .empty-title')", 20, 'the not-open state')
        check('a shell whose hall is not deployed: "The hall is not open yet"',
              ev(ws, "return D.querySelector('.view-market .empty-title').textContent;") == 'The hall is not open yet')

        # ── no shell at all ───────────────────────────────────────────────
        ws.call('Page.navigate', {'url': base + '/hq.html'})
        open_hall(ws, 'document')
        H.wait_for(ws, "!!document.querySelector('.view-market .empty-title')", 20, 'the standalone state')
        check('standalone: "The hall is behind the Cafreso sign-in"',
              H.evaluate(ws, "document.querySelector('.view-market .empty-title').textContent") == 'The hall is behind the Cafreso sign-in')
    except Exception as exc:      # noqa: BLE001
        check('the flow ran to the end', False, f'{type(exc).__name__}: {exc}')
    finally:
        if ws:
            ws.close()
        proc.kill()
        proc.wait(timeout=10)
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(profile, ignore_errors=True)
        shutil.rmtree(state_dir, ignore_errors=True)

    print()
    if FAILS:
        print(f'hiring hall UI: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('hiring hall UI: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
