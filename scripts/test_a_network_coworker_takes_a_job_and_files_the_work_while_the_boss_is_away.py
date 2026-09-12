#!/usr/bin/env python3
"""A coworker hired from the network has to take a job, do it and file the
result with nobody watching — the operator's browser closed, no Internet
Identity anywhere in the container. `market_worker.py` is that loop, on the
key `ic_agent.py` keeps for it.

Driven here against a STUB hiring hall: an HTTP replica served from a thread
that speaks the real wire (CBOR envelopes, Candid arguments, certificate
replies) and — this is the point — verifies every signed envelope under its
own sender's public key and derives the caller principal from it, exactly
as the IC would. So "the hall let this worker claim" means the worker's
signature checked out and its principal matched the linked one, not that a
flag was set.

Measured:
  * an UNLINKED key is told so and takes nothing;
  * a linked key heartbeats, polls, claims the oldest funded job, reports
    "started", runs the brief, and delivers the text with a sha256 that
    matches what the hall stored; the summary is the first line; every call
    was signed by the worker's principal, none anonymous;
  * a brain that throws → the hall gets one honest failJob sentence, the job
    goes back on the board with one attempt spent, and the worker's own
    counters say so;
  * a brain that returns nothing → the same, with the reason "returned nothing";
  * a deliverable longer than the hall accepts is cut with a marker, and the
    sha256 is of what was actually delivered;
  * two open jobs → the older one first;
  * the privacy boundary in `default_run_task`: a network job runs with NO
    tools and no working directory; `allowWeb` widens it to web only;
  * serve.py's doors: /marketplace/worker/status names a real principal and
    the 0600 key file, config merges and clamps, start/stop flip `enabled`,
    and the prefix is on the key-protected list.

No replica, no model, no network. Run:
    python3 scripts/test_a_network_coworker_takes_a_job_and_files_the_work_while_the_boss_is_away.py
"""
import hashlib
import http.server
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ic_agent as ic          # noqa: E402
import market_worker as mw     # noqa: E402

FAILS = []
CANISTER = 'vhw7q-lqaaa-aaaab-agthq-cai'   # any well-formed canister id; the stub answers for it
LEDGER = ic.Principal.from_text('ryjl3-tyaaa-aaaaa-aaaba-cai')


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + ((' — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ── the stub hiring hall ────────────────────────────────────────────────────
class Hall(http.server.BaseHTTPRequestHandler):
    """A replica + canister in one. `state` is the canister's memory."""
    state = {'listing': {'id': 7, 'worker': None, 'active': True}, 'jobs': {}, 'calls': []}

    def log_message(self, *a):
        pass

    @classmethod
    def reset(cls):
        cls.state = {'listing': {'id': 7, 'worker': None, 'active': True}, 'jobs': {}, 'calls': []}

    @classmethod
    def add_job(cls, jid, brief, created_at, listing=7):
        cls.state['jobs'][jid] = {
            'id': jid, 'title': f'job {jid}', 'brief': brief, 'kind': 'brief', 'tags': ['brief'],
            'ledger': LEDGER, 'price': 100_000, 'deadlineSecs': 900, 'listing': listing,
            'createdAt': created_at, 'status': 'funded', 'worker': None, 'attempts': 0,
            'summary': '', 'body': '', 'sha': '', 'progress': '', 'note': '',
        }

    def _caller(self, env):
        if 'sender_sig' not in env:
            return ic.Principal.anonymous(), True
        pub = bytes(env['sender_pubkey'])
        rid = ic.request_id(env['content'])
        ok = ic.ed25519_verify(pub[-32:], b'\x0aic-request' + rid, bytes(env['sender_sig']))
        return ic.Principal.self_authenticating(pub), ok

    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        env = ic.cbor_decode(self.rfile.read(n))
        content = env['content']
        caller, sig_ok = self._caller(env)
        if content['request_type'] == 'read_state':
            return self._send(404, b'')      # every call here is answered synchronously
        method = content['method_name']
        args = ic.candid_decode(content['arg']) if content['arg'] else []
        Hall.state['calls'].append({'method': method, 'caller': caller.to_text(), 'sigOk': sig_ok, 'args': args})
        if not sig_ok:
            return self._send(400, b'bad signature')
        reply = self.dispatch(method, args, caller)
        if content['request_type'] == 'query':
            return self._send(200, ic.cbor_encode({'status': 'replied', 'reply': {'arg': reply}}))
        rid = ic.request_id(content)
        tree = [2, b'request_status', [2, rid, [1, [2, b'reply', [3, reply]], [2, b'status', [3, b'replied']]]]]
        cert = ic.cbor_encode({'tree': tree, 'signature': b'\x00' * 48})
        return self._send(200, ic.cbor_encode({'status': 'replied', 'certificate': cert}))

    def dispatch(self, method, args, caller):
        st = Hall.state
        linked = st['listing']['worker'] == caller.to_text()
        R = mw.RESULT
        if method == 'workerHeartbeat':
            return ic.candid_encode([('bool', linked)])
        if method == 'workerPoll':
            offers = [] if not linked else [
                {k: j[k] for k in ('id', 'title', 'brief', 'kind', 'tags', 'ledger', 'price', 'deadlineSecs', 'listing', 'createdAt')}
                for j in st['jobs'].values() if j['status'] == 'funded']
            return ic.candid_encode([(('vec', mw.JOB_OFFER), offers)])
        if method == 'claimJob':
            j = st['jobs'].get(args[0])
            if not linked:
                return ic.candid_encode([(R, {'err': 'this key is not linked to a listing'})])
            if not j or j['status'] != 'funded':
                return ic.candid_encode([(R, {'err': 'this job is not open'})])
            j['status'], j['worker'] = 'claimed', caller.to_text()
            return ic.candid_encode([(R, {'ok': j['id']})])
        if method in ('progressJob', 'deliverJob', 'failJob'):
            j = st['jobs'].get(args[0])
            if not j or j['status'] != 'claimed' or j['worker'] != caller.to_text():
                return ic.candid_encode([(R, {'err': 'not your claim'})])
            if method == 'progressJob':
                j['progress'] = args[1]
            elif method == 'deliverJob':
                if len(args[2].encode('utf-8')) > 65_536:
                    return ic.candid_encode([(R, {'err': 'deliverable is over 65536 characters'})])
                j.update(status='delivered', summary=args[1], body=args[2], sha=args[3])
            else:
                j.update(status='funded', worker=None, attempts=j['attempts'] + 1, note=args[1])
            return ic.candid_encode([(R, {'ok': j['id']})])
        return ic.candid_encode([(R, {'err': f'no such method {method}'})])

    def _send(self, code, body):
        self.send_response(code)
        self.send_header('Content-Type', 'application/cbor')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def calls(method):
    return [c for c in Hall.state['calls'] if c['method'] == method]


# ── the loop against the stub ───────────────────────────────────────────────
def test_loop(host):
    print('the loop — against a stub hall that checks every signature')
    outputs = {'mode': 'ok'}

    def brain(brief, cfg, offer):
        if outputs['mode'] == 'raise':
            raise RuntimeError('the brain is out of coffee')
        if outputs['mode'] == 'empty':
            return ''
        if outputs['mode'] == 'huge':
            return 'x' * 70_000
        return f'Haiku for the boss\n\nescrow holds the coin\nthe worker types in the dark\nmorning brings the stamp\n\n(from: {brief[:20]})'

    with tempfile.TemporaryDirectory() as d:
        w = mw.MarketWorker(d, run_task=brain)
        w.configure({'canister': CANISTER, 'host': host, 'driver': 'stub', 'pollSecs': 5})
        check('configure does not start the loop while enabled is false', not w.status()['running'])
        agent = w._agent()
        Hall.reset()
        # 1. unlinked
        n = w.tick(agent, CANISTER)
        check('an unlinked key takes nothing', n == 0 and calls('workerPoll') == [] and calls('claimJob') == [])
        check('…and is told to get linked', 'link' in w.status()['lastError'])
        check('the heartbeat was signed by the worker principal, not anonymous',
              calls('workerHeartbeat') and calls('workerHeartbeat')[0]['caller'] == w.principal() and calls('workerHeartbeat')[0]['sigOk'])
        # 2. linked, one job
        Hall.state['listing']['worker'] = w.principal()
        Hall.add_job(1, 'Write a haiku about escrow', created_at=1000)
        w.state['lastHeartbeat'] = 0
        n = w.tick(agent, CANISTER)
        j = Hall.state['jobs'][1]
        check('a linked key takes the job', n == 1 and j['status'] == 'delivered', (n, j['status']))
        check('it reported "started" before working', j['progress'] == 'started')
        expected = brain('Write a haiku about escrow', {}, {})
        check('the delivered body is the brain\'s text, verbatim', j['body'] == expected)
        check('the sha256 the hall stored is the sha256 of the body it stored',
              j['sha'] == hashlib.sha256(j['body'].encode('utf-8')).hexdigest())
        check('the summary is the first line', j['summary'] == 'Haiku for the boss')
        check('the worker\'s own counter says one job done', w.status()['jobsDone'] == 1 and w.status()['current'] is None)
        signed = [c for c in Hall.state['calls'] if c['method'] in ('claimJob', 'progressJob', 'deliverJob')]
        check('claim, progress and deliver were all signed by the worker principal',
              len(signed) == 3 and all(c['caller'] == w.principal() and c['sigOk'] for c in signed))
        check('the claim carried the job id as a Candid nat', calls('claimJob')[-1]['args'] == [1])
        # 3. a brain that throws
        outputs['mode'] = 'raise'
        Hall.add_job(2, 'Explain escrow', created_at=2000)
        n = w.tick(agent, CANISTER)
        j2 = Hall.state['jobs'][2]
        check('a brain that throws → failJob, job back on the board, one attempt spent',
              n == 0 and j2['status'] == 'funded' and j2['attempts'] == 1 and j2['worker'] is None, (n, j2['status'], j2['attempts']))
        check('the failure reason is one honest sentence naming the exception', 'out of coffee' in j2['note'] and 'RuntimeError' in j2['note'])
        check('the worker counts the snag', w.status()['jobsFailed'] == 1 and 'out of coffee' in w.status()['lastError'])
        # 4. a brain that returns nothing
        outputs['mode'] = 'empty'
        w.tick(agent, CANISTER)
        check('a brain that returns nothing → failJob "returned nothing"', 'returned nothing' in Hall.state['jobs'][2]['note'])
        # 5. oversize
        outputs['mode'] = 'huge'
        Hall.state['jobs'][2]['status'] = 'cancelled'
        Hall.add_job(3, 'Write a lot', created_at=3000)
        w.tick(agent, CANISTER)
        j3 = Hall.state['jobs'][3]
        check('an oversize deliverable is cut to the hall\'s cap with a marker',
              j3['status'] == 'delivered' and len(j3['body'].encode('utf-8')) <= 65_536 and 'cut here' in j3['body'])
        check('…and the sha256 is of what was actually delivered', j3['sha'] == hashlib.sha256(j3['body'].encode('utf-8')).hexdigest())
        # 6. oldest first
        outputs['mode'] = 'ok'
        Hall.add_job(5, 'newer', created_at=5000)
        Hall.add_job(4, 'older', created_at=4000)
        w.tick(agent, CANISTER)
        check('with two open jobs the older one is taken first',
              Hall.state['jobs'][4]['status'] == 'delivered' and Hall.state['jobs'][5]['status'] == 'funded')
        # the key file
        mode = stat.S_IMODE(os.stat(w.key_path).st_mode)
        check('the worker key file is 0600 under hq-state/market', mode == 0o600 and w.key_path.endswith('market/worker-key.json'))
        check('the same directory reloads the same principal',
              mw.MarketWorker(d, run_task=brain).principal() == w.principal())
        check('config persisted to worker.json', json.loads(Path(w.cfg_path).read_text())['canister'] == CANISTER)


# ── the privacy boundary in default_run_task ────────────────────────────────
def test_privacy():
    print('the privacy boundary — a network job runs with no tools and no directory')
    import drivers
    import drivers.base as base
    seen = {}

    class FakeDriver:
        MANIFEST = {'id': 'fake'}

    real_get, real_run = drivers.get, base.run_task_text
    try:
        drivers.get = lambda did: FakeDriver() if did == 'fake' else None
        base.run_task_text = lambda drv, task: (seen.setdefault('task', task), ('ok', {}))[1]   # the contract returns (text, usage)
        out = mw.default_run_task('Do the thing', {'driver': 'fake', 'model': 'm', 'system': 'Be brief.'}, {'title': 'T', 'kind': 'brief'})
        t = seen['task']
        check('the brain was called and its text returned', out == 'ok')
        check('tools are OFF for a network job', t.get('tools') == [], t.get('tools'))
        check('no working directory and no extra dirs reach the driver', 'cwd' not in t and 'addDirs' not in t)
        check('the system prompt says whose job this is and that the reply is the deliverable',
              'hired from the network' in t['system'] and 'the reply is the deliverable' in t['system'] and t['system'].endswith('Be brief.'))
        check('the prompt carries the title, the kind and the brief',
              'Job: T' in t['prompt'] and 'Kind: brief' in t['prompt'] and 'Do the thing' in t['prompt'])
        seen.clear()
        mw.default_run_task('x', {'driver': 'fake', 'allowWeb': True}, {})
        check('allowWeb widens to web only', seen['task'].get('tools') == ['web'])
        try:
            mw.default_run_task('x', {'driver': 'nope'}, {})
            check('an unknown driver is refused with its name', False, 'no raise')
        except RuntimeError as e:
            check('an unknown driver is refused with its name', "'nope'" in str(e))
    finally:
        drivers.get, base.run_task_text = real_get, real_run


# ── serve.py's doors ────────────────────────────────────────────────────────
def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def req(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={'Content-Type': 'application/json'} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b'null')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'null')


def boot(state_dir):
    port = free_port()
    env = dict(os.environ, PORT=str(port), CAFRESOHQ_ALLOWED_DIRS=state_dir, CAFRESOHQ_HQ_STATE_DIR=state_dir)
    for k in ('OCI_VAULT_NAMESPACE', 'OCI_VAULT_BUCKET', 'CAFRESOHQ_API_KEY'):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = f'http://127.0.0.1:{port}'
    for _ in range(80):
        try:
            if req('GET', base + '/health')[0] == 200:
                return base, proc
        except Exception:      # noqa: BLE001
            pass
        time.sleep(0.25)
    proc.terminate()
    return None, proc


def test_doors(host):
    print('serve.py — the /marketplace/worker doors')
    src = (ROOT / 'serve.py').read_text(encoding='utf-8')
    import re
    kp = re.search(r'_KEY_PROTECTED_PREFIXES = \((.*?)\n\)', src, re.S).group(1)
    hd = re.search(r'_HOST_DATA_PREFIXES = \((.*?)\n\)', src, re.S).group(1)
    check("'/marketplace' is on the key-protected prefix list", "'/marketplace'," in kp)
    check("'/marketplace/' is on the host-data prefix list", "'/marketplace/'," in hd)
    # The fleet image copies files by name; serve.py imports market_worker
    # lazily, so a copy missing from docker/Dockerfile would not fail the
    # boot — it would 500 the Offer tab on every fleet office (found #429).
    dockerfile = (ROOT / 'docker' / 'Dockerfile').read_text(encoding='utf-8')
    copied = ' '.join(l for l in dockerfile.splitlines() if l.startswith('COPY '))
    check('the fleet image ships ic_agent.py and market_worker.py (docker/Dockerfile COPY)',
          'ic_agent.py' in copied and 'market_worker.py' in copied)
    with tempfile.TemporaryDirectory() as d:
        base, proc = boot(d)
        check('serve.py boots', base is not None)
        if base is None:
            return
        try:
            code, st = req('GET', base + '/marketplace/worker/status')
            check('GET /marketplace/worker/status → 200', code == 200, code)
            try:
                ic.Principal.from_text(st.get('principal', ''))
                check('status names the worker key\'s principal (a valid self-authenticating principal)', len(ic.Principal.from_text(st['principal']).raw) == 29)
            except Exception as e:      # noqa: BLE001
                check('status names the worker key\'s principal', False, e)
            check('a fresh office is not configured and not running', st.get('configured') is False and st.get('running') is False)
            key = Path(d) / 'market' / 'worker-key.json'
            check('the key file was created under the office\'s own hq-state dir, 0600',
                  key.is_file() and stat.S_IMODE(key.stat().st_mode) == 0o600)
            code, pr = req('GET', base + '/marketplace/worker/principal')
            check('GET /marketplace/worker/principal agrees with status', code == 200 and pr.get('principal') == st.get('principal'))
            code, st2 = req('POST', base + '/marketplace/worker/config', {'pollSecs': 1, 'driver': 'ollama', 'allowWeb': 'yes', 'bogus': 1})
            check('config merges known keys, clamps pollSecs to 5, drops unknown ones',
                  code == 200 and st2['config']['pollSecs'] == 5 and st2['config']['driver'] == 'ollama'
                  and st2['config']['allowWeb'] is True and 'bogus' not in st2['config'])
            code, st3 = req('POST', base + '/marketplace/worker/config', {'canister': CANISTER, 'host': host})
            check('pointing it at a hall makes it configured', st3['configured'] is True and st3['canister'] == CANISTER)
            code, st4 = req('POST', base + '/marketplace/worker/start', {})
            check('start flips enabled and the loop runs', st4['config']['enabled'] is True and st4['running'] is True)
            code, st5 = req('POST', base + '/marketplace/worker/stop', {})
            check('stop flips it back', st5['config']['enabled'] is False)
            code, _ = req('GET', base + '/marketplace/worker/nope')
            check('an unknown marketplace route is a 404, not a proxy', code == 404)
        finally:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()


def main():
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Hall)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host = f'http://127.0.0.1:{srv.server_address[1]}'
    try:
        test_loop(host)
        test_privacy()
        test_doors(host)
    finally:
        srv.shutdown()
        srv.server_close()
    print()
    if FAILS:
        print(f'network coworker: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('network coworker: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
