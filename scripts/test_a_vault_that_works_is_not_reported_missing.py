#!/usr/bin/env python3
"""A fleet office called its own vault missing.

`/vault/status` decided whether a vault exists with a two-arm boolean:

    configured = (backend == 'rest' and rest_ok) or (backend == 'fs' and fs_ok)

`PUT /vault/note` dispatches on three. The third — `oci`, the Object
Storage backend the OCI Fleet containers are provisioned with — had a full
write arm and no row in that expression, so it fell off the end as False.

Measured 2026-08-16, office 9262 booted with OCI_VAULT_NAMESPACE and
OCI_VAULT_BUCKET set, exactly as a fleet container is:

    GET /vault/status   → configured: false,  backend: "oci",  exists: false
    PUT /vault/note     → 502 "oci: OCI SDK not installed — run: pip install oci"

The write door dispatched. The status door said there was nothing there.
Everything that asks before writing believed the status door:

  · `isVaultReady()` in hq-runtime.jsx reads `configured && exists`, so
    `toolsForAgent` handed every coworker on a fleet container no vault
    tool, and their cards said so.
  · Since the night-shift pre-flight landed (29637e5, the day before this),
    `vault_can_take_a_note` reads the same field — so a fleet night shift
    stopped starting at all. Measured against the same office, before and
    after this fix:

        pre-29637e5   iterations=1  (ran; wrote through the oci arm)
        29637e5       iterations=0  errors=1  'vault is not reachable …'
        this fix      iterations=1  writes as the bucket allows

The pre-flight is doing exactly what it was written to do. It asked the
office a question and the office gave a wrong answer about itself.

The durable check is not "oci is in the list". It is that every backend
`PUT /vault/note` can dispatch to has a row in the readiness table — a
fourth backend added next month is covered without anyone reading this
file, because that is the shape of the defect, not the identity of the
backend that had it.

Run: python3 scripts/test_a_vault_that_works_is_not_reported_missing.py
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
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """The fix explains the defect at length in a comment that names every
    backend. A bare search would find its own evidence."""
    return re.sub(r'^\s*#.*$', '', src, flags=re.M)


def section(start_marker, end_marker):
    """One route out of the raw file, comments stripped afterwards — the
    markers that bound a route ARE comments, so the slice has to happen
    first."""
    a = SERVE_RAW.index(start_marker)
    return strip_comments(SERVE_RAW[a:SERVE_RAW.index(end_marker, a)])


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def get_json(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception:
        return None


def boot(**extra_env):
    """Bring up a real serve.py and return (base_url, kill). The status
    answer is assembled from module-level config read at import time, so
    env is the only way to ask it the question a fleet container asks."""
    tmp = tempfile.mkdtemp(prefix='vaultstatus-')
    port = free_port()
    env = dict(os.environ, PORT=str(port),
               CAFRESOHQ_HQ_STATE_DIR=str(Path(tmp) / 'state'))
    # A stray OCI_* in the developer's own shell would otherwise decide the
    # answer for the arms that are supposed to be missing it.
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

    for _ in range(80):
        if get_json(base + '/vault/status') is not None:
            return base, kill
        time.sleep(0.25)
    kill()
    return None, (lambda: None)


def status(**env):
    base, kill = boot(**env)
    if base is None:
        return None
    try:
        return get_json(base + '/vault/status')
    finally:
        kill()


def main():
    print('a vault that works is not reported missing')

    # ── 1. THE SWEEP: status must answer for every backend note writes to ─
    #
    # Both halves come out of the source, so neither one can be the thing
    # that is wrong. Naming 'oci' here would pass a file whose FOURTH
    # backend repeats this exactly, which is how this one got in: 'oci' was
    # added to the write handler and nobody was required to add it here.
    writer = section("if path == '/vault/note' and method == 'PUT':",
                     '# ---------- Delete ----------')
    dispatched = set(re.findall(r"_vault_backend == '(\w+)'", writer))
    check('the write handler names more than one backend',
          len(dispatched) >= 2,
          [sorted(dispatched), '— if PUT stops dispatching on _vault_backend '
           'this suite is checking nothing; re-read it'])

    stat = section("if path == '/vault/status' and method == 'GET':",
                   '# ---------- Discover local vaults ----------')
    table = re.search(r'backend_ready = \{([^}]*)\}', stat)
    check('the status door answers from a table, not a chain of ands',
          table is not None,
          '— a per-backend boolean chain is what silently answered False '
          'for the backend nobody added to it')
    reported = set(re.findall(r"'(\w+)':", table.group(1))) if table else set()
    missing = sorted(dispatched - reported)
    check('every backend the office writes with is a backend it reports',
          not missing,
          [missing, '— the write door dispatches to these and the status '
           'door has no row for them, so the whole product asks about a '
           'vault that works and is told it is not there'])

    # The default matters as much as the rows: a table lookup that raised, or
    # one that guessed True, would trade this defect for a louder one.
    check('a backend with no row is not configured, and does not raise',
          re.search(r'configured = backend_ready\.get\(_vault_backend,\s*False\)',
                    stat) is not None,
          '— .get(…, False): an unknown backend is honestly "no vault", not '
          'a 500 and not an optimistic yes')

    # ── 2. no network probe on the polled endpoint ───────────────────────
    check('the status door does not build the OCI client',
          '_oci_object_client(' not in stat,
          '— the UI polls this endpoint; _oci_object_client can hang on IMDS '
          'when IAM is not ready yet (its own comment says so), and a status '
          'door that hangs is a worse answer than an optimistic one')
    check('...and the presence check is the two names a write needs',
          re.search(r'oci_ok = bool\(_oci_vault_namespace and _oci_vault_bucket\)',
                    stat) is not None,
          '— _oci_obj_key + put_object need exactly these; a bucket that is '
          'named but broken comes back from the write as a 502 that says why')

    # ── 3. drive the real endpoint ───────────────────────────────────────
    fleet = status(CAFRESOHQ_VAULT_BACKEND='oci',
                   OCI_VAULT_NAMESPACE='axhoibfmftgb',
                   OCI_VAULT_BUCKET='cafresohq-fleet-vault',
                   OCI_VAULT_PREFIX='2vxsx-fake/')
    check('a provisioned fleet office has a vault', fleet and fleet['configured'],
          [fleet, '— this is the measured reproduction: a container whose '
           'write arm works, reporting no vault'])
    check('...and says so to the older field too',
          fleet and fleet['exists'] is True,
          '— hq-runtime reads `configured && exists`; one of the two saying '
          'no is the whole gate saying no')
    check('...and names the bucket it would write to',
          fleet and fleet.get('ociBucket') == 'cafresohq-fleet-vault',
          [fleet and fleet.get('ociBucket'),
           '— fsExists and restReachable both show their work; the third '
           'backend should not be the one the boss has to take on faith'])
    check('...without claiming the local directory is the answer',
          fleet and fleet['backend'] == 'oci',
          fleet)

    half = status(CAFRESOHQ_VAULT_BACKEND='oci',
                  OCI_VAULT_NAMESPACE='axhoibfmftgb', OCI_VAULT_BUCKET='')
    check('a fleet office with no bucket has no vault',
          half is not None and half['configured'] is False,
          [half, '— "set up" and "half set up" must not read the same; the '
           'night-shift pre-flight cancels on this answer'])
    check('...and offers no bucket name it cannot write to',
          half is not None and not half.get('ociBucket'), half)

    plain = status()
    check('a plain local office is unchanged',
          plain and plain['configured'] and plain['backend'] == 'fs'
          and plain['fsExists'],
          plain)
    check('...and reports no bucket', plain and not plain.get('ociBucket'),
          plain)

    unreachable = status(CAFRESOHQ_VAULT_BACKEND='rest',
                         CAFRESOHQ_OBSIDIAN_URL='http://127.0.0.1:1',
                         CAFRESOHQ_OBSIDIAN_KEY='k')
    check('a shut Obsidian is still no vault',
          unreachable is not None and unreachable['configured'] is False
          and unreachable['restReachable'] is False,
          [unreachable, '— the rest arm probes for real and must keep doing '
           'it; this fix loosens the oci arm, not that one'])

    # ── 4. the reader this broke ─────────────────────────────────────────
    # The pre-flight is not wrong and is not being changed. It asks the
    # office one question, and the point of the fix is the answer.
    sys.path.insert(0, str(ROOT))
    import night_runner as nr           # noqa: E402

    base, kill = boot(CAFRESOHQ_VAULT_BACKEND='oci',
                      OCI_VAULT_NAMESPACE='axhoibfmftgb',
                      OCI_VAULT_BUCKET='cafresohq-fleet-vault')
    try:
        check('the office came up for the pre-flight', base is not None)
        if base:
            ctx = nr.NightContext(base, '', str(Path(tempfile.gettempdir())), '')
            check('a fleet night shift is allowed to start',
                  nr.vault_can_take_a_note(ctx) == (True, ''),
                  [nr.vault_can_take_a_note(ctx),
                   '— 0 iterations, 0 tokens and "check Connections" on a '
                   'container whose bucket is right there'])
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
