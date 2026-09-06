#!/usr/bin/env python3
"""#415 — every vault-writing door's success body must name the file it wrote.

`## 410` measured one end of this and left it EXPOSED:

    PUT /vault/note?path=Research/topic&mode=write
      → 200 {"path": "Research/topic", "mode": "write", "size": 8}
      on disk: Research/topic.md

Four separate rewrites live between what a caller ASKS for and what the fs
backend WRITES, and only the first of them is "the extension":

  1. `_vault_resolve` appends '.md' to a name that carries no extension;
  2. …and a suffix only counts as an extension when it is SHAPED like one
     (1-8 alphanumerics, at least one letter), so the note TITLES
     "Q3 v1.2 plan" (suffix ".2 plan") and "Meeting 2026.08.30" (suffix
     ".30") get '.md' too, deliberately;
  3. leading '/' is stripped and '\\' is folded to '/', so "/Deep\\Dir/note"
     is written at "Deep/Dir/note.md";
  4. the upload door's collision sidestep steps to a numbered variant
     through `fs_routes.claim_name`, so a second "README" lands as
     "README (2).md".

Every one of those was invisible in the answer. Measured pre-fix on a real
serve.py with an empty vault:

    PUT    Research/topic          → "Research/topic"        Research/topic.md
    PUT    Notes/Q3 v1.2 plan      → "Notes/Q3 v1.2 plan"    …plan.md
    PUT    /Deep\\Dir/note          → "/Deep\\Dir/note"        Deep/Dir/note.md
    UPLOAD README                  → "Up/README"             Up/README.md
    UPLOAD README (again)          → "Up/README (2)"         Up/README (2).md
    RENAME →Research/renamed       → "Research/renamed"      …renamed.md

The consequence is not the mismatch itself — the READ doors run the same
resolver, so a GET of the wrong name still finds the file. It is that the
returned string is what downstream matches EXACTLY on: `_ctx.meta.filedAs`
→ the 'done' event's `arg` → `agentFiledPath` → `task.artifactPath` → the
out-tray's "open the latest", `buildDelivery`'s duplicate check, and the
receipts tray's title, which `anchorWorkReceipt` writes ON CHAIN. None of
those can be matched against a `/vault/list` row, because no listing row
holds the uncorrected name.

The fix is the exporters' own mechanism, not a second one: serve.py's
`_vault_rel_out` derives the answer from the path OBJECT that was written
(`relative_to(root)`, exactly `exporters._vault_binary_path`'s callers'
`rel_out = str(out_path.relative_to(...))`, #180/#401), so all four rewrites
and any fifth are covered without re-deriving a rule from the string. The
VAULT_NEW / VAULT_APPEND / MEMORY_WRITE / MEMORY_APPEND tools then carry it
out on `_ctx.meta.filedAs`, the channel the three EXPORT_ tools already use.

Round 1 is the general invariant on a real server: every 2xx success body
from every vault-writing door names a path the Library actually holds. It
carries a non-vacuity arm — the run is only meaningful if several probes
were genuinely REWRITTEN on the way in, so it counts those and fails if
too few happened.

Round 2 is the tool half under node, on real lifted source.

Round 3 is structural, so a fifth door added later has to answer the
question too.

Run: python3 scripts/test_every_vault_write_door_names_the_file_it_wrote.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVE = ROOT / 'serve.py'
HQ_RUNTIME = ROOT / 'hq-runtime.jsx'
ARTIFACTS = ROOT / 'app' / 'artifacts.jsx'

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = '') -> None:
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond and detail else ''))
    if not cond:
        FAILS.append(name)


# ── plumbing ───────────────────────────────────────────────────────────────
def free_port() -> int:
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def http(url, method='GET', body=None, headers=None):
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def on_disk(vault: str) -> set:
    """Every file AND folder under the vault, vault-relative, posix-spelled."""
    out = set()
    for r, dirs, files in os.walk(vault):
        for n in list(dirs) + list(files):
            out.add(Path(os.path.join(r, n)).relative_to(vault).as_posix())
    return out


def listing(base: str, headers: dict) -> set:
    st, raw = http(base + '/vault/list', headers=headers)
    if st != 200:
        return set()
    try:
        return {e.get('path') for e in (json.loads(raw).get('files') or [])}
    except Exception:
        return set()


# ── source lifting — returns '' rather than raising, so a reverted fix
#    surfaces as a NAMED failing check instead of a traceback that takes the
#    whole run down with it (`## 404`'s lesson, `## 410`'s practice). ───────
def _balanced(src: str, start: int, o: str, c: str) -> str:
    depth, j = 0, start
    while j < len(src):
        if src[j] == o:
            depth += 1
        elif src[j] == c:
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
        j += 1
    return ''


def lift_tool(src: str, key: str) -> str:
    marker = f'\n  {key}: {{'
    i = src.find(marker)
    if i == -1:
        return ''
    return _balanced(src, i + len(marker) - 1, '{', '}')


def lift_fn(src: str, name: str) -> str:
    m = re.search(r'^function %s\s*\(' % re.escape(name), src, re.M)
    if not m:
        return ''
    body_start = src.find('{', m.end() - 1)
    if body_start == -1:
        return ''
    body = _balanced(src, body_start, '{', '}')
    if not body:
        return ''
    return src[m.start():body_start] + body


def lift_on_tool(src: str, anchor: str) -> str:
    i = src.find(anchor)
    if i == -1:
        return ''
    j = src.rfind('onTool(', 0, i)
    if j == -1:
        return ''
    expr = _balanced(src, j + len('onTool'), '(', ')')
    return ('onTool' + expr) if expr else ''


# ── Round 1: the invariant, on a real server ───────────────────────────────
def round1_live_server():
    print()
    print('Round 1 — every 2xx success body names a path the Library holds')
    key = 'vault-filedas-test-key'
    port = free_port()
    with tempfile.TemporaryDirectory() as td:
        vault = os.path.join(td, 'vault')
        os.makedirs(vault)
        env = dict(os.environ)
        env.update({
            'CAFRESOHQ_API_KEY': key,
            'CAFRESOHQ_HQ_STATE_DIR': os.path.join(td, 'state'),
            'CAFRESOHQ_VAULT': vault,
            'PORT': str(port),
            'GAP_CRON': '0', 'NEWS_CRON': '0', 'TOPICS_CRON': '0',
        })
        proc = subprocess.Popen(
            [sys.executable, 'serve.py'], cwd=str(ROOT), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f'http://127.0.0.1:{port}'
        h = {'X-API-Key': key, 'Content-Type': 'application/json'}
        try:
            for _ in range(150):
                try:
                    http(base + '/health')
                    break
                except Exception:
                    if proc.poll() is not None:
                        check('serve.py stayed up through startup', False, 'exited early')
                        return
                    time.sleep(0.1)
            else:
                check('serve.py became ready', False, 'timed out')
                return

            rewritten = 0          # non-vacuity: probes the server CORRECTED
            checked = 0            # non-vacuity: fields actually asserted on

            # ---- door 1 + 2: PUT /vault/note, mode=write and mode=append ----
            note_probes = [
                ('Research/topic', 'write', 'bare slug — the .md default'),
                ('Notes/Q3 v1.2 plan', 'write', 'dotted TITLE, not an extension'),
                ('Notes/Meeting 2026.08.30', 'write', 'dated title'),
                ('Sites/page.html', 'write', 'a real extension, kept as-is'),
                ('/Deep\\Dir/note', 'write', 'leading slash + backslash'),
                ('Journal/day', 'append', 'append creates, same resolver'),
                ('Journal/day', 'append', 'append to an existing note'),
            ]
            for rel, mode, label in note_probes:
                st, raw = http(
                    base + '/vault/note?path=' + urllib.parse.quote(rel, safe='')
                    + '&mode=' + mode, 'PUT', b'hello 12', h)
                if st != 200:
                    check(f'PUT /vault/note ({label}) answered 200', False, f'{st} {raw[:120]}')
                    continue
                got = (json.loads(raw) or {}).get('path', '')
                disk = on_disk(vault)
                rows = listing(base, h)
                checked += 1
                if got != rel:
                    rewritten += 1
                check(f'PUT /vault/note ({label}) → {got!r} is on disk',
                      got in disk, f'asked {rel!r}; disk holds '
                                   f'{sorted(p for p in disk if not os.path.isdir(os.path.join(vault, p)))}')
                check(f'…and {got!r} is a row /vault/list returns',
                      got in rows, sorted(rows))

            # ---- door 3: POST /vault/upload (multipart) ----
            def upload(files, folder):
                b = uuid.uuid4().hex
                parts = []
                for name, data in files:
                    parts.append(
                        ('--' + b + '\r\nContent-Disposition: form-data; name="f"; '
                         f'filename="{name}"\r\nContent-Type: application/octet-stream'
                         '\r\n\r\n').encode('utf-8') + data + b'\r\n')
                payload = b''.join(parts) + ('--' + b + '--\r\n').encode('utf-8')
                return http(base + '/vault/upload?dir=' + urllib.parse.quote(folder),
                            'POST', payload,
                            {'X-API-Key': key,
                             'Content-Type': 'multipart/form-data; boundary=' + b})

            for label, files in [
                ('extensionless + dotted-title drops',
                 [('README', b'r'), ('Q3 v1.2 plan', b'v')]),
                ('the collision sidestep', [('README', b'again')]),
            ]:
                st, raw = upload(files, 'Up')
                if st != 200:
                    check(f'POST /vault/upload ({label}) answered 200', False, f'{st} {raw[:120]}')
                    continue
                body = json.loads(raw) or {}
                disk = on_disk(vault)
                rows = listing(base, h)
                for i, entry in enumerate(body.get('uploaded') or []):
                    got = entry.get('path', '')
                    asked = 'Up/' + files[i][0]
                    checked += 1
                    if got != asked:
                        rewritten += 1
                    check(f'POST /vault/upload ({label}) → {got!r} is on disk',
                          got in disk, f'asked {asked!r}')
                    check(f'…and {got!r} is a row /vault/list returns',
                          got in rows, sorted(rows))

            # ---- door 4: POST /vault/rename ----
            # `to` names a row the Library holds NOW; `from` names a row it
            # held a moment ago. Both halves, because a rename that answers
            # with the pre-resolve spelling of EITHER end is a receipt no
            # listing can be matched against.
            rename_probes = [
                ({'from': 'Research/topic', 'to': 'Research/renamed'},
                 'bare slug on both ends'),
                ({'from': 'Journal/day', 'to': '/Arch\\Old/day2'},
                 'leading slash + backslash destination'),
            ]
            for req, label in rename_probes:
                before = listing(base, h)
                st, raw = http(base + '/vault/rename', 'POST',
                               json.dumps(req).encode('utf-8'), h)
                if st != 200:
                    check(f'POST /vault/rename ({label}) answered 200', False, f'{st} {raw[:160]}')
                    continue
                body = json.loads(raw) or {}
                got_to, got_from = body.get('to', ''), body.get('from', '')
                disk, rows = on_disk(vault), listing(base, h)
                checked += 2
                if got_to != req['to']:
                    rewritten += 1
                if got_from != req['from']:
                    rewritten += 1
                check(f'POST /vault/rename ({label}) → to={got_to!r} is on disk',
                      got_to in disk, f'asked {req["to"]!r}')
                check(f'…and to={got_to!r} is a row /vault/list returns now',
                      got_to in rows, sorted(rows))
                check(f'…and from={got_from!r} is a row /vault/list returned before',
                      got_from in before, sorted(before))

            # ---- the folder arm of the same door ----
            os.makedirs(os.path.join(vault, 'Drawer'), exist_ok=True)
            with open(os.path.join(vault, 'Drawer', 'a.md'), 'w') as fh:
                fh.write('x')
            st, raw = http(base + '/vault/rename', 'POST',
                           json.dumps({'from': 'Drawer', 'to': '/Moved'}).encode('utf-8'), h)
            if st == 200:
                body = json.loads(raw) or {}
                checked += 1
                if body.get('to') != '/Moved':
                    rewritten += 1
                check('POST /vault/rename (a whole drawer) → to=%r is a folder on disk'
                      % body.get('to'),
                      os.path.isdir(os.path.join(vault, body.get('to') or '\0')),
                      sorted(on_disk(vault)))
            else:
                check('POST /vault/rename (a whole drawer) answered 200', False,
                      f'{st} {raw[:160]}')

            # ---- non-vacuity ----
            # An invariant nothing exercises passes trivially. This run is
            # only evidence if the server genuinely CORRECTED several of the
            # names it was handed — pre-fix every one of these came back
            # uncorrected, so this arm is also the one that proves the
            # probes are still reaching the rewrites they were chosen for.
            check('the run is not vacuous: at least 8 probes were genuinely '
                  'rewritten by the server', rewritten >= 8,
                  f'{rewritten} rewritten / {checked} fields checked')
            check('…and at least 12 success-body fields were asserted on',
                  checked >= 12, checked)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()


# ── Round 2: the tool half, real lifted source under node ──────────────────
def round2_tools():
    print()
    print('Round 2 — VAULT_NEW / VAULT_APPEND carry the corrected path out on '
          'meta.filedAs')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return
    hq = HQ_RUNTIME.read_text(encoding='utf-8')
    art = ARTIFACTS.read_text(encoding='utf-8')

    vnew = lift_tool(hq, 'vault_new')
    vapp = lift_tool(hq, 'vault_append')
    check("vault_new's tool object is present in hq-runtime.jsx", bool(vnew))
    check("vault_append's tool object is present in hq-runtime.jsx", bool(vapp))
    emit_ceo = lift_on_tool(
        hq, "arg: (meta.filedAs || call.arg), result,\n               "
            "failed: !!meta.failed, outcome: meta.outcome || '',\n               echo:")
    emit_agent = lift_on_tool(
        hq, "arg: (meta.filedAs || call.arg), result,\n               "
            "failed: !!meta.failed, outcome: meta.outcome || '', cwd,\n               echo:")
    check("ceoStream's 'done' emission still prefers meta.filedAs over call.arg",
          bool(emit_ceo))
    check("agentStream's 'done' emission still prefers meta.filedAs over call.arg",
          bool(emit_agent))
    filed = lift_fn(art, 'agentFiledPath')
    check('agentFiledPath is liftable out of app/artifacts.jsx', bool(filed))
    if not (vnew and vapp and emit_ceo and emit_agent and filed):
        return

    art_pure = '\n'.join(ln for ln in art.split('\n')
                         if not ln.startswith('import ') and not ln.startswith('export '))

    script = '''
/* The ONLY thing stubbed is the network boundary, and it answers exactly
   what round 1 just proved the real server answers: the path it WROTE. */
const CafresoHQClient = {
  vaultWrite: async (path, body, mode) => ({
    path: /\\.[A-Za-z0-9]{1,8}$/.test(path) ? path : path + '.md',
    mode, size: (body || '').length,
  }),
};
/* The tool objects' `requires` gate is a free variable in the lifted
   source; it decides whether the tool is OFFERED, which is not what this
   test is about. */
const isVaultReady = () => true;
/* Same for the emission's transcript-echo helper: it composes the text the
   model sees next, which is a different surface from the visit's `arg`. */
const toolEchoHead = (name, arg) => `[${name}: ${arg}]`;
const vault_new = ''' + vnew + ''';
const vault_append = ''' + vapp + ''';
''' + art_pure + '''
const R = {};
const visits = [];
const onTool = (ev) => visits.push(ev);

for (const [tool, name, arg] of [[vault_new, 'VAULT_NEW', 'Research/topic'],
                                 [vault_append, 'VAULT_APPEND', 'Notes/Q3 v1.2 plan']]) {
  const meta = {};
  const call = { tool: { name }, arg };
  const result = await tool.run(arg, { meta, signal: null }, '# body');
  R[name + '_filedAs'] = meta.filedAs || '';
  R[name + '_result'] = result;
  const cwd = '';
  ''' + emit_ceo + ''';
  ''' + emit_agent + ''';
}
R.emittedArgs = visits.map(v => v.arg);
R.agentFiledPath = agentFiledPath(visits);
/* The control arm: a tool that never sets meta.filedAs is untouched — the
   fallback must still be call.arg, or this "fix" would have broken every
   other tool in the registry. */
{
  const meta = {}, cwd = '';
  const call = { tool: { name: 'BROWSER_FETCH' }, arg: 'example.com' };
  const result = 'text';
  const before = visits.length;
  ''' + emit_ceo + ''';
  R.untouchedArg = visits[before].arg;
}
console.log(JSON.stringify(R));
'''
    proc = subprocess.run(['node', '--input-type=module', '-e', script],
                          cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        check('the node harness ran', False, (proc.stderr or proc.stdout)[-400:])
        return
    out = json.loads(proc.stdout.strip().split('\n')[-1])
    print('    ' + json.dumps(out))
    check("VAULT_NEW's run stashes the server's corrected path on meta.filedAs",
          out['VAULT_NEW_filedAs'] == 'Research/topic.md', out['VAULT_NEW_filedAs'])
    check("VAULT_APPEND's run does the same (dotted TITLE, not an extension)",
          out['VAULT_APPEND_filedAs'] == 'Notes/Q3 v1.2 plan.md',
          out['VAULT_APPEND_filedAs'])
    check("both 'done' emissions report the corrected path as the visit's arg",
          out['emittedArgs'] == ['Research/topic.md', 'Research/topic.md',
                                 'Notes/Q3 v1.2 plan.md', 'Notes/Q3 v1.2 plan.md'],
          out['emittedArgs'])
    check('agentFiledPath — and so task.artifactPath, the out-tray link and the '
          'on-chain receipt title — names the file that exists',
          out['agentFiledPath'] == 'Notes/Q3 v1.2 plan.md', out['agentFiledPath'])
    check('a tool that never sets meta.filedAs still reports call.arg (no regression)',
          out['untouchedArg'] == 'example.com', out['untouchedArg'])


# ── Round 3: structural, so a fifth door has to answer too ─────────────────
def round3_structure():
    print()
    print('Round 3 — the answer is derived from the path OBJECT, one mechanism')
    src = SERVE.read_text(encoding='utf-8')
    check('serve.py defines _vault_rel_out', 'def _vault_rel_out(' in src)
    check('…and it derives the answer with relative_to(root) rather than '
          're-deriving a rule from the request string',
          bool(re.search(r'def _vault_rel_out\(.*?relative_to\(root\)', src, re.S)))
    check('…and falls back to the caller string rather than answering with no '
          'path at all', bool(re.search(r'def _vault_rel_out\(.*?return fallback',
                                        src, re.S)))
    # Every fs success body on a write door. Pinned by their own distinctive
    # response shapes rather than by line number.
    for label, pattern in [
        ("PUT /vault/note's fs success body",
         r"\{'path': _vault_rel_out\(target, rel\),"),
        ("POST /vault/rename's file success body",
         r"\{'from': _vault_rel_out\(s_path, src\),\s*\n\s*'to': _vault_rel_out\(d_path, dst\),\s*\n\s*'linksRewritten'"),
        ("POST /vault/rename's folder success body",
         r"'to': _vault_rel_out\(d_path, dst\),\s*\n\s*'folder': True"),
        ("POST /vault/upload's per-file entry",
         r"entry = \{'path': _vault_rel_out\(_tgt, rel\) if _tgt is not None else rel,"),
    ]:
        check(f'{label} answers with the resolved path',
              bool(re.search(pattern, src)))
    # …and neither of the two backends whose written path this server can
    # KNOW still answers with the bare request string. The `rest` backend is
    # deliberately not on this list and is recorded EXPOSED in `## 415.`:
    # Obsidian's REST API does its own filing upstream, so the only honest
    # source for what it wrote is a round-trip this door does not make, and
    # inventing a correction here would be a second mechanism guessing.
    check("PUT /vault/note's fs branch no longer answers {'path': rel, 'mode': mode, "
          "'size': …}",
          "{'path': rel, 'mode': mode, 'size': target.stat()" not in src)
    check("POST /vault/upload no longer answers {'path': rel, 'size': len(data)}",
          "{'path': rel, 'size': len(data)}" not in src)
    check("PUT /vault/note's oci branch derives its path from the key it put",
          "key[len(_pfx):]" in src)
    hq = HQ_RUNTIME.read_text(encoding='utf-8')
    # Pinned on the guarded spelling the four vault-note tools use, not the
    # bare assignment — the three EXPORT_ tools already carry filedAs with
    # their own unguarded `if (_ctx && _ctx.meta)`, so a loose count of the
    # assignment alone could not tell a missing vault tool from a present
    # export one. (Found by the fire test: dropping VAULT_APPEND's line left
    # the loose count at 5 and this check green.)
    guarded = re.findall(
        r"if \(_ctx && _ctx\.meta && r && r\.path\) _ctx\.meta\.filedAs = r\.path;", hq)
    check('all four vault-note-writing tool runs carry filedAs out '
          '(VAULT_NEW, VAULT_APPEND, MEMORY_WRITE, MEMORY_APPEND)',
          len(guarded) == 4, len(guarded))


def main() -> int:
    print('#415 — every vault-writing door names the file it wrote')
    for p, label in [(SERVE, 'serve.py'), (HQ_RUNTIME, 'hq-runtime.jsx'),
                     (ARTIFACTS, 'app/artifacts.jsx')]:
        if not p.is_file():
            print(f'  FAIL  missing {label}')
            return 1
    round1_live_server()
    round2_tools()
    round3_structure()
    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
