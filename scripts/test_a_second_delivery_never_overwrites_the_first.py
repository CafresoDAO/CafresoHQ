#!/usr/bin/env python3
"""Two finished tasks with the same title filed to ONE file (app/artifacts.jsx).

`fileDelivery` built the cabinet path as `${home}/${slugify(task.title)}.md`
and wrote it with `mode: 'write'`:

    await CafresoHQClient.vaultWrite(built.path, built.content, 'write');

Nothing between those two lines asked whether a note was already filed
there, and `mode: 'write'` on PUT /vault/note is a REPLACE on every backend
the Library has (serve.py: `target.write_text(body)`; REST: PUT; OCI:
put_object). Nothing about the path is unique either — the folder is one of
four constants (STARTER_HOME / DEFAULT_HOME) and the slug is the boss's own
words, cut at 56 characters. So:

  * The same brief handed to two coworkers to compare their answers. The
    starter card derives the title from the subject, so both tasks are
    "Research brief: how small teams price a new product" and both resolve
    to `Research/research-brief-how-small-teams-price-a-new-product.md`. The
    second delivery replaced the first; the surviving sheet's own header
    credits whichever coworker finished last.
  * Two DIFFERENT briefs whose first ~41 characters agree — "Research
    brief: " already spends 16 of the 56-character cap.

Both tasks then carry the same `artifactPath`, so the out-tray's "open the
latest" on the first coworker opens the second coworker's work under the
first one's name, and the office's delivery count says two where the
cabinet holds one.

agent_runner.jsx's child-note writer had the identical bug and the
identical fix (`pathTaken` + a step loop) — see
scripts/test_a_generated_child_never_lands_on_an_existing_note.py. The
deliverable filer, the writer the boss meets first, never got it.

Fix (minimal): a conservative `pathIsFree()` probe and a step loop that
walks `<base>.md`, `<base>-2.md`, … up to 20 before giving up and filing
NOTHING (returning null, which the caller already handles as "no artifact")
rather than replacing someone's delivery. `pathIsFree` clears a name only
on a real 404/"not found"; offline, 502 or a 415 leaves the answer unknown,
and unknown is not permission to overwrite. A re-run of the SAME task —
`task.artifactPath` already equal to the candidate — still refreshes its own
sheet in place, so retries don't grow -2, -3, … beside it.

This test lifts the REAL module (imports/exports dropped, the browser-only
`cabinetIsEncrypted` excised by brace balancing) and runs `fileDelivery`
under Node against a fake in-memory Library, so a regression that drops the
step loop fails here.

Run: python3 scripts/test_a_second_delivery_never_overwrites_the_first.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app' / 'artifacts.jsx'
FLOOR = ROOT / 'app' / 'floor.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + str(detail)) if detail else ""}')


def _strip_module_lines(path):
    return '\n'.join(ln for ln in path.read_text(encoding='utf-8').split('\n')
                     if not ln.startswith('import ') and not ln.startswith('export '))


def _cut_function(src, anchor):
    """Remove one whole function from the source by brace balancing."""
    i = src.find(anchor)
    if i == -1:
        return src
    depth, j, started = 0, i, False
    while j < len(src):
        if src[j] == '{':
            depth += 1
            started = True
        elif src[j] == '}':
            depth -= 1
            if started and depth == 0:
                j += 1
                break
        j += 1
    return src[:i] + src[j:]


def module_source():
    """artifacts.jsx (with floor.jsx's visitLine) minus its browser-only bits.

    `fileDelivery` is KEPT — it is the subject here — and reaches the fake
    Library through the free `CafresoHQClient` binding the harness defines.
    """
    src = _strip_module_lines(FLOOR) + '\n' + _strip_module_lines(SRC)
    return _cut_function(src, 'function cabinetIsEncrypted')


HARNESS = r"""
'use strict';
const results = [];
function check(name, cond, detail) { results.push([name, !!cond, detail === undefined ? null : detail]); }

// --- a fake Library: an in-memory path -> content map that answers the way
// the real doors do (GET 404s on a missing note, PUT mode 'write' REPLACES).
let files = {};
const writes = [];
let readMode = 'normal';        // 'normal' | 'offline'
const CafresoHQClient = {
  async vaultStatus() { return { configured: true, exists: true }; },
  async vaultRead(p) {
    if (readMode === 'offline') throw new Error('Failed to fetch');
    if (!(p in files)) throw new Error('not found');
    return files[p];
  },
  async vaultWrite(p, content, mode) { writes.push([p, mode]); files[p] = content; return { path: p }; },
};

__MODULE__

async function file(task, agentName, text) {
  return await fileDelivery(task, { name: agentName }, text, []);
}

(async () => {
  const TITLE = 'Research brief: how small teams price a new product';
  const SLUG = 'Research/research-brief-how-small-teams-price-a-new-product.md';

  // --- Scenario A: the same brief, two coworkers, compared side by side ---
  {
    files = {}; writes.length = 0; readMode = 'normal';
    const a = { id: 't1', title: TITLE, starter: 'brief' };
    const b = { id: 't2', title: TITLE, starter: 'brief' };
    const pathA = await file(a, 'Nova', 'Nova says price on value, not on cost.');
    const pathB = await file(b, 'Kip', 'Kip says price on cost, not on value.');

    check("the first delivery lands where the slug says it should",
      pathA === SLUG, pathA);
    check("THE BUG: Nova's delivery is still in the cabinet after Kip files his",
      !!files[SLUG] && files[SLUG].includes('price on value'),
      { atSlug: (files[SLUG] || '').slice(0, 120), files: Object.keys(files) });
    check("THE FIX: Kip's delivery was stepped to a free name",
      pathB === 'Research/research-brief-how-small-teams-price-a-new-product-2.md', pathB);
    check("THE FIX: both deliveries exist as two separate files",
      Object.keys(files).length === 2, Object.keys(files));
    check("the two tasks no longer share one artifactPath",
      pathA !== pathB, [pathA, pathB]);
    check("each sheet credits the coworker who wrote it",
      !!files[pathB] && files[pathB].includes('Delivered by Kip')
      && !!files[pathA] && files[pathA].includes('Delivered by Nova'),
      { a: (files[pathA] || '').slice(0, 80), b: (files[pathB] || '').slice(0, 80) });
    check("nothing was written with an append mode that would splice them together",
      writes.every(w => w[1] === 'write'), writes);
  }

  // --- Scenario B: two DIFFERENT briefs that collide only after the 56-char cut
  {
    files = {}; writes.length = 0; readMode = 'normal';
    const long1 = 'Research brief: how small teams handle onboarding for new hires in week one';
    const long2 = 'Research brief: how small teams handle onboarding for new hires in year one';
    const p1 = await file({ id: 'x1', title: long1, starter: 'brief' }, 'Nova', 'Week-one answer.');
    const p2 = await file({ id: 'x2', title: long2, starter: 'brief' }, 'Nova', 'Year-one answer.');
    check("titles that collide only after the 56-char slug cap still get two files",
      p1 !== p2 && Object.keys(files).length === 2, { p1, p2, files: Object.keys(files) });
    check("the earlier of the two long titles is intact",
      !!files[p1] && files[p1].includes('Week-one answer'), (files[p1] || '').slice(0, 120));
  }

  // --- Scenario C: a re-run of the SAME task refreshes its own sheet -------
  {
    files = {}; writes.length = 0; readMode = 'normal';
    const t = { id: 't1', title: TITLE, starter: 'brief' };
    const first = await file(t, 'Nova', 'A first, thin answer.');
    t.artifactPath = first;                       // what app.jsx sets on the task
    const again = await file(t, 'Nova', 'A better answer on the second run.');
    check("re-running one task updates its own sheet instead of piling up -2, -3",
      again === first && Object.keys(files).length === 1, { first, again, files: Object.keys(files) });
    check("the re-run's text is the one now on the sheet",
      !!files[first] && files[first].includes('better answer'), (files[first] || '').slice(0, 160));
  }

  // --- Scenario D: an unreadable cabinet is not permission to overwrite ----
  {
    files = {}; writes.length = 0; readMode = 'normal';
    await file({ id: 't1', title: TITLE, starter: 'brief' }, 'Nova', 'The original delivery.');
    readMode = 'offline';                          // every probe now fails, not 404
    const p = await file({ id: 't2', title: TITLE, starter: 'brief' }, 'Kip', 'The replacement.');
    check("when the cabinet cannot answer, nothing is filed and nothing is replaced",
      p === null && files[SLUG].includes('The original delivery'),
      { returned: p, atSlug: (files[SLUG] || '').slice(0, 120) });
    check("…and no write was attempted at all",
      writes.length === 1, writes);
  }

  // --- Scenario E: the page starter's .html steps on its extension ---------
  {
    files = {}; writes.length = 0; readMode = 'normal';
    const html = '<html><body><h1>Dog walking</h1></body></html>';
    const t1 = { id: 'p1', title: 'Simple page: a one-page site for my dog-walking business', starter: 'page' };
    const t2 = { id: 'p2', title: 'Simple page: a one-page site for my dog-walking business', starter: 'page' };
    const h1 = await file(t1, 'Nova', html);
    const h2 = await file(t2, 'Kip', '<html><body><h1>Cat sitting</h1></body></html>');
    check("a stepped .html keeps its extension (…-2.html, not ….html-2)",
      h1.endsWith('.html') && h2.endsWith('-2.html'), { h1, h2 });
    check("the first page is still openable html, not the second page's markup",
      files[h1].includes('Dog walking'), (files[h1] || '').slice(0, 80));
  }

  console.log(JSON.stringify(results));
})();
"""


def run():
    if not shutil.which('node'):
        print('  FAIL  node is on PATH (needed to execute the real fileDelivery)')
        return 1
    script = HARNESS.replace('__MODULE__', module_source())
    proc = subprocess.run(['node', '--input-type=module', '-e', script],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


print('a second delivery never overwrites the first')
for name, ok, detail in run():
    check(name, ok, '' if detail is None else json.dumps(detail)[:300])

print()
if FAILS:
    print(f'delivery filing: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
    raise SystemExit(1)
print('delivery filing: all checks passed')
