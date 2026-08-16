#!/usr/bin/env python3
"""A night shift was confirmed by an office that knew it had nowhere to file.

Every mission `build_prompt` writes for ends with a mandatory vault write;
the notes ARE the deliverable. `POST /missions/schedule` validated the
topic, clamped the duration, capped the count — and never asked the one
question that decides whether tonight can produce anything.

Measured 2026-08-16, office 9261, vault pointed at a closed Obsidian REST:

    GET  /vault/status     → configured: false,  restReachable: false
    POST /missions/schedule → {"ok": true, "schedule": {…}}

Two keys. Nothing about the vault. Worse than silence, the reply echoes
`vaultFolder: "Research/ooo"` — a folder the office has just established
nothing can be written to — and the modal answered "Scheduled 🌙 — runs
even with this tab closed", which is true and beside the point. The boss
finds out at 1am.

The sibling fix at the run door (the night-shift pre-flight) is what keeps
this cheap once it happens: 0 iterations, 0 tokens, one sentence. It does
not stop the boss from being told, at 9pm, that a thing is set up.

Deliberately advisory, and the suite pins that as hard as it pins the
warning. A vault down at 9pm can be up by 1am, so the schedule is SAVED
either way and the run door stays authoritative. And a probe that cannot
answer in time must not manufacture a warning — same fail-open reasoning
as the run door, one moment earlier.

Guards:
  · the office asks, and says so in the reply
  · the modal READS the field — a warning nothing renders is the shipped
    Roster checkbox all over again
  · the confirmation is not replaced by the caveat; both halves are true
  · the schedule is still saved, and still in the list afterwards
  · an unanswerable probe warns about nothing
  · the probe is short here and unchanged everywhere else, and it happens
    before _night_lock is taken

Run: python3 scripts/test_the_schedule_door_says_what_it_knows.py
"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVE_RAW = (ROOT / 'serve.py').read_text(encoding='utf-8')
MISSIONS_RAW = (ROOT / 'missions.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_py_comments(src):
    """The fix argues for itself at length in comments that use every word
    these checks look for."""
    return re.sub(r'^\s*#.*$', '', src, flags=re.M)


def strip_js_comments(src):
    return re.sub(r'/\*[\s\S]*?\*/', '', re.sub(r'^\s*//.*$', '', src, flags=re.M))


def func(src, name):
    """One function's source, or '' if it is not there.

    Empty rather than raising: under a full revert `_vault_readiness` does
    not exist, and a suite that dies at that point reports "caught" while
    leaving every check below it unrun — caught for the wrong reason, which
    proves nothing about the checks that were supposed to catch it.
    """
    a = src.find('def %s(' % name)
    if a < 0:
        return ''
    m = re.search(r'\n(?=(?:def |    def |# ---- ))', src[a + 1:])
    return src[a:a + 1 + m.start()] if m else src[a:]


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def call(url, body=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(
        url, data=data, method='POST' if data else 'GET',
        headers={'Content-Type': 'application/json'} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}
    except Exception:
        return 0, {}


def boot(**extra_env):
    tmp = tempfile.mkdtemp(prefix='scheduledoor-')
    port = free_port()
    env = dict(os.environ, PORT=str(port),
               CAFRESOHQ_HQ_STATE_DIR=str(Path(tmp) / 'state'))
    for k in ('OCI_VAULT_NAMESPACE', 'OCI_VAULT_BUCKET', 'OCI_VAULT_PREFIX',
              'CAFRESOHQ_VAULT_BACKEND', 'CAFRESOHQ_VAULT',
              'CAFRESOHQ_OBSIDIAN_URL', 'CAFRESOHQ_OBSIDIAN_KEY'):
        env.pop(k, None)
    env.update({k: str(v) for k, v in extra_env.items()})
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT),
                            env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT)
    base = 'http://127.0.0.1:%d' % port

    def kill():
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    # Waits on a route that reads a file, NOT on /vault/status: with the
    # backend pointed at a routable-but-dead host the status probe takes the
    # full default 30s, and the readiness poll would spend minutes learning
    # what it is about to test on purpose.
    for _ in range(80):
        if call(base + '/missions/scheduled')[0] == 200:
            return base, kill
        time.sleep(0.25)
    kill()
    return None, (lambda: None)


# Far enough out that the scan thread never picks it up mid-test.
SOON = int(time.time() * 1000) + 86_400_000


def schedule(base, topic):
    return call(base + '/missions/schedule', {
        'topic': topic, 'agentId': 'kip', 'agentName': 'Kip',
        'vaultFolder': 'Research/night', 'startAt': SOON,
        'recurrence': 'once', 'durationMs': 600_000, 'intervalMs': 300_000})


def main():
    print('the schedule door says what it knows')
    src = strip_py_comments(SERVE_RAW)
    ui = strip_js_comments(MISSIONS_RAW)

    # ── 1. one computation, two doors ────────────────────────────────────
    # The readiness answer used to live inline in the status handler. A
    # second door needing it is exactly how a copy gets made, and a copy is
    # how one door starts answering last week's question.
    check('the office has one place that decides whether a note can land',
          src.count('backend_ready = {') == 1
          and 'def _vault_readiness(' in src,
          [src.count('backend_ready = {'),
           '— two tables is two answers, and the boss reads whichever door '
           'they happened to open'])
    readiness = func(src, '_vault_readiness')
    for door in ("if path == '/vault/status' and method == 'GET':",
                 'def _missions_schedule('):
        seg = src[src.index(door):][:2500]
        check('%s reads it rather than recomputing' % door.split('(')[0][:34],
              '_vault_readiness(' in seg and 'backend_ready' not in seg, seg[:200])

    # ── 2. the probe is short HERE and unchanged everywhere else ─────────
    sched_fn = func(src, '_missions_schedule')
    m = re.search(r'_vault_readiness\(probe_timeout=(\d+)\)', sched_fn)
    check('the save door caps how long it will wait to be advised',
          m is not None and int(m.group(1)) <= 5,
          [m and m.group(1), '— the save is the job and this only decorates '
           'the confirmation; 30s of Obsidian silence must not become 30s of '
           'a boss staring at a button'])
    check('...and the default stayed 30s for every other caller',
          re.search(r'def _obsidian_request\([\s\S]{0,400}?timeout: float = 30',
                    src) is not None,
          '— a shorter global default would silently shorten the real vault '
          'reads and writes, which is not what this door asked for')
    ask_at = sched_fn.find('_vault_readiness(')
    lock_at = sched_fn.find('with _night_lock')
    check('...and it is asked before the night lock is taken',
          0 <= ask_at < lock_at, [ask_at, lock_at,
          '— a 3s network call inside _night_lock stalls the scan thread '
          'that starts tonight\'s runs'])

    # ── 3. advisory, not a gate ──────────────────────────────────────────
    check('a warning does not stop the schedule being saved',
          re.search(r'return self\._send_json\(200, \{\'ok\': True', sched_fn)
          is not None
          and 'if warning' not in sched_fn and 'if not warning' not in sched_fn,
          '— a vault down at 9pm can be up by 1am; refusing the save would '
          'be a worse wrong answer than the silence this replaces')
    check('an unanswered probe warns about nothing',
          re.search(r"warning = '' if \(v\['configured'\] or v\['unanswered'\]\)",
                    sched_fn) is not None,
          "— same reasoning as the run door: a question nobody answered must "
          'not be the thing that puts a scary sentence on a correct save')
    check('...and only a timeout counts as unanswered',
          re.search(r'except \(socket\.timeout, TimeoutError\)', readiness)
          is not None,
          '— a refused connection IS an answer, and it is the reproduced '
          'case; swallowing it would make this fix do nothing')

    # ── 4. the sentence ──────────────────────────────────────────────────
    sent = re.search(r"NO_VAULT_AT_SAVE = '([^']+)'", src)
    check('the save door has one sentence, named once', sent is not None,
          '— spelled inline it drifts from the door the run reports')
    s = sent.group(1) if sent else ''
    sys.path.insert(0, str(ROOT))
    import night_runner as nr           # noqa: E402
    run_door = nr.vault_refused_sentence(503)
    check('...and it sends the boss to the same screen the run door does',
          'Connections' in s and 'Connections' in run_door, [s, run_door])
    check('...and is not a copy of it',
          s != run_door,
          [s, '— nothing has been refused at 9pm and the schedule IS saved; '
           'reporting a failed write would be a different lie'])
    check('...says what happened AND what to do', '—' in s, [s, '§7'])
    check('...in office words',
          not re.search(r'[A-Z]{2,}|_|\b\d{3}\b', s), [s, '§6'])
    check('...and fits the narrowest surface that shows it',
          len(s) <= nr.NIGHT_ERROR_MAX,
          '%d > %d: %r' % (len(s), nr.NIGHT_ERROR_MAX, s))

    # ── 5. the modal reads it ────────────────────────────────────────────
    # A field the server sets and no screen renders is the shipped Roster
    # checkbox: present, inert, and worse than absent because it reads as
    # done.
    sfn = ui[ui.index('const schedule = async ('):]
    sfn = sfn[:sfn.index('const cancel = async (')]
    check('the modal reads the warning off the reply',
          'res.vaultWarning' in sfn,
          '— the server can be as honest as it likes; nobody is looking')
    check('...and the confirmation still confirms',
          len(re.findall(r'Scheduled', sfn)) >= 2,
          [sfn, '— the caveat rides the confirmation; a boss who saved a '
           'schedule needs to know it saved'])
    check('...and the two arms are not the same string',
          re.search(r'res\.vaultWarning\s*\n?\s*\?', sfn) is not None,
          '— a ternary that renders the same message either way is a field '
          'that is read and then thrown away')

    # ── 6. drive the real door ───────────────────────────────────────────
    base, kill = boot()
    try:
        check('the office came up', base is not None)
        st, rep = schedule(base, 'a night with a vault')
        check('a healthy office confirms without a caveat',
              st == 200 and rep.get('ok') and rep.get('vaultWarning') == '',
              rep)
    finally:
        kill()

    # Port 1 refuses instantly — this is the reproduced case, an Obsidian
    # that is configured and shut.
    base, kill = boot(CAFRESOHQ_VAULT_BACKEND='rest',
                      CAFRESOHQ_OBSIDIAN_URL='http://127.0.0.1:1',
                      CAFRESOHQ_OBSIDIAN_KEY='k')
    try:
        check('the office with a shut vault came up', base is not None)
        st, rep = schedule(base, 'a night with nowhere to file')
        check('the reproduced save is still a save',
              st == 200 and rep.get('ok') is True, rep)
        check('...and it says what it knows',
              rep.get('vaultWarning') == s,
              [rep.get('vaultWarning'),
               '— two keys and a vaultFolder nothing can be written to'])
        _st, listing = call(base + '/missions/scheduled')
        check('...and the schedule really is on the board',
              any(x.get('topic') == 'a night with nowhere to file'
                  for x in (listing.get('schedules') or [])),
              [listing, '— advisory means saved; if the warning became a '
               'refusal this suite must go red'])
    finally:
        kill()

    # 10.255.255.1 is routable-but-dead: the probe times out rather than
    # being refused, so the office genuinely does not know.
    base, kill = boot(CAFRESOHQ_VAULT_BACKEND='rest',
                      CAFRESOHQ_OBSIDIAN_URL='http://10.255.255.1:27124',
                      CAFRESOHQ_OBSIDIAN_KEY='k')
    try:
        check('the office with an unreachable vault came up', base is not None)
        t0 = time.time()
        st, rep = schedule(base, 'a night the office cannot vouch for')
        took = time.time() - t0
        check('a probe that cannot answer adds no caveat',
              st == 200 and rep.get('vaultWarning') == '',
              [rep, '— the office does not know, and saying "no vault" on a '
               'guess is the wrong door in the other direction'])
        check('...and the boss is not left waiting on it',
              took < 15,
              '%.1fs — the old 30s default would have been the whole save'
              % took)
    finally:
        kill()

    print()
    if FAILS:
        print('%d check(s) failed' % len(FAILS))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
