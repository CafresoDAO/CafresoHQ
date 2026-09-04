#!/usr/bin/env python3
""""Generate child note" wrote over whatever was already at that path
(agent_runner.jsx).

Right-click a note in the graph -> "Generate child note". The runner asks
the model for a sub-topic, takes the TITLE: line the model produced, slugs
it into a filename, and files it in the PARENT'S OWN FOLDER:

    const folder = nodeId.split('/').slice(0, -1).join('/') || 'Inbox';
    const path = `${folder}/${slug(title)}.md`;
    await CafresoHQClient.vaultWrite(path, ..., 'write');

Nothing between those two lines asks whether a note is already filed there,
and `mode: 'write'` on PUT /vault/note is a REPLACE on every backend the
Library has (serve.py: `target.write_text(body)`; REST: PUT; OCI:
put_object). So the model's choice of title was, in effect, the choice of
which existing note to destroy:

  * The model echoes the parent's name — the single most likely collision,
    since the parent's title is the only title in its prompt. Parent
    "Notes/Project Helios.md" + TITLE: Project Helios resolves to
    "Notes/Project Helios.md". The parent note was overwritten by its own
    child. The follow-up "link from the parent" step then read the child
    back and appended a link to itself — the only surviving trace.
  * The model picks a sibling that already exists ("API Design" next door).
    That note is replaced by generated text, no error, no prompt, no undo;
    the graph refresh right after makes it look like a normal success.

The rest of the office already refuses this: the Library's own upload door
collision-steps a filename, and rename answers 409 on a collision. Only the
runner, the one writer whose filenames come from a language model, replaced.

Fix (minimal): a `pathTaken()` probe, and a step loop that walks
`<base>.md`, `<base>-2.md`, ... up to 20 before giving up and THROWING (the
dispatcher turns that into a cafresohq:agentRunnerError the UI shows) rather
than overwriting. `pathTaken` is deliberately conservative — only a real
404/"not found" from vaultRead clears a path; any other failure (offline,
502, bridge refusal) leaves the answer unknown, and unknown is not
permission to replace. The parent's back-link now points at the file that
was actually written, not at the un-stepped title.

This test extracts the REAL `slug`, `pathTaken` and `handleGenerateChild`
out of agent_runner.jsx by source-anchored brace balancing (not a line
range, not a reimplementation) and runs them under Node against a fake
in-memory Library, so a regression that drops the step loop fails here.

Run: python3 scripts/test_a_generated_child_never_lands_on_an_existing_note.py
(skips the live-execution checks if `node` isn't on PATH — the source-shape
checks still run everywhere)
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNNER_JSX = ROOT / 'agent_runner.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract_function(src, name):
    """Pull `[async] function <name>(...) { ... }` out of src by balancing
    braces from the first `{` of the body, skipping strings, template
    literals, regex-ish slashes and comments. Anchored on the declaration,
    not on line numbers."""
    m = re.search(r'(async\s+)?function\s+' + re.escape(name) + r'\s*\(', src)
    if not m:
        raise AssertionError('function %s not found' % name)
    start = m.start()
    # Walk past the PARAMETER list first — a destructured param (`{ nodeId,
    # agent }`) opens a brace that is not the body.
    j = m.end()
    paren = 1
    while paren:
        if src[j] == '(':
            paren += 1
        elif src[j] == ')':
            paren -= 1
        j += 1
    i = src.index('{', j)
    depth = 0
    n = len(src)
    in_str = None
    prev = ''
    while i < n:
        c = src[i]
        if in_str:
            if c == '\\':
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c in '"\'`':
            in_str = c
        elif c == '/' and i + 1 < n and src[i + 1] == '/':
            i = src.find('\n', i)
            if i == -1:
                break
            continue
        elif c == '/' and i + 1 < n and src[i + 1] == '*':
            i = src.find('*/', i) + 2
            continue
        elif c == '/' and prev in '(,=:[!&|?{};+' :
            # a regex literal — its body may hold quotes and braces that are
            # not JS syntax (`/[\\/:*?"<>|]/g` in slug(), for one)
            j = i + 1
            in_class = False
            while j < n:
                d = src[j]
                if d == '\\':
                    j += 2
                    continue
                if d == '[':
                    in_class = True
                elif d == ']':
                    in_class = False
                elif d == '/' and not in_class:
                    break
                j += 1
            i = j + 1
            prev = '/'
            continue
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        if not c.isspace():
            prev = c
        i += 1
    raise AssertionError('unterminated body for function %s' % name)


def main():
    src = RUNNER_JSX.read_text(encoding='utf-8')

    slug_src = extract_function(src, 'slug')
    child_src = extract_function(src, 'handleGenerateChild')
    check('slug() extracted from agent_runner.jsx', 'replace(/\\.md$/' in slug_src)
    check('handleGenerateChild() extracted from agent_runner.jsx',
          'vaultWrite' in child_src and 'Parent: [[' in child_src)

    try:
        taken_src = extract_function(src, 'pathTaken')
    except AssertionError:
        taken_src = ''
    check('agent_runner.jsx has an existence probe before it files a generated note',
          bool(taken_src), 'no pathTaken() — nothing checks the path before vaultWrite')

    # --- source-shape checks -------------------------------------------------

    check('the child path is no longer a single unchecked `${folder}/${slug(title)}.md`',
          not re.search(r'const\s+path\s*=\s*`\$\{folder\}/\$\{slug\(title\)\}\.md`', child_src),
          'the un-stepped path expression is still there')

    check('handleGenerateChild steps the filename before writing',
          ('pathTaken(' in child_src) and ('-${n}' in child_src or "-' + n" in child_src),
          child_src[-900:])

    if taken_src:
        check('pathTaken treats a non-404 failure as TAKEN (unknown is not permission to overwrite)',
              re.search(r'return\s*!\s*/not found\|404/i\.test', taken_src) is not None,
              taken_src)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted handler)',
          has_node, 'skipping the live-execution checks')

    if not has_node:
        print()
        print(('FAILED: %s' % FAILS) if FAILS else
              'source-shape checks passed (node unavailable, live checks skipped)')
        return 1 if FAILS else 0

    harness = """
'use strict';
const results = [];
function check(name, cond, detail) { results.push([name, !!cond, detail === undefined ? null : detail]); }

// --- a fake Library: an in-memory path -> content map that answers the way
// the real doors do (GET 404s on a missing note, PUT mode 'write' REPLACES).
let files = {};
let modelTitle = '';
const writes = [];
const CafresoHQClient = {
  async vaultRead(p) {
    if (!(p in files)) throw new Error('not found');
    return files[p];
  },
  async vaultWrite(p, content) { writes.push(p); files[p] = content; return { path: p }; },
};

// stand-ins for the runner's own surroundings (all unrelated to the bug)
const window = { CafresoHQGraph: null, dispatchEvent() {} };
function emitActivity() {}
async function readWithBeacon(p) { try { return await CafresoHQClient.vaultRead(p); } catch (_) { return ''; } }
async function ask() { return 'TITLE: ' + modelTitle + '\\n---\\nA body for the child note.\\n'; }

__SLUG__
__PATH_TAKEN__
__HANDLE_GENERATE_CHILD__

async function run(seedFiles, title, nodeId) {
  files = Object.assign({}, seedFiles);
  modelTitle = title;
  writes.length = 0;
  let threw = null;
  try { await handleGenerateChild({ nodeId, agent: null }); }
  catch (e) { threw = e && e.message || String(e); }
  return { files: Object.assign({}, files), writes: writes.slice(), threw };
}

(async () => {
  const PARENT = 'Notes/Project Helios.md';
  const PARENT_BODY = '# Project Helios\\n\\nThe boss wrote this. Budget: 40k. Owner: Ana.\\n';

  // --- Scenario A: the model echoes the parent's own title. --------------
  {
    const out = await run({ [PARENT]: PARENT_BODY }, 'Project Helios', PARENT);
    check('THE BUG: the parent note still holds the boss\\'s own text after a same-titled child',
      out.files[PARENT] && out.files[PARENT].includes('Budget: 40k'),
      { parent: out.files[PARENT], writes: out.writes });
    check('THE FIX: the child was filed under a stepped name, beside the parent',
      !!out.files['Notes/Project Helios-2.md'], Object.keys(out.files));
    check('THE FIX: the parent gained a link to the file that was actually written',
      out.files[PARENT] && out.files[PARENT].includes('[[Project Helios-2]]'),
      out.files[PARENT]);
  }

  // --- Scenario B: the model picks an existing SIBLING. ------------------
  {
    const SIB = 'Notes/API Design.md';
    const SIB_BODY = '# API Design\\n\\nv3 endpoints, agreed 2026-04-02.\\n';
    const out = await run({ [PARENT]: PARENT_BODY, [SIB]: SIB_BODY }, 'API Design', PARENT);
    check('THE BUG: an existing sibling note is not replaced by generated text',
      out.files[SIB] === SIB_BODY, out.files[SIB]);
    check('THE FIX: the generated child landed on a free path instead',
      !!out.files['Notes/API Design-2.md'], Object.keys(out.files));
    check('no write ever targeted an occupied path',
      out.writes.every(p => p === PARENT || p === 'Notes/API Design-2.md'), out.writes);
  }

  // --- Scenario C: the ordinary case — a fresh title still writes exactly
  // where it always did, with the same back-link. -------------------------
  {
    const out = await run({ [PARENT]: PARENT_BODY }, 'Helios Telemetry', PARENT);
    check('an uncontested title still files at `<parent folder>/<title>.md` (no gratuitous suffix)',
      !!out.files['Notes/Helios Telemetry.md'] && !out.files['Notes/Helios Telemetry-2.md'],
      Object.keys(out.files));
    check('the parent still gets its back-link in the ordinary case',
      out.files[PARENT].includes('[[Helios Telemetry]]'), out.files[PARENT]);
    check('the ordinary case does not throw', out.threw === null, out.threw);
  }

  // --- Scenario D: the Library is unreachable (read fails with something
  // that is NOT a 404). Unknown must not authorize a replace. -------------
  {
    files = { [PARENT]: PARENT_BODY };
    modelTitle = 'Project Helios';
    writes.length = 0;
    const realRead = CafresoHQClient.vaultRead;
    CafresoHQClient.vaultRead = async () => { throw new Error('HTTP 502'); };
    let threw = null;
    try { await handleGenerateChild({ nodeId: PARENT, agent: null }); }
    catch (e) { threw = e && e.message || String(e); }
    CafresoHQClient.vaultRead = realRead;
    check('a Library that cannot answer never causes an overwrite — it refuses',
      threw !== null && writes.length === 0 && files[PARENT] === PARENT_BODY,
      { threw, writes: writes.slice() });
    check('the refusal says the note was not written',
      typeof threw === 'string' && /not written/.test(threw), threw);
  }

  console.log(JSON.stringify(results));
})();
"""
    harness = (harness
               .replace('__SLUG__', slug_src)
               .replace('__PATH_TAKEN__', taken_src)
               .replace('__HANDLE_GENERATE_CHILD__', child_src))

    proc = subprocess.run(['node', '-e', harness], capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        check('node harness ran without throwing', False, proc.stderr.strip()[-2000:])
        print()
        print('FAILED: %s' % FAILS)
        return 1

    try:
        node_results = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as e:
        check('node harness produced parseable JSON', False,
              '%s — stdout: %r' % (e, proc.stdout[:2000]))
        print()
        print('FAILED: %s' % FAILS)
        return 1

    for item in node_results:
        name, cond = item[0], item[1]
        detail = item[2] if len(item) > 2 else ''
        check(name, cond, detail)

    print()
    print(('FAILED: %s' % FAILS) if FAILS
          else 'generated child notes never land on an occupied path: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
