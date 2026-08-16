#!/usr/bin/env python3
"""Connections offered to take a fleet office's vault away.

Three backends write notes — fs, rest, oci. Settings → Connections knew
two. The whole model was one boolean:

    const isRest = status.backend === 'rest';

so `!isRest` meant "local folder", and on a fleet office running the oci
backend the screen lit LOCAL DIRECTORY as the SELECTED storage, printed a
green "✓ N notes indexed" against a container-local path that was not the
vault, and rendered USE APP VAULT / DETECT OBSIDIAN / SAVE. All three post
`{backend:'fs'}`.

Measured 2026-08-16 against a provisioned office (bucket
cafresohq-fleet-vault):

    GET  /vault/status                        → backend oci, configured true
    POST /vault/configure {"backend":"fs",…}  → backend fs
    GET  /vault/status                        → configured TRUE, backend fs
    POST /vault/configure {"backend":"oci"}   → 400 bad backend: oci

One click moved the office off its bucket. `configured` stayed true, so
nothing warned — and the door refused the only value that would undo it.
Short of restarting the container there was no way back, and in a
container a restart also discards whatever landed in the local folder
meanwhile.

This is the screen every honesty sentence in the office points at. The
night-shift save door says "no vault to file into yet — check
Connections"; the coworker cards and the tool grant say the same. A door
named as the way forward has to be one, and on a fleet office this one was
a trapdoor.

The fix keeps 'oci' provisioned rather than typed — the container signs
its own requests and there is nothing here that could supply credentials —
so the screen's job is to say truly which vault this is, name the bucket,
say where the setting lives, and not offer controls that move it by
accident. The server's job is to let a boss who left come back.

Guards:
  · one list of backends, and the configure door validates against it
  · every backend the write handler dispatches on is in that list
  · 'oci' is accepted only by an office that HAS fleet storage, and the
    refusal names where the setting actually lives
  · the post-configure route gate asks the right question per backend —
    the `else` it replaces asked oci for a local folder
  · the screen derives three states, and the fs body is gated on isFs
  · the FLEET STORAGE chip keys off the bucket, not the active backend,
    so the way back does not close behind the boss

Run: python3 scripts/test_the_vault_screen_knows_which_vault.py
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
PROVIDERS_RAW = (ROOT / 'modals' / 'providers.jsx').read_text(encoding='utf-8')
FAILS = []

BUCKET = 'cafresohq-fleet-vault'
NAMESPACE = 'axfleetns'


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


def section(src, start, end):
    """A slice between two markers, or '' if either is missing.

    Empty rather than raising: under a full revert the markers this suite
    slices on do not exist, and a suite that dies there reports "caught"
    while leaving every check below it unrun — caught for the wrong reason,
    which proves nothing about the checks that were supposed to catch it.

    Empty rather than "the rest of the file", too: a missing end marker
    used to widen the slice to everything below it, so a check looking for
    a string in one handler would find it in some other handler entirely
    and pass for the wrong reason.
    """
    a = src.find(start)
    if a < 0:
        return ''
    b = src.find(end, a)
    return src[a:b] if b > a else ''


def py_section(start, end):
    """A slice of serve.py taken BEFORE comments are stripped.

    The handler boundaries here are `# ---------- Name ----------` banners
    and one plain comment line. Slicing the stripped source looks for
    markers that stripping has already removed — the first cut of this
    suite did exactly that and reported two false FAILs against a fix that
    was in the file.
    """
    return strip_py_comments(section(SERVE_RAW, start, end))


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
    tmp = tempfile.mkdtemp(prefix='vaultscreen-')
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

    # Polls a route that reads a file, not /vault/status: the status probe
    # can take its full timeout on some backends, and a readiness poll must
    # not be the slowest thing in the suite.
    for _ in range(80):
        if call(base + '/missions/scheduled')[0] == 200:
            return base, kill
        time.sleep(0.25)
    kill()
    return None, (lambda: None)


def main():
    print('the vault screen knows which vault')
    src = strip_py_comments(SERVE_RAW)
    ui = strip_js_comments(PROVIDERS_RAW)

    # ── 1. one list of backends ──────────────────────────────────────────
    # The configure door kept its own shorter copy of the set, which is how
    # it came to refuse the one backend a fleet office runs on.
    check('the office has one list of the backends it writes with',
          re.search(r"_VAULT_BACKENDS\s*=\s*\(", src) is not None,
          '— two lists is how one of them goes stale')
    listed = re.search(r"_VAULT_BACKENDS\s*=\s*\(([^)]*)\)", src)
    names = set(re.findall(r"'(\w+)'", listed.group(1))) if listed else set()
    check('...and all three backends are on it', names == {'fs', 'rest', 'oci'},
          [sorted(names), "— 'oci' missing is the reproduced bug"])

    cfg = py_section('# ---------- Configure ----------', '# Routes from here')
    check('the configure door validates against that list, not its own copy',
          'in _VAULT_BACKENDS' in cfg,
          "— a literal ('fs', 'rest') here is the copy that went stale")

    # Structural sweep, same shape as the readiness table's: whatever the
    # write handler dispatches on has to be a backend the door will accept,
    # or the office can reach a state its own settings screen cannot name.
    write = py_section('# ---------- Write/Append ----------',
                       '# ---------- Delete ----------')
    dispatched = set(re.findall(r"_vault_backend == '(\w+)'", write))
    check('every backend the write door dispatches on is on the list',
          dispatched and dispatched <= names,
          [sorted(dispatched), sorted(names)])

    # ── 2. 'oci' is provisioned, not typed ───────────────────────────────
    check('selecting fleet storage is gated on the office having it',
          re.search(r"bk == 'oci' and not \(_oci_vault_namespace and "
                    r"_oci_vault_bucket\)", cfg) is not None,
          '— a laptop office must not be able to pick a backend it can '
          'never write to; that is the same wrong door in the other '
          'direction')

    # ── 3. the route gate asks the right question per backend ────────────
    gate = py_section('# Routes from here', '# ---------- List ----------')
    check('the route gate has an arm for fleet storage',
          "elif _vault_backend == 'oci':" in gate,
          '— the else it replaces asked every non-rest backend for a '
          '_vault_root, which is the wrong question on oci')
    check('...and that arm asks about the bucket, not a local folder',
          '_oci_vault_bucket' in gate and '_vault_root' in gate and
          gate.index('_oci_vault_bucket') < gate.rindex('_vault_root'),
          '— a provisioned fleet office turned away over a folder it '
          'never writes to')

    # ── 4. the screen derives three states ───────────────────────────────
    check('the screen knows there is a third backend',
          "const isOci = status.backend === 'oci'" in ui,
          '— isRest was the whole model, so !isRest meant "local folder"')
    check('...and the local arm is its own state, not the absence of rest',
          re.search(r'const isFs = !isRest && !isOci', ui) is not None,
          '— !isRest is true on a fleet office, which is how LOCAL '
          'DIRECTORY came to render as the selected storage')
    check('the local body renders only for the local backend',
          '{isFs && (<>' in ui and '{!isRest && (<>' not in ui,
          '— USE APP VAULT / DETECT OBSIDIAN / SAVE each post '
          "{backend:'fs'}, and on a fleet office they were one click "
          'from moving the vault off the bucket')
    check('the fleet arm has a body of its own',
          '{isOci && (<>' in ui,
          '— a backend with no panel is a screen that cannot say what '
          'the vault IS')

    # ── 5. the way back does not close behind the boss ───────────────────
    check('the fleet chip keys off having a bucket, not off using one',
          re.search(r'const hasFleetStorage = isOci \|\| !!status\.ociBucket',
                    ui) is not None,
          '— keyed off isOci, the control that returns the boss is the '
          'one control the state they landed in stops rendering')
    check('...and the chip is what renders it',
          re.search(r'\{hasFleetStorage && \(', ui) is not None
          and 'FLEET STORAGE' in ui,
          '— hasFleetStorage computed and not used is the Roster '
          'checkbox all over again')

    # ── 6. what the fleet arm says ───────────────────────────────────────
    oci_body = section(ui, '{isOci && (<>', '{isFs && (<>')
    # Pinned to the INTERPOLATION, not to a mention of the field: the panel
    # also tests `status.ociBucket` as a condition, and a first cut of this
    # check that only looked for the name survived an arm that deleted the
    # rendered value and left the condition behind — a screen that reads the
    # bucket and does not show it.
    check('the fleet panel shows the bucket it files into',
          '${status.ociBucket}' in oci_body,
          '— /vault/status has answered with the bucket name since the '
          'readiness table landed; not showing it is a screen describing '
          'a vault it will not identify')
    check('...and says where the setting actually lives (§7)',
          'OCI_VAULT_NAMESPACE' in oci_body and 'OCI_VAULT_BUCKET' in oci_body,
          '— "you cannot set this here" is only honest if it also says '
          'where it is set')
    check('...and does not print a green tick for a folder that is not the vault',
          'status.fsExists' not in oci_body,
          '— the reproduced screen showed "✓ N notes indexed" against a '
          'container-local path while the notes were in object storage')
    check('...and points at the way out by name, not by direction',
          'LOCAL DIRECTORY above' in oci_body and 'below' not in oci_body,
          '— the storage row is above this paragraph, so "switching to a '
          'local directory below" sends the boss looking the wrong way; '
          'the control has a label, and the label is the door')

    refusal = re.search(r"'this office has no fleet storage[^}]*", SERVE_RAW)
    # Joined, not read raw: the sentence is written as adjacent literals
    # wrapped across three source lines, so "set when the office is set up"
    # exists in what the boss reads and nowhere in the file. A check that
    # greps the source is asking about the formatting, not the sentence.
    refusal_text = ''.join(re.findall(r"'([^']*)'", refusal.group(0))) if refusal else ''
    check('the refusal speaks in office words with a way forward (§6/§7)',
          'OCI_VAULT_NAMESPACE' in refusal_text
          and 'set when the office is set up' in refusal_text
          and 'container' not in refusal_text,
          [refusal_text[:90], '— "bad backend: oci" was a stack trace at '
           'the boss and named no door at all. The replacement has to name '
           'where the setting lives AND stay in office words: the first '
           'draft said "when the container is provisioned", which is the '
           'hosting word §6 rejects, in a sentence the boss reads as '
           'msg.text on the Connections panel'])

    # ── 7. live: a fleet office can leave and come back ──────────────────
    base, kill = boot(CAFRESOHQ_VAULT_BACKEND='oci',
                      OCI_VAULT_NAMESPACE=NAMESPACE, OCI_VAULT_BUCKET=BUCKET)
    try:
        check('a provisioned fleet office boots on its bucket', base is not None)
        if base:
            s, before = call(base + '/vault/status')
            check('...and says so, with the bucket named',
                  before.get('backend') == 'oci' and before.get('configured') is True
                  and before.get('ociBucket') == BUCKET, before)
            call(base + '/vault/configure', {'backend': 'fs'})
            s, mid = call(base + '/vault/status')
            check('...the bucket is still reported after switching away',
                  mid.get('backend') == 'fs' and mid.get('ociBucket') == BUCKET,
                  [mid, '— this is the field the chip that offers the way '
                   'back is drawn from'])
            s, back = call(base + '/vault/configure', {'backend': 'oci'})
            check('...and the boss can come back through the same door',
                  s == 200 and back.get('backend') == 'oci',
                  [s, back, '— 400 here is the reproduced trapdoor'])
    finally:
        kill()

    # ── 8. live: an office with no fleet storage is refused, and unmoved ─
    base, kill = boot(CAFRESOHQ_VAULT_BACKEND='fs')
    try:
        check('a laptop office boots', base is not None)
        if base:
            s, err = call(base + '/vault/configure', {'backend': 'oci'})
            check('...and cannot select a backend it has no storage for',
                  s == 400 and 'fleet storage' in (err.get('error') or ''),
                  [s, err])
            s, after = call(base + '/vault/status')
            check('...and the refusal leaves its own vault alone',
                  after.get('backend') == 'fs' and after.get('configured') is True,
                  [after, '— a refused change that half-applies is worse '
                   'than the change'])
    finally:
        kill()

    # ── 9. live: a misprovisioned fleet office names the right thing ─────
    base, kill = boot(CAFRESOHQ_VAULT_BACKEND='oci', OCI_VAULT_BUCKET='')
    try:
        check('a fleet office with no bucket still boots', base is not None)
        if base:
            s, st = call(base + '/vault/status')
            check('...and reports itself unconfigured without claiming a bucket',
                  st.get('backend') == 'oci' and st.get('configured') is False
                  and not st.get('ociBucket'), st)
            s, err = call(base + '/vault/list')
            msg = err.get('error') or ''
            check('...and the routes turn work away naming fleet storage',
                  s == 503 and 'fleet storage' in msg,
                  [s, msg])
            check('...not a local folder it does not use',
                  'POST /vault/configure' not in msg and '"root"' not in msg,
                  [msg, '— the old else sent a fleet boss to configure a '
                   'directory that has nothing to do with their vault'])
    finally:
        kill()

    print()
    if FAILS:
        print('FAILED %d check(s):' % len(FAILS))
        for f in FAILS:
            print('  · ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
